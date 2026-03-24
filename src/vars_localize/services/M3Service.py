"""Service facade around M3 utility functions."""

import json
from typing import List, Optional

import requests
import requests.auth
from PyQt6.QtGui import QPixmap

from vars_localize.util import endpoints, utils


class BasicJWTAuth(requests.auth.AuthBase):
    def __init__(self, token: str):
        self.token = token

    def __call__(self, r):
        r.headers["Authorization"] = "BEARER " + self.token
        return r


class M3Service:
    """Instance-based service for M3 operations and HTTP session state."""

    def __init__(self, m3_url: str):
        self._m3_url = m3_url.rstrip("/")
        self._default_session = requests.Session()
        self._anno_session = requests.Session()
        self._kb_concepts = None
        self._kb_parts = None

    @property
    def m3_url(self) -> str:
        return self._m3_url

    def check_connection(self, timeout_secs: int = 3) -> bool:
        try:
            r = self._default_session.get(
                self._m3_url + "/health", timeout=max(1, int(timeout_secs))
            )
            return r.status_code == 200
        except requests.RequestException as e:
            utils.log(f"Connection check failed: {e}", level=2)
            return False

    def configure(self, username: str, password: str):
        endpoints.configure(self._m3_url, username, password)
        if not self.jwt_auth(self._anno_session, endpoints.Annosaurus):
            raise RuntimeError("Failed to authenticate with Annosaurus")

    def _require_anno_auth(self):
        if self._anno_session.auth is None:
            raise Exception("Session must be authenticated")

    def jwt_auth(
        self, session: requests.Session, endpoint: endpoints.ConfigEndpoint
    ) -> bool:
        try:
            response = session.post(
                endpoint.AUTH,
                headers={"Authorization": "APIKEY {}".format(endpoint.SECRET)},
            )
            response.raise_for_status()

            token = response.json()["access_token"]
            session.auth = BasicJWTAuth(token)
            return True
        except Exception as e:
            utils.log("Authentication failed.", level=2)
            utils.log(e, level=2)
            return False

    def get_all_users(self) -> list:
        response = self._default_session.get(endpoints.VARSUserServer.ALL_USERS)
        response.raise_for_status()
        return response.json()

    def get_all_concepts(self) -> List[str]:
        if self._kb_concepts is None:
            response = self._default_session.get(endpoints.VARSKBServer.ALL_CONCEPTS)
            response.raise_for_status()
            self._kb_concepts = response.json()
        return self._kb_concepts

    def get_imaged_moment_uuids(self, concept: str) -> List[str]:
        self._require_anno_auth()
        response = self._anno_session.get(
            endpoints.Annosaurus.IMAGED_MOMENTS_BY_CONCEPT + "/" + concept
        )
        return response.json()

    def get_imaged_moment(self, imaged_moment_uuid: str) -> dict:
        self._require_anno_auth()
        response = self._anno_session.get(
            endpoints.Annosaurus.IMAGED_MOMENT + "/" + imaged_moment_uuid
        )
        return response.json()

    def get_imaged_moments_by_image_reference(self, image_reference_uuid: str):
        try:
            response = self._default_session.get(
                endpoints.Annosaurus.IMAGED_MOMENTS_BY_IMAGE_REFERENCE
                + "/"
                + image_reference_uuid
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            utils.log(
                "Could not fetch imaged moment data for image reference {}".format(
                    image_reference_uuid
                ),
                level=1,
            )
            utils.log(e, level=1)

    def get_annotations_by_video_reference(self, video_reference_uuid: str):
        try:
            response = self._default_session.get(
                endpoints.Annosaurus.ANNOTATIONS_BY_VIDEO_REFERENCE
                + "/"
                + video_reference_uuid,
                params={"data": True},
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            utils.log(
                "Could not fetch annotation data for video reference {}".format(
                    video_reference_uuid
                ),
                level=1,
            )
            utils.log(e, level=1)

    def delete_observation(self, observation_uuid: str):
        self._require_anno_auth()
        try:
            response = self._anno_session.delete(
                endpoints.Annosaurus.DELETE_OBSERVATION + "/" + observation_uuid
            )
            response.raise_for_status()
            return response
        except Exception as e:
            utils.log("Observation deletion failed.", level=2)
            utils.log(e, level=2)

    def rename_observation(
        self, observation_uuid: str, new_concept: str, observer: str
    ):
        self._require_anno_auth()
        request_data = {"concept": new_concept, "observer": observer}
        try:
            response = self._anno_session.put(
                endpoints.Annosaurus.OBSERVATION + "/" + observation_uuid,
                data=request_data,
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            utils.log("Concept rename failed.", level=2)
            utils.log(e, level=2)

    def create_observation(
        self,
        video_reference_uuid,
        concept,
        observer,
        timecode=None,
        elapsed_time_millis=None,
        recorded_timestamp=None,
    ) -> Optional[dict]:
        self._require_anno_auth()
        request_data = {
            "video_reference_uuid": video_reference_uuid,
            "concept": concept,
            "observer": observer,
            "activity": "localize",
            "group": "ROV:training-set",
        }

        if not (timecode or elapsed_time_millis or recorded_timestamp):
            utils.log(
                "No observation index provided. Observation creation failed.", level=2
            )
            return None

        if timecode:
            request_data["timecode"] = timecode
        if elapsed_time_millis:
            request_data["elapsed_time_millis"] = int(elapsed_time_millis)
        if recorded_timestamp:
            request_data["recorded_timestamp"] = recorded_timestamp

        try:
            response = self._anno_session.post(
                endpoints.Annosaurus.OBSERVATION, data=request_data
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            utils.log("Observation creation failed.", level=2)
            utils.log(e, level=2)

    def create_box(
        self, box_json, observation_uuid: str, to_concept: Optional[str] = None
    ) -> Optional[dict]:
        self._require_anno_auth()
        request_data = {
            "observation_uuid": observation_uuid,
            "link_name": "bounding box",
            "link_value": json.dumps(box_json),
            "mime_type": "application/json",
        }

        if to_concept is not None:
            request_data["to_concept"] = to_concept

        try:
            response = self._anno_session.post(
                endpoints.Annosaurus.ASSOCIATION,
                data=request_data,
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            utils.log("Box creation failed.", level=2)
            utils.log(e, level=2)

    def modify_box(
        self,
        box_json,
        observation_uuid: str,
        association_uuid: str,
        to_concept: Optional[str] = None,
    ) -> Optional[dict]:
        self._require_anno_auth()
        request_data = {
            "observation_uuid": observation_uuid,
            "link_name": "bounding box",
            "link_value": json.dumps(box_json),
            "mime_type": "application/json",
        }

        if to_concept is not None:
            request_data["to_concept"] = to_concept

        try:
            response = self._anno_session.put(
                endpoints.Annosaurus.ASSOCIATION + "/" + association_uuid,
                data=request_data,
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            utils.log("Box modification failed.", level=2)
            utils.log(e, level=2)

    def delete_box(self, association_uuid: str):
        self._require_anno_auth()
        try:
            response = self._anno_session.delete(
                endpoints.Annosaurus.ASSOCIATION + "/" + association_uuid
            )
            response.raise_for_status()
            return response
        except Exception as e:
            utils.log("Box deletion failed.", level=2)
            utils.log(e, level=2)

    def fetch_image(self, url: str):
        try:
            response = self._default_session.get(url)
            response.raise_for_status()
            pixmap = QPixmap()
            pixmap.loadFromData(response.content)
            return pixmap
        except Exception:
            utils.log("Could not fetch image at {}".format(url), level=1)

    def get_all_parts(self) -> List[str]:
        if self._kb_parts is None:
            response = self._default_session.get(endpoints.VARSKBServer.ALL_PARTS)
            response.raise_for_status()
            self._kb_parts = [el["name"] for el in response.json()]
        return self._kb_parts

    def get_video_data(self, video_reference_uuid: str):
        try:
            response = self._default_session.get(
                endpoints.VampireSquid.VIDEO_DATA + "/" + video_reference_uuid
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            utils.log(
                "Could not fetch video data for {}".format(video_reference_uuid),
                level=1,
            )
            utils.log(e, level=1)

    def get_video_by_video_reference_uuid(self, video_reference_uuid: str):
        try:
            response = self._default_session.get(
                endpoints.VampireSquid.VIDEO_BY_VIDEO_REFERENCE_UUID
                + "/"
                + video_reference_uuid
            )
            response.raise_for_status()

            response_parsed = response.json()
            if isinstance(response_parsed, list):
                return response_parsed[0]

            return response_parsed
        except Exception as e:
            utils.log(
                "Could not fetch video data for video reference {}".format(
                    video_reference_uuid
                ),
                level=1,
            )
            utils.log(e, level=1)
