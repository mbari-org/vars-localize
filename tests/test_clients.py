from __future__ import annotations

from typing import Any, Dict, List, Optional, cast

import pytest
import requests

from vars_localize.services import clients
from vars_localize.services.errors import (
    ServiceAuthError,
    ServiceRequestError,
    ServiceValidationError,
)


class FakeResponse:
    def __init__(
        self,
        status_code: int = 200,
        payload: Any = None,
        content: bytes = b"",
        raise_exc: Optional[Exception] = None,
    ):
        self.status_code = status_code
        self._payload = payload
        self.content = content
        self._raise_exc = raise_exc
        self.response = self

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self._raise_exc is not None:
            raise self._raise_exc
        if self.status_code >= 400:
            exc = requests.HTTPError(f"status={self.status_code}")
            exc.response = self
            raise exc


class FakeSession:
    def __init__(self):
        self.headers: Dict[str, str] = {}
        self._responses: Dict[str, List[Any]] = {
            "get": [],
            "post": [],
            "put": [],
            "delete": [],
        }
        self.calls: List[tuple[str, str, dict]] = []

    def push(self, method: str, value: Any):
        self._responses[method].append(value)

    def request(self, method: str, url: str, **kwargs):
        method = method.lower()
        self.calls.append((method, url, kwargs))
        if not self._responses[method]:
            raise AssertionError(f"No queued response for {method}")
        value = self._responses[method].pop(0)
        if isinstance(value, Exception):
            raise value
        return value


@pytest.fixture
def annosaurus_endpoint() -> Dict[str, Any]:
    return {"url": "https://annosaurus.example", "secret": "s3cr3t"}


@pytest.fixture
def fake_session(monkeypatch) -> FakeSession:
    session = FakeSession()
    monkeypatch.setattr(clients.requests, "Session", lambda: session)
    return session


def test_annosaurus_authenticate_success(annosaurus_endpoint, fake_session):
    fake_session.push("post", FakeResponse(payload={"access_token": "jwt-token"}))
    client = clients.AnnosaurusClient(annosaurus_endpoint)

    client.authenticate()
    assert fake_session.headers["Authorization"] == "BEARER jwt-token"


def test_annosaurus_authenticate_missing_token(annosaurus_endpoint, fake_session):
    fake_session.push("post", FakeResponse(payload={}))
    client = clients.AnnosaurusClient(annosaurus_endpoint)

    with pytest.raises(ServiceAuthError):
        client.authenticate()


def test_annosaurus_requires_auth(annosaurus_endpoint, fake_session):
    client = clients.AnnosaurusClient(annosaurus_endpoint)

    with pytest.raises(ServiceAuthError, match="Session must be authenticated"):
        client.get_imaged_moment_uuids("octopus")


def test_annosaurus_getters_success(annosaurus_endpoint, fake_session):
    fake_session.push("post", FakeResponse(payload={"access_token": "jwt"}))
    fake_session.push("get", FakeResponse(payload=["im-1", "im-2"]))
    fake_session.push("get", FakeResponse(payload={"uuid": "im-1"}))
    client = clients.AnnosaurusClient(annosaurus_endpoint)

    client.authenticate()
    assert client.get_imaged_moment_uuids("fish") == ["im-1", "im-2"]
    assert client.get_imaged_moment("im-1") == {"uuid": "im-1"}


def test_annosaurus_request_failure_raises_typed_error(
    annosaurus_endpoint, fake_session
):
    fake_session.push("post", FakeResponse(payload={"access_token": "jwt"}))
    fake_session.push("get", requests.ConnectionError("network down"))
    fake_session.push("get", requests.ConnectionError("network down"))
    fake_session.push("get", requests.ConnectionError("network down"))
    client = clients.AnnosaurusClient(annosaurus_endpoint)

    client.authenticate()
    with pytest.raises(ServiceRequestError):
        client.get_annotations_by_video_reference("vr-1")


def test_create_observation_validation_and_success(annosaurus_endpoint, fake_session):
    fake_session.push("post", FakeResponse(payload={"access_token": "jwt"}))
    fake_session.push("post", FakeResponse(payload={"observation_uuid": "obs-1"}))
    client = clients.AnnosaurusClient(annosaurus_endpoint)
    client.authenticate()

    with pytest.raises(ServiceValidationError):
        client.create_observation("vr", "fish", "u")

    payload = client.create_observation(
        "vr",
        "fish",
        "u",
        elapsed_time_millis=123,
    )
    assert payload["observation_uuid"] == "obs-1"


def test_box_lifecycle_success(annosaurus_endpoint, fake_session):
    fake_session.push("post", FakeResponse(payload={"access_token": "jwt"}))
    fake_session.push("post", FakeResponse(payload={"uuid": "assoc-1"}))
    fake_session.push("put", FakeResponse(payload={"uuid": "assoc-1", "updated": True}))
    fake_session.push("delete", FakeResponse(payload={"ok": True}))

    client = clients.AnnosaurusClient(annosaurus_endpoint)
    client.authenticate()

    created = client.create_box({"x": 1}, "obs-1", "fin")
    updated = client.modify_box({"x": 2}, "obs-1", "assoc-1")
    deleted = client.delete_box("assoc-1")

    assert created["uuid"] == "assoc-1"
    assert updated["updated"] is True
    assert deleted.status_code == 200


def test_oni_client_methods_and_caching():
    session = FakeSession()
    endpoint = {"url": "https://oni.example"}
    session.push("get", FakeResponse(payload=[{"name": "u1"}]))
    session.push("get", FakeResponse(payload=["fish", "jelly"]))
    session.push("get", FakeResponse(payload=[{"name": "arm"}, {"name": "fin"}]))
    client = clients.OniClient(endpoint, cast(Any, session))

    assert client.get_all_users() == [{"name": "u1"}]
    assert client.get_all_concepts() == ["fish", "jelly"]
    assert client.get_all_concepts() == ["fish", "jelly"]
    assert client.get_all_parts() == ["arm", "fin"]
    assert client.get_all_parts() == ["arm", "fin"]

    get_calls = [call for call in session.calls if call[0] == "get"]
    assert len(get_calls) == 3


def test_vampire_squid_methods_success():
    session = FakeSession()
    endpoint = {"url": "https://vampire.example"}
    session.push("get", FakeResponse(payload={"uuid": "vr-1"}))
    session.push("get", FakeResponse(payload=[{"uuid": "video-1"}]))
    session.push("get", FakeResponse(payload={"video_sequence_name": "dive-42"}))
    client = clients.VampireSquidClient(endpoint, cast(Any, session))

    assert client.get_video_data("vr-1") == {"uuid": "vr-1"}
    assert client.get_video_by_video_reference_uuid("vr-1") == {"uuid": "video-1"}
    assert client.get_media_by_video_reference_uuid("vr-1") == {
        "video_sequence_name": "dive-42"
    }
