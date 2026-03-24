from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest
import requests

from vars_localize.services import clients


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

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self._raise_exc is not None:
            raise self._raise_exc
        if self.status_code >= 400:
            raise requests.HTTPError(f"status={self.status_code}")


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

    def _next(self, method: str):
        if not self._responses[method]:
            raise AssertionError(f"No queued response for {method}")
        value = self._responses[method].pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    def get(self, url: str, **kwargs):
        self.calls.append(("get", url, kwargs))
        return self._next("get")

    def post(self, url: str, **kwargs):
        self.calls.append(("post", url, kwargs))
        return self._next("post")

    def put(self, url: str, **kwargs):
        self.calls.append(("put", url, kwargs))
        return self._next("put")

    def delete(self, url: str, **kwargs):
        self.calls.append(("delete", url, kwargs))
        return self._next("delete")


@pytest.fixture
def annosaurus_endpoint() -> Dict[str, Any]:
    return {"url": "https://annosaurus.example", "secret": "s3cr3t"}


@pytest.fixture
def fake_session(monkeypatch) -> FakeSession:
    session = FakeSession()
    monkeypatch.setattr(clients.requests, "Session", lambda: session)
    return session


@pytest.fixture
def captured_logs(monkeypatch):
    logs: List[Any] = []

    monkeypatch.setattr(
        clients.logger,
        "warning",
        lambda *args, **kwargs: logs.append(("warning", args, kwargs)),
    )
    monkeypatch.setattr(
        clients.logger,
        "error",
        lambda *args, **kwargs: logs.append(("error", args, kwargs)),
    )
    monkeypatch.setattr(
        clients.logger,
        "exception",
        lambda *args, **kwargs: logs.append(("exception", args, kwargs)),
    )
    return logs


def test_annosaurus_authenticate_success(annosaurus_endpoint, fake_session):
    fake_session.push("post", FakeResponse(payload={"access_token": "jwt-token"}))
    client = clients.AnnosaurusClient(annosaurus_endpoint)

    client.authenticate()
    assert fake_session.headers["Authorization"] == "BEARER jwt-token"


def test_annosaurus_authenticate_failure_logs(
    annosaurus_endpoint, fake_session, captured_logs
):
    fake_session.push("post", requests.RequestException("boom"))
    client = clients.AnnosaurusClient(annosaurus_endpoint)

    with pytest.raises(RuntimeError, match="Failed to authenticate with Annosaurus"):
        client.authenticate()
    assert captured_logs


def test_annosaurus_requires_auth(annosaurus_endpoint, fake_session):
    client = clients.AnnosaurusClient(annosaurus_endpoint)

    with pytest.raises(Exception, match="Session must be authenticated"):
        client.get_imaged_moment_uuids("octopus")


def test_annosaurus_getters_success(annosaurus_endpoint, fake_session):
    fake_session.push("post", FakeResponse(payload={"access_token": "jwt"}))
    fake_session.push("get", FakeResponse(payload=["im-1", "im-2"]))
    fake_session.push("get", FakeResponse(payload={"uuid": "im-1"}))
    client = clients.AnnosaurusClient(annosaurus_endpoint)

    client.authenticate()
    assert client.get_imaged_moment_uuids("fish") == ["im-1", "im-2"]
    assert client.get_imaged_moment("im-1") == {"uuid": "im-1"}


def test_annosaurus_image_reference_and_video_reference_failure_logs(
    annosaurus_endpoint, fake_session, captured_logs
):
    fake_session.push("post", FakeResponse(payload={"access_token": "jwt"}))
    fake_session.push("get", requests.RequestException("bad image ref"))
    fake_session.push("get", requests.RequestException("bad video ref"))
    client = clients.AnnosaurusClient(annosaurus_endpoint)
    client.authenticate()
    assert client.get_imaged_moments_by_image_reference("img-ref") is None
    assert client.get_annotations_by_video_reference("vid-ref") is None
    assert len(captured_logs) >= 2


def test_annosaurus_image_reference_and_video_reference_success(
    annosaurus_endpoint, fake_session
):
    fake_session.push("post", FakeResponse(payload={"access_token": "jwt"}))
    fake_session.push("get", FakeResponse(payload=[{"uuid": "im-1"}]))
    fake_session.push("get", FakeResponse(payload=[{"uuid": "ann-1"}]))
    client = clients.AnnosaurusClient(annosaurus_endpoint)

    client.authenticate()
    assert client.get_imaged_moments_by_image_reference("img-ref") == [{"uuid": "im-1"}]
    assert client.get_annotations_by_video_reference("vid-ref") == [{"uuid": "ann-1"}]


def test_annosaurus_delete_observation_success_and_failure(
    annosaurus_endpoint, fake_session, captured_logs
):
    fake_session.push("post", FakeResponse(payload={"access_token": "jwt"}))
    ok_response = FakeResponse(payload={"ok": True})
    fake_session.push("delete", ok_response)
    fake_session.push("delete", requests.RequestException("cannot delete"))
    client = clients.AnnosaurusClient(annosaurus_endpoint)
    client.authenticate()
    assert client.delete_observation("obs-1") is ok_response
    assert client.delete_observation("obs-2") is None
    assert captured_logs


def test_annosaurus_rename_success_and_failure(
    annosaurus_endpoint, fake_session, captured_logs
):
    fake_session.push("post", FakeResponse(payload={"access_token": "jwt"}))
    fake_session.push(
        "put", FakeResponse(payload={"uuid": "obs-1", "concept": "shark"})
    )
    fake_session.push("put", requests.RequestException("rename failed"))
    client = clients.AnnosaurusClient(annosaurus_endpoint)
    client.authenticate()
    assert client.rename_observation("obs-1", "shark", "u1") == {
        "uuid": "obs-1",
        "concept": "shark",
    }
    assert client.rename_observation("obs-1", "ray", "u1") is None
    assert captured_logs


def test_annosaurus_create_observation_no_index_short_circuits(
    annosaurus_endpoint, fake_session
):
    fake_session.push("post", FakeResponse(payload={"access_token": "jwt"}))
    client = clients.AnnosaurusClient(annosaurus_endpoint)

    client.authenticate()
    assert client.create_observation("vid", "fish", "u1") is None
    # Only auth call was made.
    assert len(fake_session.calls) == 1


def test_annosaurus_create_observation_success_paths(annosaurus_endpoint, fake_session):
    fake_session.push("post", FakeResponse(payload={"access_token": "jwt"}))
    fake_session.push("post", FakeResponse(payload={"uuid": "obs-timecode"}))
    fake_session.push("post", FakeResponse(payload={"uuid": "obs-elapsed"}))
    fake_session.push("post", FakeResponse(payload={"uuid": "obs-recorded"}))
    client = clients.AnnosaurusClient(annosaurus_endpoint)

    client.authenticate()

    res1 = client.create_observation("vid", "fish", "u1", timecode="01:02:03:04")
    res2 = client.create_observation("vid", "fish", "u1", elapsed_time_millis=123)
    res3 = client.create_observation(
        "vid", "fish", "u1", recorded_timestamp="2026-01-01T00:00:00Z"
    )

    assert res1 == {"uuid": "obs-timecode"}
    assert res2 == {"uuid": "obs-elapsed"}
    assert res3 == {"uuid": "obs-recorded"}


def test_annosaurus_create_observation_failure_logs(
    annosaurus_endpoint, fake_session, captured_logs
):
    fake_session.push("post", FakeResponse(payload={"access_token": "jwt"}))
    fake_session.push("post", requests.RequestException("create failed"))
    client = clients.AnnosaurusClient(annosaurus_endpoint)
    client.authenticate()
    assert (
        client.create_observation("vid", "fish", "u1", timecode="00:00:00:01") is None
    )
    assert captured_logs


def test_annosaurus_box_lifecycle_success_and_failure(
    annosaurus_endpoint, fake_session, captured_logs
):
    fake_session.push("post", FakeResponse(payload={"access_token": "jwt"}))
    fake_session.push("post", FakeResponse(payload={"uuid": "assoc-1"}))
    fake_session.push("put", FakeResponse(payload={"uuid": "assoc-1", "updated": True}))
    ok_delete = FakeResponse(payload={"ok": True})
    fake_session.push("delete", ok_delete)
    fake_session.push("post", requests.RequestException("create box failed"))
    fake_session.push("put", requests.RequestException("modify box failed"))
    fake_session.push("delete", requests.RequestException("delete box failed"))

    client = clients.AnnosaurusClient(annosaurus_endpoint)
    client.authenticate()

    assert client.create_box({"x": 1}, "obs-1", "fin") == {"uuid": "assoc-1"}
    assert client.modify_box({"x": 2}, "obs-1", "assoc-1") == {
        "uuid": "assoc-1",
        "updated": True,
    }
    assert client.delete_box("assoc-1") is ok_delete

    assert client.create_box({"x": 1}, "obs-1") is None
    assert client.modify_box({"x": 2}, "obs-1", "assoc-1") is None
    assert client.delete_box("assoc-1") is None
    assert captured_logs


def test_oni_client_methods_and_caching():
    session = FakeSession()
    endpoint = {"url": "https://oni.example"}
    session.push("get", FakeResponse(payload=[{"name": "u1"}]))
    session.push("get", FakeResponse(payload=["fish", "jelly"]))
    session.push("get", FakeResponse(payload=[{"name": "arm"}, {"name": "fin"}]))
    client = clients.OniClient(endpoint, session)

    assert client.get_all_users() == [{"name": "u1"}]
    assert client.get_all_concepts() == ["fish", "jelly"]
    assert client.get_all_concepts() == ["fish", "jelly"]
    assert client.get_all_parts() == ["arm", "fin"]
    assert client.get_all_parts() == ["arm", "fin"]

    get_calls = [call for call in session.calls if call[0] == "get"]
    assert len(get_calls) == 3


def test_vampire_squid_video_methods_success_failure(captured_logs):
    session = FakeSession()
    endpoint = {"url": "https://vampire.example"}
    session.push("get", FakeResponse(payload={"uuid": "vr-1"}))
    session.push("get", requests.RequestException("video_data failed"))
    session.push("get", FakeResponse(payload=[{"uuid": "video-1"}]))
    session.push("get", FakeResponse(payload={"uuid": "video-2"}))
    session.push("get", requests.RequestException("video lookup failed"))

    client = clients.VampireSquidClient(endpoint, session)
    assert client.get_video_data("vr-1") == {"uuid": "vr-1"}
    assert client.get_video_data("vr-2") is None
    assert client.get_video_by_video_reference_uuid("vr-1") == {"uuid": "video-1"}
    assert client.get_video_by_video_reference_uuid("vr-2") == {"uuid": "video-2"}
    assert client.get_video_by_video_reference_uuid("vr-3") is None
    assert captured_logs
