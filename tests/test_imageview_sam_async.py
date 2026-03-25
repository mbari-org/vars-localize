from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("PyQt6")


def test_set_sam_assist_enabled_transitions(monkeypatch):
    from vars_localize.ui.ImageView import ImageView

    calls = {"clear": 0, "start": 0, "notify": 0, "redraw": 0}

    view = ImageView.__new__(ImageView)
    view.sam3_service = SimpleNamespace(available=True)
    view._sam_assist_enabled = False
    view._clear_sam_state = lambda reset_embedding=True: calls.__setitem__(
        "clear", calls["clear"] + 1
    )
    view._maybe_start_sam_embedding = lambda: calls.__setitem__(
        "start", calls["start"] + 1
    )
    view._notify_sam_status = lambda _: calls.__setitem__("notify", calls["notify"] + 1)
    view._build_sam_status = lambda: "status"
    view.redraw = lambda: calls.__setitem__("redraw", calls["redraw"] + 1)

    view.set_sam_assist_enabled(True)
    assert view._sam_assist_enabled is True
    assert calls["start"] == 1

    view.set_sam_assist_enabled(False)
    assert view._sam_assist_enabled is False
    assert calls["clear"] == 1
    assert calls["notify"] == 2
    assert calls["redraw"] == 2


def test_clear_sam_state_resets_runtime_fields():
    from vars_localize.ui.ImageView import ImageView

    view = ImageView.__new__(ImageView)
    view._sam_candidate_boxes = [1, 2]
    view._sam_candidate_index = 1
    view._sam_candidate_observation_uuid = "obs"
    view._sam_pending_observation_uuid = "obs2"
    view._sam_hover_box = object()
    view._sam_hover_inflight = True
    view._sam_last_hover_point = object()
    view._sam_ready_image_uuid = "im"
    view._sam_embedding_request_uuid = "im"
    view._notify_sam_candidate_state = lambda: None
    view._build_sam_status = lambda: "status"
    view._notify_sam_status = lambda _: None

    view._clear_sam_state(reset_embedding=True)

    assert view._sam_candidate_boxes == []
    assert view._sam_candidate_index == 0
    assert view._sam_candidate_observation_uuid is None
    assert view._sam_pending_observation_uuid is None
    assert view._sam_hover_box is None
    assert view._sam_hover_inflight is False
    assert view._sam_last_hover_point is None
    assert view._sam_ready_image_uuid is None
    assert view._sam_embedding_request_uuid is None
