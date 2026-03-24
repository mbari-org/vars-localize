from __future__ import annotations

import importlib
from typing import Any, Dict, List, Optional

import pytest
import requests

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

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self._raise_exc is not None:
            raise self._raise_exc
        if self.status_code >= 400:
            raise requests.HTTPError(f"status={self.status_code}")


class FakeSession:
    def __init__(self):
        self._responses: Dict[str, List[Any]] = {"get": []}
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


class StubClient:
    def __init__(self):
        self.called = []

    def __getattr__(self, item):
        def _fn(*args, **kwargs):
            self.called.append((item, args, kwargs))
            return (item, args, kwargs)

        return _fn


def test_check_connection_success_and_failure(monkeypatch):
    service = m3mod.M3Service("https://m3.example")
    session = FakeSession()
    session.push("get", FakeResponse(status_code=200))
    session.push("get", FakeResponse(status_code=503))
    session.push("get", requests.RequestException("down"))
    monkeypatch.setattr(service, "_default_session", session)

    service.check_connection()
    with pytest.raises(ConnectionError, match="M3 health check failed"):
        service.check_connection()
    with pytest.raises(ConnectionError, match="Connection check failed"):
        service.check_connection()


def test_fetch_endpoints_success(monkeypatch):
    service = m3mod.M3Service("https://m3.example")

    post_calls = []
    get_calls = []

    def fake_post(url, headers=None):
        post_calls.append((url, headers))
        return FakeResponse(status_code=200, payload={"accessToken": "abc"})

    def fake_get(url, headers=None):
        get_calls.append((url, headers))
        return FakeResponse(
            payload=[
                {
                    "name": "annosaurus",
                    "url": "https://anno",
                    "secret": "s",
                    "timeoutMillis": 1,
                    "proxyPath": "p",
                },
                {
                    "name": "oni",
                    "url": "https://oni",
                    "secret": "s",
                    "timeoutMillis": 1,
                    "proxyPath": "p",
                },
            ]
        )

    monkeypatch.setattr(m3mod.requests, "post", fake_post)
    monkeypatch.setattr(m3mod.requests, "get", fake_get)

    service._fetch_endpoints("u", "p")

    assert "annosaurus" in service._endpoints
    assert "oni" in service._endpoints
    assert post_calls and get_calls


def test_fetch_endpoints_auth_failure(monkeypatch):
    service = m3mod.M3Service("https://m3.example")

    def fake_post(url, headers=None):
        return FakeResponse(status_code=401, payload={"message": "denied"})

    monkeypatch.setattr(m3mod.requests, "post", fake_post)

    with pytest.raises(Exception, match="Failed to authenticate with Raziel"):
        service._fetch_endpoints("u", "p")


def test_get_and_find_endpoint_guards():
    service = m3mod.M3Service("https://m3.example")

    with pytest.raises(Exception, match="You must call configure"):
        service._get_endpoint("annosaurus")
    with pytest.raises(Exception, match="You must call configure"):
        service._find_endpoint("annosaurus")

    service._endpoints = {"annosaurus": {"url": "x"}}
    assert service._get_endpoint("annosaurus") == {"url": "x"}
    with pytest.raises(Exception, match="No endpoint named oni"):
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

        def __init__(self, endpoint):
            self.endpoint = endpoint

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


def test_configure_missing_oni(monkeypatch):
    service = m3mod.M3Service("https://m3.example")
    service._endpoints = {
        "annosaurus": {"url": "https://anno", "secret": "a"},
        "vampire-squid": {"url": "https://vs"},
    }
    monkeypatch.setattr(service, "_fetch_endpoints", lambda u, p: None)

    with pytest.raises(RuntimeError, match="No endpoint named oni"):
        service.configure("u", "p")


def test_configure_authentication_failure(monkeypatch):
    service = m3mod.M3Service("https://m3.example")
    service._endpoints = {
        "annosaurus": {"url": "https://anno", "secret": "a"},
        "oni": {"url": "https://oni"},
        "vampire-squid": {"url": "https://vs"},
    }
    monkeypatch.setattr(service, "_fetch_endpoints", lambda u, p: None)

    class FakeAnno:
        SERVICE_NAME = "annosaurus"

        def __init__(self, endpoint):
            self.endpoint = endpoint

        def authenticate(self):
            raise RuntimeError("bad auth")

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

    with pytest.raises(RuntimeError, match="bad auth"):
        service.configure("u", "p")


def test_require_clients_and_client_accessors():
    service = m3mod.M3Service("https://m3.example")

    with pytest.raises(Exception, match="Service must be configured"):
        service._require_clients()

    anno = StubClient()
    oni = StubClient()
    vs = StubClient()
    service._annosaurus = anno
    service._oni = oni
    service._vampire_squid = vs

    assert service._annosaurus_client() is anno
    assert service._oni_client() is oni
    assert service._vampire_squid_client() is vs


def test_m3service_delegates_to_clients():
    service = m3mod.M3Service("https://m3.example")
    anno = StubClient()
    oni = StubClient()
    vs = StubClient()
    service._annosaurus = anno
    service._oni = oni
    service._vampire_squid = vs

    assert service.get_all_users()[0] == "get_all_users"
    assert service.get_all_concepts()[0] == "get_all_concepts"
    assert service.get_imaged_moment_uuids("concept")[0] == "get_imaged_moment_uuids"
    assert service.get_imaged_moment("im-1")[0] == "get_imaged_moment"
    assert (
        service.get_imaged_moments_by_image_reference("img-1")[0]
        == "get_imaged_moments_by_image_reference"
    )
    assert (
        service.get_annotations_by_video_reference("vid-1")[0]
        == "get_annotations_by_video_reference"
    )
    assert service.delete_observation("obs-1")[0] == "delete_observation"
    assert (
        service.rename_observation("obs-1", "concept", "user")[0]
        == "rename_observation"
    )
    assert (
        service.create_observation("vid", "concept", "user", timecode="00")[0]
        == "create_observation"
    )
    assert service.create_box({"x": 1}, "obs-1", "part")[0] == "create_box"
    assert service.modify_box({"x": 2}, "obs-1", "assoc-1", "part")[0] == "modify_box"
    assert service.delete_box("assoc-1")[0] == "delete_box"
    assert service.get_all_parts()[0] == "get_all_parts"
    assert service.get_video_data("vr-1")[0] == "get_video_data"
    assert (
        service.get_video_by_video_reference_uuid("vr-1")[0]
        == "get_video_by_video_reference_uuid"
    )


def test_fetch_image_success_and_failure(monkeypatch):
    service = m3mod.M3Service("https://m3.example")
    session = FakeSession()
    session.push("get", FakeResponse(content=b"fake-image"))
    session.push("get", requests.RequestException("image failed"))
    monkeypatch.setattr(service, "_default_session", session)

    class FakePixmap:
        def __init__(self):
            self.loaded = None

        def loadFromData(self, data):
            self.loaded = data

    monkeypatch.setattr(m3mod, "QPixmap", FakePixmap)

    pixmap = service.fetch_image("https://img")
    assert isinstance(pixmap, FakePixmap)
    assert pixmap.loaded == b"fake-image"
    assert service.fetch_image("https://img") is None
