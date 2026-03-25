from __future__ import annotations

from typing import Any, Dict, List, Optional, cast

import importlib

import pytest
import requests

from vars_localize.services.errors import (
    ServiceAuthError,
    ServiceNotConfiguredError,
    ServiceRequestError,
)

m3mod = importlib.import_module("vars_localize.services.M3Service")


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


class StubClient:
    def __init__(self):
        self.called = []

    def __getattr__(self, item):
        def _fn(*args, **kwargs):
            self.called.append((item, args, kwargs))
            return (item, args, kwargs)

        return _fn


class StubAnnoClient:
    def __init__(self):
        self.called = []

    def get_imaged_moment_uuids(self, concept: str):
        self.called.append("get_imaged_moment_uuids")
        return ["id-1"]

    def get_imaged_moment(self, im_uuid: str):
        self.called.append("get_imaged_moment")
        return {"uuid": im_uuid}

    def get_imaged_moments_by_image_reference(self, image_reference_uuid: str):
        self.called.append("get_imaged_moments_by_image_reference")
        return [{"imaged_moment_uuid": "im-1"}]

    def get_annotations_by_video_reference(self, video_reference_uuid: str):
        self.called.append("get_annotations_by_video_reference")
        return [{"imaged_moment_uuid": "im-1"}]

    def delete_observation(self, observation_uuid: str):
        self.called.append("delete_observation")
        return FakeResponse(payload={"ok": True})

    def rename_observation(
        self, observation_uuid: str, new_concept: str, observer: str
    ):
        self.called.append("rename_observation")
        return {"uuid": observation_uuid, "concept": new_concept}

    def create_observation(self, *args, **kwargs):
        self.called.append("create_observation")
        return {"observation_uuid": "obs-1"}

    def create_box(self, *args, **kwargs):
        self.called.append("create_box")
        return {"uuid": "assoc-1"}

    def modify_box(self, *args, **kwargs):
        self.called.append("modify_box")
        return {"uuid": "assoc-1"}

    def delete_box(self, association_uuid: str):
        self.called.append("delete_box")
        return FakeResponse(payload={"ok": True})


class StubOniClient:
    def get_all_users(self):
        return [{"username": "u"}]

    def get_all_concepts(self):
        return ["fish"]

    def get_all_parts(self):
        return ["self"]


class StubVsClient:
    def get_video_data(self, video_reference_uuid: str):
        return {"uuid": video_reference_uuid}

    def get_video_by_video_reference_uuid(self, video_reference_uuid: str):
        return {"uuid": video_reference_uuid}

    def get_media_by_video_reference_uuid(self, video_reference_uuid: str):
        return {
            "video_reference_uuid": video_reference_uuid,
            "video_sequence_name": "seq-{}".format(video_reference_uuid),
        }


def test_check_connection_success_and_failure(monkeypatch):
    service = m3mod.M3Service("https://m3.example")
    session = FakeSession()
    session.push("get", FakeResponse(status_code=200))
    session.push("get", FakeResponse(status_code=503))
    session.push("get", FakeResponse(status_code=503))
    session.push("get", FakeResponse(status_code=503))
    monkeypatch.setattr(service, "_default_session", session)

    service.check_connection()
    with pytest.raises(ServiceRequestError):
        service.check_connection()


def test_fetch_endpoints_success(monkeypatch):
    service = m3mod.M3Service("https://m3.example")
    session = FakeSession()
    session.push("post", FakeResponse(status_code=200, payload={"accessToken": "abc"}))
    session.push(
        "get",
        FakeResponse(
            payload=[
                {"name": "annosaurus", "url": "https://anno", "secret": "s"},
                {"name": "oni", "url": "https://oni", "secret": "s"},
            ]
        ),
    )
    monkeypatch.setattr(service, "_default_session", session)

    service._fetch_endpoints("u", "p")
    assert service._endpoints is not None
    assert "annosaurus" in service._endpoints
    assert "oni" in service._endpoints


def test_fetch_endpoints_auth_failure(monkeypatch):
    service = m3mod.M3Service("https://m3.example")
    session = FakeSession()
    session.push("post", FakeResponse(payload={}))
    monkeypatch.setattr(service, "_default_session", session)

    with pytest.raises(ServiceAuthError):
        service._fetch_endpoints("u", "p")


def test_get_and_find_endpoint_guards():
    service = m3mod.M3Service("https://m3.example")

    with pytest.raises(ServiceNotConfiguredError):
        service._get_endpoint("annosaurus")
    with pytest.raises(ServiceNotConfiguredError):
        service._find_endpoint("annosaurus")

    service._endpoints = {"annosaurus": {"url": "x"}}
    assert service._get_endpoint("annosaurus") == {"url": "x"}
    with pytest.raises(ServiceNotConfiguredError):
        service._get_endpoint("oni")
    assert service._find_endpoint("missing", "annosaurus") == {"url": "x"}
    assert service._find_endpoint("missing") is None


def test_configure_success(monkeypatch):
    service = m3mod.M3Service("https://m3.example")

    service._endpoints = {
        "annosaurus": {"url": "https://anno", "secret": "a"},
        "oni": {"url": "https://oni"},
        "vampire-squid": {"url": "https://vs"},
    }
    monkeypatch.setattr(service, "_fetch_endpoints", lambda u, p: None)

    class FakeAnno:
        SERVICE_NAME = "annosaurus"

        def __init__(self, endpoint, session=None):
            self.endpoint = endpoint
            self.session = session

        def authenticate(self):
            return True

    class FakeOni:
        SERVICE_NAME = "oni"

        def __init__(self, endpoint, session):
            self.endpoint = endpoint
            self.session = session

    class FakeVS:
        SERVICE_NAME = "vampire-squid"

        def __init__(self, endpoint, session):
            self.endpoint = endpoint
            self.session = session

    monkeypatch.setattr(m3mod, "AnnosaurusClient", FakeAnno)
    monkeypatch.setattr(m3mod, "OniClient", FakeOni)
    monkeypatch.setattr(m3mod, "VampireSquidClient", FakeVS)

    service.configure("u", "p")

    assert isinstance(service._annosaurus, FakeAnno)
    assert isinstance(service._oni, FakeOni)
    assert isinstance(service._vampire_squid, FakeVS)


def test_require_clients_and_accessors():
    service = m3mod.M3Service("https://m3.example")

    with pytest.raises(ServiceNotConfiguredError):
        service._require_clients()

    anno = StubClient()
    oni = StubClient()
    vs = StubClient()
    service._annosaurus = cast(Any, anno)
    service._oni = cast(Any, oni)
    service._vampire_squid = cast(Any, vs)

    assert service._annosaurus_client() is anno
    assert service._oni_client() is oni
    assert service._vampire_squid_client() is vs


def test_m3service_delegates_to_clients():
    service = m3mod.M3Service("https://m3.example")
    anno = StubAnnoClient()
    oni = StubOniClient()
    vs = StubVsClient()
    service._annosaurus = cast(Any, anno)
    service._oni = cast(Any, oni)
    service._vampire_squid = cast(Any, vs)

    assert service.get_all_users() == [{"username": "u"}]
    assert service.get_all_concepts() == ["fish"]
    assert service.get_imaged_moment_uuids("concept") == ["id-1"]
    assert service.get_imaged_moment("im-1") == {"uuid": "im-1"}
    assert service.get_imaged_moments_by_image_reference("img-1") == [
        {"imaged_moment_uuid": "im-1"}
    ]
    assert service.get_annotations_by_video_reference("vid-1") == [
        {"imaged_moment_uuid": "im-1"}
    ]
    assert service.delete_observation("obs-1").status_code == 200
    assert service.rename_observation("obs-1", "concept", "user") == {
        "uuid": "obs-1",
        "concept": "concept",
    }
    assert service.create_observation("vid", "concept", "user", timecode="00") == {
        "observation_uuid": "obs-1"
    }
    assert service.create_box({"x": 1}, "obs-1", "part") == {"uuid": "assoc-1"}
    assert service.modify_box({"x": 2}, "obs-1", "assoc-1", "part") == {
        "uuid": "assoc-1"
    }
    assert service.delete_box("assoc-1").status_code == 200
    assert service.get_all_parts() == ["self"]
    assert service.get_video_data("vr-1") == {"uuid": "vr-1"}
    assert service.get_video_by_video_reference_uuid("vr-1") == {"uuid": "vr-1"}
    assert service.get_media_by_video_reference_uuid("vr-1") == {
        "video_reference_uuid": "vr-1",
        "video_sequence_name": "seq-vr-1",
    }


def test_get_media_by_video_reference_uuid_uses_cache():
    service = m3mod.M3Service("https://m3.example")

    class CountingVsClient:
        def __init__(self):
            self.calls = 0

        def get_media_by_video_reference_uuid(self, video_reference_uuid: str):
            self.calls += 1
            return {
                "video_reference_uuid": video_reference_uuid,
                "video_sequence_name": "seq-{}".format(video_reference_uuid),
            }

    vs = CountingVsClient()
    service._annosaurus = cast(Any, StubAnnoClient())
    service._oni = cast(Any, StubOniClient())
    service._vampire_squid = cast(Any, vs)

    first = service.get_media_by_video_reference_uuid("vr-1")
    second = service.get_media_by_video_reference_uuid("vr-1")

    assert first == second
    assert vs.calls == 1


def test_fetch_image_bytes_success_and_failure(monkeypatch):
    service = m3mod.M3Service("https://m3.example")
    session = FakeSession()
    session.push("get", FakeResponse(content=b"fake-image"))
    session.push("get", requests.ConnectionError("image failed"))
    session.push("get", requests.ConnectionError("image failed"))
    session.push("get", requests.ConnectionError("image failed"))
    monkeypatch.setattr(service, "_default_session", session)

    assert service.fetch_image_bytes("https://img") == b"fake-image"
    with pytest.raises(ServiceRequestError):
        service.fetch_image_bytes("https://img")
