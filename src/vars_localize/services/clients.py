"""Dedicated API clients used by M3Service.

Each client encapsulates endpoint paths and request behavior for one backend
service so M3Service can remain an orchestration/facade layer.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests

from vars_localize.services.errors import ServiceAuthError, ServiceValidationError
from vars_localize.services.http import request_with_policy


class AnnosaurusClient:
    """Client for annosaurus endpoints, including JWT-based auth.

    Args:
        endpoint: Raziel endpoint metadata for annosaurus.
    """

    SERVICE_NAME = "annosaurus"

    OBSERVATION = "/annotations"
    ASSOCIATION = "/associations"
    IMAGED_MOMENT = "/imagedmoments"
    DELETE_OBSERVATION = "/observations"
    IMAGED_MOMENTS_BY_CONCEPT = "/fast/imagedmoments/concept/images"
    IMAGED_MOMENTS_BY_IMAGE_REFERENCE = "/annotations/imagereference"
    ANNOTATIONS_BY_VIDEO_REFERENCE = "/fast/videoreference"
    IMAGED_MOMENTS_BY_VIDEO_REFERENCE = "/imagedmoments/videoreference"

    def __init__(
        self,
        endpoint: Dict[str, Any],
        session: Optional[requests.Session] = None,
    ):
        """Initialize the client from Raziel endpoint metadata.

        Args:
            endpoint: Endpoint metadata containing at least `url` and `secret`.
            session: Optional shared requests session.
        """
        self._base_url = endpoint["url"].rstrip("/")
        self._secret = endpoint["secret"]
        self._session = session or requests.Session()

    def _url(self, path: str) -> str:
        """Build an absolute URL for this service.

        Args:
            path: Relative path beginning with `/`.

        Returns:
            Fully qualified URL for the service.
        """
        return self._base_url + path

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        """Execute a request using the shared HTTP policy."""
        return request_with_policy(self._session, method, self._url(path), **kwargs)

    def authenticate(self) -> None:
        """Authenticate against annosaurus and install a bearer token.

        Raises:
            ServiceAuthError: If auth response does not include access token.
            ServiceRequestError: On HTTP transport/response failures.
        """
        response = self._request(
            "post",
            "/auth",
            headers={"Authorization": "APIKEY {}".format(self._secret)},
        )
        token = response.json().get("access_token")
        if not token:
            raise ServiceAuthError("Annosaurus auth response missing access_token")
        self._session.headers.update({"Authorization": "BEARER " + token})

    def _require_auth(self) -> None:
        """Guard methods that require annosaurus JWT auth.

        Raises:
            ServiceAuthError: If client has not yet authenticated.
        """
        if "Authorization" not in self._session.headers:
            raise ServiceAuthError("Session must be authenticated")

    def get_imaged_moment_uuids(self, concept: str) -> List[str]:
        """Return imaged moment UUIDs for a concept.

        Args:
            concept: Concept name.

        Returns:
            List of imaged moment UUID strings.
        """
        self._require_auth()
        response = self._request("get", self.IMAGED_MOMENTS_BY_CONCEPT + "/" + concept)
        payload = response.json()
        return payload if isinstance(payload, list) else []

    def get_imaged_moment(self, imaged_moment_uuid: str) -> Dict[str, Any]:
        """Return imaged moment details by UUID.

        Args:
            imaged_moment_uuid: Imaged moment UUID.

        Returns:
            Parsed JSON payload.
        """
        self._require_auth()
        response = self._request("get", self.IMAGED_MOMENT + "/" + imaged_moment_uuid)
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def get_imaged_moments_by_image_reference(
        self, image_reference_uuid: str
    ) -> List[Dict[str, Any]]:
        """Return imaged moments linked to an image reference UUID.

        Args:
            image_reference_uuid: Image reference UUID.

        Returns:
            Parsed JSON payload list.
        """
        self._require_auth()
        response = self._request(
            "get",
            self.IMAGED_MOMENTS_BY_IMAGE_REFERENCE + "/" + image_reference_uuid,
        )
        payload = response.json()
        return payload if isinstance(payload, list) else []

    def get_annotations_by_video_reference(
        self, video_reference_uuid: str
    ) -> List[Dict[str, Any]]:
        """Return annotations for a video reference UUID.

        Args:
            video_reference_uuid: Video reference UUID.

        Returns:
            Parsed JSON payload list.
        """
        self._require_auth()
        response = self._request(
            "get",
            self.ANNOTATIONS_BY_VIDEO_REFERENCE + "/" + video_reference_uuid,
            params={"data": True},
        )
        payload = response.json()
        return payload if isinstance(payload, list) else []

    def get_imaged_moments_by_video_reference(
        self, video_reference_uuid: str
    ) -> List[Dict[str, Any]]:
        """Return imaged moments for a video reference UUID.

        Args:
            video_reference_uuid: Video reference UUID.

        Returns:
            Parsed JSON payload list of ImagedMomentSC objects.
        """
        self._require_auth()
        response = self._request(
            "get",
            self.IMAGED_MOMENTS_BY_VIDEO_REFERENCE + "/" + video_reference_uuid,
        )
        payload = response.json()
        return payload if isinstance(payload, list) else []

    def delete_observation(self, observation_uuid: str) -> requests.Response:
        """Delete an observation by UUID.

        Args:
            observation_uuid: Observation UUID.

        Returns:
            Response on success.
        """
        self._require_auth()
        return self._request("delete", self.DELETE_OBSERVATION + "/" + observation_uuid)

    def rename_observation(
        self, observation_uuid: str, new_concept: str, observer: str
    ) -> Dict[str, Any]:
        """Rename an observation to a new concept.

        Args:
            observation_uuid: Observation UUID.
            new_concept: New concept name.
            observer: Observer identifier.

        Returns:
            Parsed JSON payload.
        """
        self._require_auth()
        request_data = {"concept": new_concept, "observer": observer}
        response = self._request(
            "put",
            self.OBSERVATION + "/" + observation_uuid,
            data=request_data,
        )
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def create_observation(
        self,
        video_reference_uuid: str,
        concept: str,
        observer: str,
        timecode: Optional[str] = None,
        elapsed_time_millis: Optional[int] = None,
        recorded_timestamp: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create an observation with one of the accepted time index fields.

        Args:
            video_reference_uuid: Video reference UUID.
            concept: Concept name.
            observer: Observer identifier.
            timecode: Optional SMPTE-like timecode.
            elapsed_time_millis: Optional elapsed time in milliseconds.
            recorded_timestamp: Optional recorded timestamp.

        Returns:
            Parsed JSON payload.

        Raises:
            ServiceValidationError: If no temporal index is provided.
        """
        self._require_auth()
        request_data: Dict[str, Any] = {
            "video_reference_uuid": video_reference_uuid,
            "concept": concept,
            "observer": observer,
            "activity": "localize",
            "group": "ROV:training-set",
        }

        if not (timecode or elapsed_time_millis is not None or recorded_timestamp):
            raise ServiceValidationError(
                "No observation index provided (timecode, elapsed_time_millis, or recorded_timestamp is required)."
            )

        if timecode:
            request_data["timecode"] = timecode
        if elapsed_time_millis is not None:
            request_data["elapsed_time_millis"] = int(elapsed_time_millis)
        if recorded_timestamp:
            request_data["recorded_timestamp"] = recorded_timestamp

        response = self._request("post", self.OBSERVATION, data=request_data)
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def create_box(
        self,
        box_json: Dict[str, Any],
        observation_uuid: str,
        to_concept: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a bounding-box association for an observation.

        Args:
            box_json: Bounding box payload.
            observation_uuid: Observation UUID.
            to_concept: Optional target concept for association.

        Returns:
            Parsed JSON payload.
        """
        self._require_auth()
        request_data: Dict[str, Any] = {
            "observation_uuid": observation_uuid,
            "link_name": "bounding box",
            "link_value": json.dumps(box_json),
            "mime_type": "application/json",
        }
        if to_concept is not None:
            request_data["to_concept"] = to_concept

        response = self._request("post", self.ASSOCIATION, data=request_data)
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def modify_box(
        self,
        box_json: Dict[str, Any],
        observation_uuid: str,
        association_uuid: str,
        to_concept: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Modify an existing bounding-box association.

        Args:
            box_json: Bounding box payload.
            observation_uuid: Observation UUID.
            association_uuid: Association UUID.
            to_concept: Optional target concept for association.

        Returns:
            Parsed JSON payload.
        """
        self._require_auth()
        request_data: Dict[str, Any] = {
            "observation_uuid": observation_uuid,
            "link_name": "bounding box",
            "link_value": json.dumps(box_json),
            "mime_type": "application/json",
        }
        if to_concept is not None:
            request_data["to_concept"] = to_concept

        response = self._request(
            "put",
            self.ASSOCIATION + "/" + association_uuid,
            data=request_data,
        )
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def delete_box(self, association_uuid: str) -> requests.Response:
        """Delete a bounding-box association by UUID.

        Args:
            association_uuid: Association UUID.

        Returns:
            Response on success.
        """
        self._require_auth()
        return self._request("delete", self.ASSOCIATION + "/" + association_uuid)


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
        self._concept_name_cache: Dict[str, str] = {}

    def _url(self, path: str) -> str:
        """Build an absolute URL for this service.

        Args:
            path: Relative path beginning with `/`.

        Returns:
            Fully qualified URL for the service.
        """
        return self._base_url + path

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        """Execute a request using the shared HTTP policy."""
        return request_with_policy(self._session, method, self._url(path), **kwargs)

    def get_all_users(self) -> List[Dict[str, Any]]:
        """Return all users.

        Returns:
            User records returned by oni.
        """
        response = self._request("get", self.ALL_USERS)
        payload = response.json()
        return payload if isinstance(payload, list) else []

    def get_all_concepts(self) -> List[str]:
        """Return all concepts with in-memory caching.

        Returns:
            Concept names.
        """
        if self._kb_concepts is None:
            response = self._request("get", self.ALL_CONCEPTS)
            payload = response.json()
            self._kb_concepts = payload if isinstance(payload, list) else []
        return self._kb_concepts

    def get_all_parts(self) -> List[str]:
        """Return all parts with in-memory caching.

        Returns:
            Organism part names.
        """
        if self._kb_parts is None:
            response = self._request("get", self.ALL_PARTS)
            payload = response.json()
            rows = payload if isinstance(payload, list) else []
            self._kb_parts = [entry["name"] for entry in rows if "name" in entry]
        return self._kb_parts

    def get_concept_name(self, concept: str) -> str:
        """Resolve a concept (possibly a synonym or common name) to its primary name.

        Args:
            concept: Any concept name recognized by the KB.

        Returns:
            The primary/canonical concept name, or *concept* unchanged if
            resolution fails.
        """
        if concept in self._concept_name_cache:
            return self._concept_name_cache[concept]
        try:
            response = self._request("get", f"/concept/{concept}")
            response.raise_for_status()
            name: str = response.json().get("name") or concept
        except Exception:
            name = concept
        self._concept_name_cache[concept] = name
        return name


class VampireSquidClient:
    """Client for vampire-squid video metadata endpoints.

    Args:
        endpoint: Raziel endpoint metadata for vampire-squid.
        session: Shared HTTP session for requests.
    """

    SERVICE_NAME = "vampire-squid"

    VIDEO_DATA = "/videoreferences"
    VIDEO_BY_VIDEO_REFERENCE_UUID = "/videos/videoreference"
    MEDIA_BY_VIDEO_REFERENCE_UUID = "/media/videoreference"
    MEDIA_BY_VIDEO_SEQUENCE_NAME = "/media/videosequence"
    ALL_VIDEO_SEQUENCE_NAMES = "/videosequences/names"

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

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        """Execute a request using the shared HTTP policy."""
        return request_with_policy(self._session, method, self._url(path), **kwargs)

    def get_video_data(self, video_reference_uuid: str) -> Dict[str, Any]:
        """Return video metadata for a video reference UUID.

        Args:
            video_reference_uuid: Video reference UUID.

        Returns:
            Parsed JSON payload.
        """
        response = self._request("get", self.VIDEO_DATA + "/" + video_reference_uuid)
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def get_video_by_video_reference_uuid(
        self, video_reference_uuid: str
    ) -> Dict[str, Any]:
        """Return video payload by reference UUID, normalizing list responses.

        Args:
            video_reference_uuid: Video reference UUID.

        Returns:
            Parsed JSON payload.
        """
        response = self._request(
            "get",
            self.VIDEO_BY_VIDEO_REFERENCE_UUID + "/" + video_reference_uuid,
        )
        response_parsed = response.json()
        if isinstance(response_parsed, list):
            return response_parsed[0] if response_parsed else {}
        return response_parsed if isinstance(response_parsed, dict) else {}

    def get_media_by_video_reference_uuid(
        self, video_reference_uuid: str
    ) -> Dict[str, Any]:
        """Return media payload by video reference UUID, normalizing list responses.

        Args:
            video_reference_uuid: Video reference UUID.

        Returns:
            Parsed JSON payload.
        """
        response = self._request(
            "get",
            self.MEDIA_BY_VIDEO_REFERENCE_UUID + "/" + video_reference_uuid,
        )
        response_parsed = response.json()
        if isinstance(response_parsed, list):
            return response_parsed[0] if response_parsed else {}
        return response_parsed if isinstance(response_parsed, dict) else {}

    def get_all_video_sequence_names(self) -> List[str]:
        """Return all video sequence names.

        Returns:
            Sorted list of video sequence name strings.
        """
        response = self._request("get", self.ALL_VIDEO_SEQUENCE_NAMES)
        payload = response.json()
        return payload if isinstance(payload, list) else []

    def get_media_by_video_sequence_name(
        self, video_sequence_name: str
    ) -> List[Dict[str, Any]]:
        """Return all media for a video sequence name.

        Args:
            video_sequence_name: Video sequence name.

        Returns:
            Parsed JSON payload list of Media objects.
        """
        response = self._request(
            "get",
            self.MEDIA_BY_VIDEO_SEQUENCE_NAME
            + "/"
            + quote(video_sequence_name, safe=""),
        )
        payload = response.json()
        return payload if isinstance(payload, list) else []
