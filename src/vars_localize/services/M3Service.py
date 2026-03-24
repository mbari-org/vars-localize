"""Service facade around M3 utility functions."""

from base64 import b64encode
from typing import Any, Dict, List, Optional

import requests
from PyQt6.QtGui import QPixmap

from vars_localize.services.clients import (
    AnnosaurusClient,
    OniClient,
    VampireSquidClient,
)
from vars_localize.util.logging import get_logger

DEFAULT_M3_URL = "https://m3.shore.mbari.org/config"
logger = get_logger("M3Service")


class M3Service:
    """Compatibility facade over service-specific API clients.

    This class owns:
    - Raziel authentication and endpoint discovery
    - Client construction and lifecycle
    - Legacy method names used by existing UI/service callers

    Args:
        m3_url: M3 Raziel base URL.
    """

    def __init__(self, m3_url: str):
        """Create an orchestrator bound to an M3 config server URL.

        Args:
            m3_url: M3 Raziel base URL.
        """
        self._m3_url = m3_url.rstrip("/")
        self._default_session = requests.Session()
        self._endpoints: Optional[Dict[str, Dict[str, Any]]] = None
        self._annosaurus: Optional[AnnosaurusClient] = None
        self._oni: Optional[OniClient] = None
        self._vampire_squid: Optional[VampireSquidClient] = None

    @property
    def m3_url(self) -> str:
        """Return the configured M3 config service URL.

        Returns:
            M3 Raziel base URL.
        """
        return self._m3_url

    def check_connection(self, timeout_secs: int = 3) -> None:
        """Ensure the M3 config service responds to /health.

        Args:
            timeout_secs: Timeout in seconds.

        Raises:
            ConnectionError: If the health check fails or returns a non-200 response.
        """
        try:
            r = self._default_session.get(
                self._m3_url + "/health", timeout=max(1, int(timeout_secs))
            )
            if r.status_code != 200:
                raise ConnectionError(
                    "M3 health check failed with status code {}.".format(r.status_code)
                )
        except requests.RequestException as e:
            raise ConnectionError("Connection check failed: {}".format(e)) from e

    def _fetch_endpoints(self, username: str, password: str) -> None:
        """Authenticate with Raziel and populate endpoint metadata.

        Args:
            username: Raziel username.
            password: Raziel password.

        Raises:
            Exception: If Raziel authentication fails.
        """
        # Raziel expects HTTP Basic credentials for the auth token request.
        user_pass_base64 = "Basic " + b64encode(
            "{}:{}".format(username, password).encode("utf-8")
        ).decode("utf-8")

        res = requests.post(
            self._m3_url + "/auth", headers={"Authorization": user_pass_base64}
        )
        if res.status_code != 200:
            raise Exception(
                "Failed to authenticate with Raziel (code {}): {}".format(
                    res.status_code, res.json()["message"]
                )
            )

        token = res.json()["accessToken"]
        self._endpoints = {
            endpoint["name"]: endpoint
            for endpoint in requests.get(
                self._m3_url + "/endpoints",
                headers={"Authorization": "Bearer " + token},
            ).json()
        }

    def _get_endpoint(self, name: str) -> Dict[str, Any]:
        """Return a required endpoint by name.

        Args:
            name: Endpoint key.

        Returns:
            Endpoint metadata.

        Raises:
            Exception: If service is not configured or endpoint is missing.
        """
        if self._endpoints is None:
            raise Exception("You must call configure() before accessing endpoints.")
        if name not in self._endpoints:
            raise Exception("No endpoint named {}".format(name))
        return self._endpoints[name]

    def _find_endpoint(self, *names: str) -> Optional[Dict[str, Any]]:
        """Return the first configured endpoint from a list of names.

        Args:
            *names: Candidate endpoint keys in search order.

        Returns:
            Endpoint metadata for the first match, else None.

        Raises:
            Exception: If service is not configured.
        """
        if self._endpoints is None:
            raise Exception("You must call configure() before accessing endpoints.")
        for name in names:
            endpoint = self._endpoints.get(name)
            if endpoint is not None:
                return endpoint
        return None

    def configure(self, username: str, password: str) -> None:
        """Configure and authenticate all backing clients.

        Args:
            username: Raziel username.
            password: Raziel password.

        Raises:
            RuntimeError: If required endpoints are missing or auth fails.
        """
        self._fetch_endpoints(username, password)

        annosaurus_endpoint = self._get_endpoint(AnnosaurusClient.SERVICE_NAME)
        oni_endpoint = self._find_endpoint(OniClient.SERVICE_NAME)
        if oni_endpoint is None:
            raise RuntimeError("No endpoint named oni")
        vampire_squid_endpoint = self._get_endpoint(VampireSquidClient.SERVICE_NAME)

        self._annosaurus = AnnosaurusClient(annosaurus_endpoint)
        self._oni = OniClient(oni_endpoint, self._default_session)
        self._vampire_squid = VampireSquidClient(
            vampire_squid_endpoint, self._default_session
        )

        self._annosaurus.authenticate()

    def _require_clients(self) -> None:
        """Ensure configure() has been completed before API usage.

        Raises:
            Exception: If clients are not initialized.
        """
        if self._annosaurus is None or self._oni is None or self._vampire_squid is None:
            raise Exception("Service must be configured")

    def _annosaurus_client(self) -> AnnosaurusClient:
        """Return configured annosaurus client.

        Returns:
            Configured AnnosaurusClient.
        """
        self._require_clients()
        assert self._annosaurus is not None
        return self._annosaurus

    def _oni_client(self) -> OniClient:
        """Return configured oni client.

        Returns:
            Configured OniClient.
        """
        self._require_clients()
        assert self._oni is not None
        return self._oni

    def _vampire_squid_client(self) -> VampireSquidClient:
        """Return configured vampire-squid client.

        Returns:
            Configured VampireSquidClient.
        """
        self._require_clients()
        assert self._vampire_squid is not None
        return self._vampire_squid

    def get_all_users(self) -> List[Dict[str, Any]]:
        """Compatibility wrapper for OniClient.get_all_users.

        Returns:
            User records.
        """
        return self._oni_client().get_all_users()

    def get_all_concepts(self) -> List[str]:
        """Compatibility wrapper for OniClient.get_all_concepts.

        Returns:
            Concept names.
        """
        return self._oni_client().get_all_concepts()

    def get_imaged_moment_uuids(self, concept: str) -> List[str]:
        """Compatibility wrapper for AnnosaurusClient.get_imaged_moment_uuids.

        Args:
            concept: Concept name.

        Returns:
            Imaged moment UUIDs.
        """
        return self._annosaurus_client().get_imaged_moment_uuids(concept)

    def get_imaged_moment(self, imaged_moment_uuid: str) -> Dict[str, Any]:
        """Compatibility wrapper for AnnosaurusClient.get_imaged_moment.

        Args:
            imaged_moment_uuid: Imaged moment UUID.

        Returns:
            Imaged moment payload.
        """
        return self._annosaurus_client().get_imaged_moment(imaged_moment_uuid)

    def get_imaged_moments_by_image_reference(
        self, image_reference_uuid: str
    ) -> Optional[Any]:
        """Compatibility wrapper for image-reference lookup.

        Args:
            image_reference_uuid: Image reference UUID.

        Returns:
            Parsed payload or None when downstream call fails.
        """
        return self._annosaurus_client().get_imaged_moments_by_image_reference(
            image_reference_uuid
        )

    def get_annotations_by_video_reference(
        self, video_reference_uuid: str
    ) -> Optional[Any]:
        """Compatibility wrapper for video-reference annotation lookup.

        Args:
            video_reference_uuid: Video reference UUID.

        Returns:
            Parsed payload or None when downstream call fails.
        """
        return self._annosaurus_client().get_annotations_by_video_reference(
            video_reference_uuid
        )

    def delete_observation(self, observation_uuid: str) -> Optional[requests.Response]:
        """Compatibility wrapper for observation deletion.

        Args:
            observation_uuid: Observation UUID.

        Returns:
            Response on success, else None.
        """
        return self._annosaurus_client().delete_observation(observation_uuid)

    def rename_observation(
        self, observation_uuid: str, new_concept: str, observer: str
    ) -> Optional[Dict[str, Any]]:
        """Compatibility wrapper for observation rename.

        Args:
            observation_uuid: Observation UUID.
            new_concept: New concept name.
            observer: Observer identifier.

        Returns:
            Parsed payload or None.
        """
        return self._annosaurus_client().rename_observation(
            observation_uuid, new_concept, observer
        )

    def create_observation(
        self,
        video_reference_uuid: str,
        concept: str,
        observer: str,
        timecode: Optional[str] = None,
        elapsed_time_millis: Optional[int] = None,
        recorded_timestamp: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Compatibility wrapper for observation creation.

        Args:
            video_reference_uuid: Video reference UUID.
            concept: Concept name.
            observer: Observer identifier.
            timecode: Optional SMPTE-like timecode.
            elapsed_time_millis: Optional elapsed time in milliseconds.
            recorded_timestamp: Optional recorded timestamp.

        Returns:
            Parsed payload or None.
        """
        return self._annosaurus_client().create_observation(
            video_reference_uuid,
            concept,
            observer,
            timecode,
            elapsed_time_millis,
            recorded_timestamp,
        )

    def create_box(
        self,
        box_json: Dict[str, Any],
        observation_uuid: str,
        to_concept: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Compatibility wrapper for bounding-box creation.

        Args:
            box_json: Bounding box payload.
            observation_uuid: Observation UUID.
            to_concept: Optional target concept.

        Returns:
            Parsed payload or None.
        """
        return self._annosaurus_client().create_box(
            box_json, observation_uuid, to_concept
        )

    def modify_box(
        self,
        box_json: Dict[str, Any],
        observation_uuid: str,
        association_uuid: str,
        to_concept: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Compatibility wrapper for bounding-box modification.

        Args:
            box_json: Bounding box payload.
            observation_uuid: Observation UUID.
            association_uuid: Association UUID.
            to_concept: Optional target concept.

        Returns:
            Parsed payload or None.
        """
        return self._annosaurus_client().modify_box(
            box_json, observation_uuid, association_uuid, to_concept
        )

    def delete_box(self, association_uuid: str) -> Optional[requests.Response]:
        """Compatibility wrapper for bounding-box deletion.

        Args:
            association_uuid: Association UUID.

        Returns:
            Response on success, else None.
        """
        return self._annosaurus_client().delete_box(association_uuid)

    def fetch_image(self, url: str) -> Optional[QPixmap]:
        """Fetch an image URL and convert it into a QPixmap.

        Args:
            url: Image URL.

        Returns:
            QPixmap on success, else None.
        """
        try:
            response = self._default_session.get(url)
            response.raise_for_status()
            pixmap = QPixmap()
            pixmap.loadFromData(response.content)
            return pixmap
        except Exception:
            logger.warning("Could not fetch image at {}", url)

    def get_all_parts(self) -> List[str]:
        """Compatibility wrapper for OniClient.get_all_parts.

        Returns:
            Organism part names.
        """
        return self._oni_client().get_all_parts()

    def get_video_data(self, video_reference_uuid: str) -> Optional[Any]:
        """Compatibility wrapper for VampireSquidClient.get_video_data.

        Args:
            video_reference_uuid: Video reference UUID.

        Returns:
            Parsed payload or None.
        """
        return self._vampire_squid_client().get_video_data(video_reference_uuid)

    def get_video_by_video_reference_uuid(
        self, video_reference_uuid: str
    ) -> Optional[Any]:
        """Compatibility wrapper for VampireSquidClient.get_video_by_video_reference_uuid.

        Args:
            video_reference_uuid: Video reference UUID.

        Returns:
            Parsed payload or None.
        """
        return self._vampire_squid_client().get_video_by_video_reference_uuid(
            video_reference_uuid
        )
