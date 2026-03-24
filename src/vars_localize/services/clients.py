"""Dedicated API clients used by M3Service.

Each client encapsulates endpoint paths and request behavior for one backend
service so M3Service can remain an orchestration/facade layer.
"""

import json
from typing import Any, Dict, List, Optional

import requests

from vars_localize.util.logging import get_logger

logger = get_logger("M3Clients")


class AnnosaurusClient:
    """Client for annosaurus endpoints, including JWT-based auth.

    Args:
        endpoint: Raziel endpoint metadata for annosaurus.
    """

    SERVICE_NAME = "annosaurus"

    OBSERVATION = "/annotations"
    ASSOCIATION = "/associations"
    FAST_SEARCH = "/fast/concept/images"
    IMAGE_COUNT = "/observations/concept/images/count"
    IMAGED_MOMENT = "/imagedmoments"
    WINDOW_REQUEST = "/imagedmoments/windowrequest"
    ALL_CONCEPTS_USED = "/observations/concepts"
    DELETE_OBSERVATION = "/observations"
    IMAGED_MOMENTS_BY_CONCEPT = "/fast/imagedmoments/concept/images"
    IMAGED_MOMENTS_BY_IMAGE_REFERENCE = "/annotations/imagereference"
    ANNOTATIONS_BY_VIDEO_REFERENCE = "/fast/videoreference"

    def __init__(self, endpoint: Dict[str, Any]):
        """Initialize the client from Raziel endpoint metadata.

        Args:
            endpoint: Endpoint metadata containing at least `url` and `secret`.
        """
        self._base_url = endpoint["url"].rstrip("/")
        self._secret = endpoint["secret"]
        self._session = requests.Session()

    def _url(self, path: str) -> str:
        """Build an absolute URL for this service.

        Args:
            path: Relative path beginning with `/`.

        Returns:
            Fully qualified URL for the service.
        """
        return self._base_url + path

    def authenticate(self) -> None:
        """Authenticate against annosaurus and install a bearer token.

        Raises:
            RuntimeError: If authentication fails.
        """
        try:
            response = self._session.post(
                self._url("/auth"),
                headers={"Authorization": "APIKEY {}".format(self._secret)},
            )
            response.raise_for_status()

            token = response.json()["access_token"]
            # Keep auth state in the session so all subsequent requests reuse it.
            self._session.headers.update({"Authorization": "BEARER " + token})
        except Exception as exc:
            logger.exception("Authentication failed: {}", exc)
            raise RuntimeError("Failed to authenticate with Annosaurus.") from exc

    def _require_auth(self) -> None:
        """Guard methods that require annosaurus JWT auth.

        Raises:
            Exception: If the client has not been authenticated yet.
        """
        if "Authorization" not in self._session.headers:
            raise Exception("Session must be authenticated")

    def get_imaged_moment_uuids(self, concept: str) -> List[str]:
        """Return imaged moment UUIDs for a concept.

        Args:
            concept: Concept name.

        Returns:
            List of imaged moment UUID strings.
        """
        self._require_auth()
        response = self._session.get(
            self._url(self.IMAGED_MOMENTS_BY_CONCEPT + "/" + concept)
        )
        return response.json()

    def get_imaged_moment(self, imaged_moment_uuid: str) -> Dict[str, Any]:
        """Return imaged moment details by UUID.

        Args:
            imaged_moment_uuid: Imaged moment UUID.

        Returns:
            Parsed JSON payload.
        """
        self._require_auth()
        response = self._session.get(
            self._url(self.IMAGED_MOMENT + "/" + imaged_moment_uuid)
        )
        return response.json()

    def get_imaged_moments_by_image_reference(
        self, image_reference_uuid: str
    ) -> Optional[Any]:
        """Return imaged moments linked to an image reference UUID.

        Args:
            image_reference_uuid: Image reference UUID.

        Returns:
            Parsed JSON payload, or None when request/logged failure occurs.
        """
        try:
            response = self._session.get(
                self._url(
                    self.IMAGED_MOMENTS_BY_IMAGE_REFERENCE + "/" + image_reference_uuid
                )
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            logger.warning(
                "Could not fetch imaged moment data for image reference {}".format(
                    image_reference_uuid
                ),
            )
            logger.exception("Image reference lookup failed: {}", exc)

    def get_annotations_by_video_reference(
        self, video_reference_uuid: str
    ) -> Optional[Any]:
        """Return annotations for a video reference UUID.

        Args:
            video_reference_uuid: Video reference UUID.

        Returns:
            Parsed JSON payload, or None when request/logged failure occurs.
        """
        try:
            response = self._session.get(
                self._url(
                    self.ANNOTATIONS_BY_VIDEO_REFERENCE + "/" + video_reference_uuid
                ),
                params={"data": True},
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            logger.warning(
                "Could not fetch annotation data for video reference {}".format(
                    video_reference_uuid
                ),
            )
            logger.exception("Video reference annotation lookup failed: {}", exc)

    def delete_observation(self, observation_uuid: str) -> Optional[requests.Response]:
        """Delete an observation by UUID.

        Args:
            observation_uuid: Observation UUID.

        Returns:
            Response on success, or None when request/logged failure occurs.
        """
        self._require_auth()
        try:
            response = self._session.delete(
                self._url(self.DELETE_OBSERVATION + "/" + observation_uuid)
            )
            response.raise_for_status()
            return response
        except Exception as exc:
            logger.exception("Observation deletion failed: {}", exc)

    def rename_observation(
        self, observation_uuid: str, new_concept: str, observer: str
    ) -> Optional[Dict[str, Any]]:
        """Rename an observation to a new concept.

        Args:
            observation_uuid: Observation UUID.
            new_concept: New concept name.
            observer: Observer identifier.

        Returns:
            Parsed JSON payload, or None when request/logged failure occurs.
        """
        self._require_auth()
        request_data = {"concept": new_concept, "observer": observer}
        try:
            response = self._session.put(
                self._url(self.OBSERVATION + "/" + observation_uuid),
                data=request_data,
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            logger.exception("Concept rename failed: {}", exc)

    def create_observation(
        self,
        video_reference_uuid: str,
        concept: str,
        observer: str,
        timecode: Optional[str] = None,
        elapsed_time_millis: Optional[int] = None,
        recorded_timestamp: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Create an observation with one of the accepted time index fields.

        Args:
            video_reference_uuid: Video reference UUID.
            concept: Concept name.
            observer: Observer identifier.
            timecode: Optional SMPTE-like timecode.
            elapsed_time_millis: Optional elapsed time in milliseconds.
            recorded_timestamp: Optional recorded timestamp.

        Returns:
            Parsed JSON payload, or None when validation/request failure occurs.
        """
        self._require_auth()
        request_data: Dict[str, Any] = {
            "video_reference_uuid": video_reference_uuid,
            "concept": concept,
            "observer": observer,
            "activity": "localize",
            "group": "ROV:training-set",
        }

        if not (timecode or elapsed_time_millis or recorded_timestamp):
            logger.error("No observation index provided. Observation creation failed.")
            return None

        if timecode:
            request_data["timecode"] = timecode
        if elapsed_time_millis:
            request_data["elapsed_time_millis"] = int(elapsed_time_millis)
        if recorded_timestamp:
            request_data["recorded_timestamp"] = recorded_timestamp

        try:
            response = self._session.post(
                self._url(self.OBSERVATION), data=request_data
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            logger.exception("Observation creation failed: {}", exc)

    def create_box(
        self,
        box_json: Dict[str, Any],
        observation_uuid: str,
        to_concept: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Create a bounding-box association for an observation.

        Args:
            box_json: Bounding box payload.
            observation_uuid: Observation UUID.
            to_concept: Optional target concept for association.

        Returns:
            Parsed JSON payload, or None when request/logged failure occurs.
        """
        self._require_auth()
        request_data = {
            "observation_uuid": observation_uuid,
            "link_name": "bounding box",
            "link_value": json.dumps(box_json),
            "mime_type": "application/json",
        }

        if to_concept is not None:
            request_data["to_concept"] = to_concept

        try:
            response = self._session.post(
                self._url(self.ASSOCIATION), data=request_data
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            logger.exception("Box creation failed: {}", exc)

    def modify_box(
        self,
        box_json: Dict[str, Any],
        observation_uuid: str,
        association_uuid: str,
        to_concept: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Modify an existing bounding-box association.

        Args:
            box_json: Bounding box payload.
            observation_uuid: Observation UUID.
            association_uuid: Association UUID.
            to_concept: Optional target concept for association.

        Returns:
            Parsed JSON payload, or None when request/logged failure occurs.
        """
        self._require_auth()
        request_data = {
            "observation_uuid": observation_uuid,
            "link_name": "bounding box",
            "link_value": json.dumps(box_json),
            "mime_type": "application/json",
        }

        if to_concept is not None:
            request_data["to_concept"] = to_concept

        try:
            response = self._session.put(
                self._url(self.ASSOCIATION + "/" + association_uuid),
                data=request_data,
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            logger.exception("Box modification failed: {}", exc)

    def delete_box(self, association_uuid: str) -> Optional[requests.Response]:
        """Delete a bounding-box association by UUID.

        Args:
            association_uuid: Association UUID.

        Returns:
            Response on success, or None when request/logged failure occurs.
        """
        self._require_auth()
        try:
            response = self._session.delete(
                self._url(self.ASSOCIATION + "/" + association_uuid)
            )
            response.raise_for_status()
            return response
        except Exception as exc:
            logger.exception("Box deletion failed: {}", exc)


class OniClient:
    """Client for oni endpoints (merged kb + user service).

    Args:
        endpoint: Raziel endpoint metadata for oni.
        session: Shared HTTP session for non-auth oni calls.
    """

    SERVICE_NAME = "oni"

    ALL_USERS = "/users"
    ALL_CONCEPTS = "/concept"
    ALL_PARTS = "/phylogeny/taxa/organism part"

    def __init__(self, endpoint: Dict[str, Any], session: requests.Session):
        """Initialize from Raziel endpoint metadata and shared app session.

        Args:
            endpoint: Endpoint metadata containing at least `url`.
            session: Shared requests session.
        """
        self._base_url = endpoint["url"].rstrip("/")
        self._session = session
        self._kb_concepts: Optional[List[str]] = None
        self._kb_parts: Optional[List[str]] = None

    def _url(self, path: str) -> str:
        """Build an absolute URL for this service.

        Args:
            path: Relative path beginning with `/`.

        Returns:
            Fully qualified URL for the service.
        """
        return self._base_url + path

    def get_all_users(self) -> List[Dict[str, Any]]:
        """Return all users.

        Returns:
            User records returned by oni.
        """
        response = self._session.get(self._url(self.ALL_USERS))
        response.raise_for_status()
        return response.json()

    def get_all_concepts(self) -> List[str]:
        """Return all concepts with in-memory caching.

        Returns:
            Concept names.
        """
        if self._kb_concepts is None:
            response = self._session.get(self._url(self.ALL_CONCEPTS))
            response.raise_for_status()
            self._kb_concepts = response.json()
        return self._kb_concepts

    def get_all_parts(self) -> List[str]:
        """Return all parts with in-memory caching.

        Returns:
            Organism part names.
        """
        if self._kb_parts is None:
            response = self._session.get(self._url(self.ALL_PARTS))
            response.raise_for_status()
            self._kb_parts = [entry["name"] for entry in response.json()]
        return self._kb_parts


class VampireSquidClient:
    """Client for vampire-squid video metadata endpoints.

    Args:
        endpoint: Raziel endpoint metadata for vampire-squid.
        session: Shared HTTP session for requests.
    """

    SERVICE_NAME = "vampire-squid"

    VIDEO_DATA = "/videoreferences"
    VIDEO_BY_VIDEO_REFERENCE_UUID = "/videos/videoreference"

    def __init__(self, endpoint: Dict[str, Any], session: requests.Session):
        """Initialize from Raziel endpoint metadata and shared app session.

        Args:
            endpoint: Endpoint metadata containing at least `url`.
            session: Shared requests session.
        """
        self._base_url = endpoint["url"].rstrip("/")
        self._session = session

    def _url(self, path: str) -> str:
        """Build an absolute URL for this service.

        Args:
            path: Relative path beginning with `/`.

        Returns:
            Fully qualified URL for the service.
        """
        return self._base_url + path

    def get_video_data(self, video_reference_uuid: str) -> Optional[Any]:
        """Return video metadata for a video reference UUID.

        Args:
            video_reference_uuid: Video reference UUID.

        Returns:
            Parsed JSON payload, or None when request/logged failure occurs.
        """
        try:
            response = self._session.get(
                self._url(self.VIDEO_DATA + "/" + video_reference_uuid)
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            logger.warning("Could not fetch video data for {}", video_reference_uuid)
            logger.exception("Video data fetch failed: {}", exc)

    def get_video_by_video_reference_uuid(
        self, video_reference_uuid: str
    ) -> Optional[Any]:
        """Return video payload by reference UUID, normalizing list responses.

        Args:
            video_reference_uuid: Video reference UUID.

        Returns:
            Parsed JSON payload, or None when request/logged failure occurs.
        """
        try:
            response = self._session.get(
                self._url(
                    self.VIDEO_BY_VIDEO_REFERENCE_UUID + "/" + video_reference_uuid
                )
            )
            response.raise_for_status()

            response_parsed = response.json()
            if isinstance(response_parsed, list):
                return response_parsed[0]
            return response_parsed
        except Exception as exc:
            logger.warning(
                "Could not fetch video data for video reference {}",
                video_reference_uuid,
            )
            logger.exception("Video-by-reference fetch failed: {}", exc)
