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
    view._sam_candidate_concept = "fish"
    view._sam_pending_concept = "sponge"
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
    assert view._sam_candidate_concept is None
    assert view._sam_pending_concept is None
    assert view._sam_hover_box is None
    assert view._sam_hover_inflight is False
    assert view._sam_last_hover_point is None
    assert view._sam_ready_image_uuid is None
    assert view._sam_embedding_request_uuid is None


def test_handle_new_box_rejects_second_box_for_observation():
    from vars_localize.ui.BoundingBox import SourceBoundingBox
    from vars_localize.ui.ImageView import ImageView

    view = ImageView.__new__(ImageView)
    observation = SimpleNamespace(
        uuid="obs-1",
        associations=[SimpleNamespace(link_name="bounding box", uuid="assoc-1")],
        boxes=[object()],
        video_boxes=[],
    )
    view.observation_uuid = "obs-1"
    view.observation_map = {
        "obs-1": SimpleNamespace(observation=observation),
    }
    view.reload_moment = lambda: None
    view._m3_create_box = lambda *_args, **_kwargs: {"uuid": "assoc-new"}

    box = SourceBoundingBox(
        {
            "x": 10,
            "y": 20,
            "width": 30,
            "height": 40,
            "image_reference_uuid": "img-1",
        },
        label="fish",
        observer="tester",
        part="self",
    )

    with pytest.raises(ValueError, match="already has a bounding box association"):
        view.handle_new_box(box)


def test_delete_last_owned_box_prompts_to_delete_observation(monkeypatch):
    from vars_localize.ui.BoundingBox import SourceBoundingBox
    from vars_localize.ui.ImageView import ImageView
    from PyQt6.QtWidgets import QMessageBox

    view = ImageView.__new__(ImageView)
    box = SourceBoundingBox(
        {
            "x": 10,
            "y": 20,
            "width": 30,
            "height": 40,
            "image_reference_uuid": "img-1",
        },
        label="fish",
        observer="tester",
        observation_uuid="obs-1",
        association_uuid="assoc-1",
        part="self",
    )

    observation = SimpleNamespace(
        uuid="obs-1",
        associations=[SimpleNamespace(link_name="bounding box", uuid="assoc-1")],
        boxes=[box],
        video_boxes=[],
    )
    view.observation_map = {
        "obs-1": SimpleNamespace(observation=observation),
    }

    calls = {"delete_box": 0, "delete_observation": 0, "reload": 0}
    view._m3_delete_box = lambda _assoc_uuid: calls.__setitem__(
        "delete_box", calls["delete_box"] + 1
    )
    view._m3_delete_observation = lambda _obs_uuid: calls.__setitem__(
        "delete_observation", calls["delete_observation"] + 1
    )
    view.reload_moment = lambda: calls.__setitem__("reload", calls["reload"] + 1)

    view.moment = SimpleNamespace(
        treeWidget=lambda: SimpleNamespace(editable_uuids={"obs-1"})
    )
    view.window = lambda: SimpleNamespace(admin_mode=False)

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    view.delete_box(box)

    assert calls["delete_box"] == 1
    assert calls["delete_observation"] == 1
    assert calls["reload"] == 1


def test_set_annotation_focus_triggers_sam_on_concept_change_only():
    from vars_localize.ui.ImageView import ImageView

    calls = {"start": []}

    view = ImageView.__new__(ImageView)
    view._active_annotation_concept = None
    view._sam_assist_enabled = True
    view._sam_candidate_boxes = []
    view._sam_hover_box = None
    view._sam_pending_concept = None
    view.enabled_observations = {"obs-1": True, "obs-2": True}
    view.observation_map = {
        "obs-1": SimpleNamespace(observation=SimpleNamespace(concept="fish")),
        "obs-2": SimpleNamespace(observation=SimpleNamespace(concept="sponge")),
    }
    view.selected_box = None
    view.observation_uuid = None
    view._notify_sam_candidate_state = lambda: None
    view._notify_sam_status = lambda _status: None
    view._build_sam_status = lambda: "status"
    view._start_sam_candidates_for_concept = lambda concept: calls["start"].append(
        concept
    )
    view.redraw = lambda: None

    view.set_annotation_focus(concept_filter="fish", observation_uuid=None)
    assert calls["start"] == ["fish"]

    # Observation selection should not re-query SAM text prompts.
    view.set_annotation_focus(concept_filter="fish", observation_uuid="obs-1")
    assert calls["start"] == ["fish"]

    # Clearing concept should not start text prompting.
    view.set_annotation_focus(concept_filter=None, observation_uuid=None)
    assert calls["start"] == ["fish"]


def test_box_highlight_precedence_association_over_observation():
    from vars_localize.ui.BoundingBox import SourceBoundingBox
    from vars_localize.ui.ImageView import ImageView

    box_a = SourceBoundingBox(
        {"x": 1, "y": 1, "width": 10, "height": 10, "image_reference_uuid": "im"},
        label="fish",
        observation_uuid="obs-1",
        association_uuid="assoc-1",
    )
    box_b = SourceBoundingBox(
        {"x": 20, "y": 20, "width": 10, "height": 10, "image_reference_uuid": "im"},
        label="fish",
        observation_uuid="obs-1",
        association_uuid="assoc-2",
    )

    view = ImageView.__new__(ImageView)
    view.observation_uuid = "obs-1"
    view.selected_box = None

    # With an observation selected and no specific association selected, all boxes in the
    # selected observation should be highlighted.
    assert view._box_is_highlighted(box_a) is True
    assert view._box_is_highlighted(box_b) is True

    # Association focus should override and highlight only one box.
    view.selected_box = box_a
    assert view._box_is_highlighted(box_a) is True
    assert view._box_is_highlighted(box_b) is False


def test_accept_sam_candidate_deselects_observation_and_preserves_sam_state():
    from vars_localize.ui.ImageView import ImageView

    calls = {"handle": [], "drop": 0, "focus": [], "reload": [], "redraw": 0}

    view = ImageView.__new__(ImageView)
    view.observation_uuid = "obs-1"
    view._active_annotation_concept = "fish"
    view._sam_candidate_boxes = [SimpleNamespace(id="candidate-1")]
    view._sam_candidate_index = 0
    view.handle_new_box = (
        lambda candidate, refresh=True, preserve_sam_state=False: calls[
            "handle"
        ].append((candidate.id, refresh, preserve_sam_state))
    )
    view._drop_current_candidate = lambda: calls.__setitem__("drop", calls["drop"] + 1)
    view.set_annotation_focus = (
        lambda concept_filter=None, observation_uuid=None: calls["focus"].append(
            (concept_filter, observation_uuid)
        )
    )
    view.reload_moment = lambda preserve_sam_state=False: calls["reload"].append(
        preserve_sam_state
    )
    view.redraw = lambda: calls.__setitem__("redraw", calls["redraw"] + 1)

    view.accept_sam_candidate()

    assert calls["handle"] == [("candidate-1", False, True)]
    assert calls["drop"] == 1
    assert calls["focus"] == [("fish", None)]
    assert calls["reload"] == [True]
    assert calls["redraw"] == 1
