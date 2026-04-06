from vars_localize.services.SAM3Service import SAM3Service


def _fake_build_predictors(service):
    def _build(device: str, semantic_enabled: bool = True, point_enabled: bool = True):
        service._cleanup_predictors()
        service._semantic_predictor = object() if semantic_enabled else None
        service._point_predictor = object() if point_enabled else None
        service._predictor_ready = False
        service._device = device

    return _build


def test_ensure_loaded_semantic_only(monkeypatch):
    service = SAM3Service(model_path="/tmp/model.pt")

    monkeypatch.setattr(service, "_validate_model_path", lambda: None)
    monkeypatch.setattr(service, "_select_device", lambda: "cpu")
    monkeypatch.setattr(service, "_build_predictors", _fake_build_predictors(service))

    service.ensure_loaded(semantic_enabled=True, point_enabled=False)

    assert service.semantic_available is True
    assert service.point_available is False
    assert service.available is True


def test_ensure_loaded_point_only(monkeypatch):
    service = SAM3Service(model_path="/tmp/model.pt")

    monkeypatch.setattr(service, "_validate_model_path", lambda: None)
    monkeypatch.setattr(service, "_select_device", lambda: "cpu")
    monkeypatch.setattr(service, "_build_predictors", _fake_build_predictors(service))

    service.ensure_loaded(semantic_enabled=False, point_enabled=True)

    assert service.semantic_available is False
    assert service.point_available is True
    assert service.available is True


def test_ensure_loaded_with_no_modes_cleans_up(monkeypatch):
    service = SAM3Service(model_path="/tmp/model.pt")
    service._semantic_predictor = object()
    service._point_predictor = object()

    monkeypatch.setattr(service, "_validate_model_path", lambda: None)
    monkeypatch.setattr(service, "_select_device", lambda: "cpu")

    service.ensure_loaded(semantic_enabled=False, point_enabled=False)

    assert service.semantic_available is False
    assert service.point_available is False
    assert service.available is False
