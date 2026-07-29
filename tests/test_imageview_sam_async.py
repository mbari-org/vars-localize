from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("PyQt6")


def test_get_prompt_concepts_uses_app_state_when_search_mode_is_video_sequence():
    from vars_localize.ui.ImageView import ImageView

    view = ImageView.__new__(ImageView)
    view.window = lambda: SimpleNamespace(
        search_panel=SimpleNamespace(
            _state=SimpleNamespace(concepts=["Actiniaria", "Cnidaria"]),
            search_mode="video_sequence_name",
            search_bar=SimpleNamespace(
                get_concepts=lambda: ["CIC 2023 ArcticRays Survey"]
            ),
        )
    )

    assert view._get_prompt_concepts() == ["Actiniaria", "Cnidaria"]


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
    view._sam_semantic_enabled = True
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


def test_sam_embedding_cuda_oom_pauses_retries(monkeypatch):
    from vars_localize.ui.ImageView import ImageView

    run_calls = {"count": 0}
    statuses = []
    moment_uuid = "moment-1"

    def fake_run_async(
        _owner,
        _fn,
        *args,
        on_result=None,
        on_error=None,
        on_finished=None,
        **kwargs,
    ):
        _ = (on_result, args, kwargs)
        run_calls["count"] += 1
        if on_error is not None:
            on_error(RuntimeError("CUDA out of memory. Tried to allocate 40.00 MiB"))
        if on_finished is not None:
            on_finished()

    monkeypatch.setattr("vars_localize.ui.ImageView.run_async", fake_run_async)

    view = ImageView.__new__(ImageView)
    view._sam_assist_enabled = True
    view.moment = SimpleNamespace(imaged_moment=SimpleNamespace(uuid=moment_uuid))
    view.pixmap_src = object()
    view.sam3_service = SimpleNamespace(available=True)
    view._sam_ready_image_uuid = None
    view._sam_embedding_busy = False
    view._sam_embedding_request_uuid = None
    view._sam_failed_image_uuid = None
    view._sam_last_error_message = None
    view._sam_pending_concept = None
    view._notify_sam_status = lambda status: statuses.append(status)
    view._pixmap_to_rgb_ndarray = lambda _pixmap: object()

    view._maybe_start_sam_embedding()

    assert run_calls["count"] == 1
    assert view._sam_embedding_busy is False
    assert view._sam_failed_image_uuid == moment_uuid
    assert view._sam_last_error_message == "SAM embedding failed (GPU out of memory)"
    assert statuses[-1] == "SAM embedding failed (GPU out of memory)"


def test_semantic_mode_disabled_skips_concept_query(monkeypatch):
    from vars_localize.ui.ImageView import ImageView

    run_calls = {"count": 0}

    def fake_run_async(*_args, **_kwargs):
        run_calls["count"] += 1

    monkeypatch.setattr("vars_localize.ui.ImageView.run_async", fake_run_async)

    view = ImageView.__new__(ImageView)
    view._sam_assist_enabled = True
    view._sam_semantic_enabled = False
    view._notify_sam_status = lambda _status: None
    view._build_sam_status = lambda: "status"
    view.moment = SimpleNamespace(imaged_moment=SimpleNamespace(uuid="moment-1"))

    view._start_sam_candidates_for_concept("fish")

    assert run_calls["count"] == 0


def test_point_mode_disabled_skips_hover_query(monkeypatch):
    from vars_localize.ui.ImageView import ImageView
    from PyQt6.QtCore import QPoint
    from PyQt6.QtCore import Qt

    run_calls = {"count": 0}

    def fake_run_async(*_args, **_kwargs):
        run_calls["count"] += 1

    monkeypatch.setattr("vars_localize.ui.ImageView.run_async", fake_run_async)

    class FakeEvent:
        def buttons(self):
            return Qt.MouseButton.NoButton

        def pos(self):
            return QPoint(10, 10)

    view = ImageView.__new__(ImageView)
    view._sam_assist_enabled = True
    view._sam_point_enabled = False
    view.pixmap_src = SimpleNamespace(width=lambda: 100, height=lambda: 100)
    view.moment = SimpleNamespace(imaged_moment=SimpleNamespace(uuid="moment-1"))
    view.resize_type = None
    view._sam_ready_image_uuid = "moment-1"
    view.get_im_rel_point = lambda _pt: QPoint(10, 10)
    view._sam_last_hover_point = None
    view._sam_hover_inflight = False

    view._maybe_update_hover_candidate(FakeEvent())

    assert run_calls["count"] == 0


def test_mouse_move_without_state_change_skips_full_redraw():
    from vars_localize.ui.ImageView import ImageView
    from PyQt6.QtCore import QPointF, QEvent, Qt
    from PyQt6.QtGui import QMouseEvent, QPixmap
    from PyQt6.QtWidgets import QApplication

    _app = QApplication.instance() or QApplication([])

    view = ImageView()
    view.resize(1200, 700)
    view.moment = SimpleNamespace(
        imaged_moment=SimpleNamespace(
            ancillary_data=None,
            recorded_timestamp=None,
            video_data=None,
        )
    )
    view.enabled_observations = {}
    view.observation_map = {}

    pixmap = QPixmap(640, 360)
    pixmap.fill()
    view.set_pixmap(pixmap)
    view.redraw()

    redraw_calls = {"count": 0}
    overlay_updates = {"count": 0}

    original_overlay_update = view._update_mouse_overlay

    def tracked_redraw():
        redraw_calls["count"] += 1

    def tracked_overlay_update():
        overlay_updates["count"] += 1
        original_overlay_update()

    view.redraw = tracked_redraw
    view._update_mouse_overlay = tracked_overlay_update

    move_event = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(150.0, 130.0),
        QPointF(150.0, 130.0),
        QPointF(150.0, 130.0),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )

    view.mouseMoveEvent(move_event)

    assert redraw_calls["count"] == 0
    assert overlay_updates["count"] == 1


def _make_box(x, y, w, h, observation_uuid="obs-1"):
    from vars_localize.ui.BoundingBox import SourceBoundingBox

    return SourceBoundingBox(
        {"x": x, "y": y, "width": w, "height": h, "image_reference_uuid": "im"},
        label="fish",
        observation_uuid=observation_uuid,
    )


def test_exemplar_boxes_for_active_concept_returns_empty_without_active_concept():
    from vars_localize.ui.ImageView import ImageView

    view = ImageView.__new__(ImageView)
    view._active_annotation_concept = None
    view.observation_map = {
        "obs-1": SimpleNamespace(
            observation=SimpleNamespace(concept="fish", boxes=[_make_box(0, 0, 10, 10)])
        )
    }

    assert view._exemplar_boxes_for_active_concept() == []


def test_exemplar_boxes_for_active_concept_returns_empty_without_observation_map():
    from vars_localize.ui.ImageView import ImageView

    view = ImageView.__new__(ImageView)
    view._active_annotation_concept = "fish"
    view.observation_map = None

    assert view._exemplar_boxes_for_active_concept() == []


def test_exemplar_boxes_for_active_concept_filters_by_concept_and_excludes_video_boxes():
    from vars_localize.ui.ImageView import ImageView

    view = ImageView.__new__(ImageView)
    view._active_annotation_concept = "fish"

    fish_box = _make_box(0, 0, 10, 10, observation_uuid="obs-1")
    fish_video_box = _make_box(50, 50, 10, 10, observation_uuid="obs-1")
    sponge_box = _make_box(20, 20, 10, 10, observation_uuid="obs-2")

    view.observation_map = {
        "obs-1": SimpleNamespace(
            observation=SimpleNamespace(
                concept="fish", boxes=[fish_box], video_boxes=[fish_video_box]
            )
        ),
        "obs-2": SimpleNamespace(
            observation=SimpleNamespace(
                concept="sponge", boxes=[sponge_box], video_boxes=[]
            )
        ),
    }

    assert view._exemplar_boxes_for_active_concept() == [fish_box]


def test_can_find_similar_requires_assist_semantic_concept_and_exemplars():
    from vars_localize.ui.ImageView import ImageView

    view = ImageView.__new__(ImageView)
    view._sam_assist_enabled = True
    view._sam_semantic_enabled = True
    view.sam3_service = SimpleNamespace(available=True)
    view._active_annotation_concept = "fish"
    view._exemplar_boxes_for_active_concept = lambda: [_make_box(0, 0, 10, 10)]

    assert view.can_find_similar() is True

    view._sam_assist_enabled = False
    assert view.can_find_similar() is False
    view._sam_assist_enabled = True

    view._sam_semantic_enabled = False
    assert view.can_find_similar() is False
    view._sam_semantic_enabled = True

    view.sam3_service = SimpleNamespace(available=False)
    assert view.can_find_similar() is False
    view.sam3_service = SimpleNamespace(available=True)

    view._active_annotation_concept = None
    assert view.can_find_similar() is False
    view._active_annotation_concept = "fish"

    view._exemplar_boxes_for_active_concept = lambda: []
    assert view.can_find_similar() is False


def test_start_sam_candidates_from_exemplars_noop_when_no_exemplars(monkeypatch):
    import vars_localize.ui.ImageView as image_view_module
    from vars_localize.ui.ImageView import ImageView

    calls = {"run_async": 0}
    monkeypatch.setattr(
        image_view_module,
        "run_async",
        lambda *a, **k: calls.__setitem__("run_async", calls["run_async"] + 1),
    )

    view = ImageView.__new__(ImageView)
    view._sam_assist_enabled = True
    view._sam_semantic_enabled = True
    view.moment = SimpleNamespace(imaged_moment=SimpleNamespace(uuid="im-1"))
    view._exemplar_boxes_for_active_concept = lambda: []
    view._notify_sam_status = lambda _status: None
    view._build_sam_status = lambda: "status"

    view._start_sam_candidates_from_exemplars("fish")

    assert calls["run_async"] == 0


def test_start_sam_candidates_from_exemplars_defers_until_embedding_ready(monkeypatch):
    import vars_localize.ui.ImageView as image_view_module
    from vars_localize.ui.ImageView import ImageView

    calls = {"run_async": 0, "embed": 0}
    monkeypatch.setattr(
        image_view_module,
        "run_async",
        lambda *a, **k: calls.__setitem__("run_async", calls["run_async"] + 1),
    )

    view = ImageView.__new__(ImageView)
    view._sam_assist_enabled = True
    view._sam_semantic_enabled = True
    view.moment = SimpleNamespace(imaged_moment=SimpleNamespace(uuid="im-1"))
    view._exemplar_boxes_for_active_concept = lambda: [_make_box(0, 0, 10, 10)]
    view._sam_ready_image_uuid = None
    view._sam_failed_image_uuid = None
    view._sam_pending_concept = "some-other-concept"
    view._sam_pending_exemplar_concept = None
    view._notify_sam_status = lambda _status: None
    view._build_sam_status = lambda: "status"
    view._maybe_start_sam_embedding = lambda: calls.__setitem__(
        "embed", calls["embed"] + 1
    )

    view._start_sam_candidates_from_exemplars("fish")

    assert calls["run_async"] == 0
    assert calls["embed"] == 1
    assert view._sam_pending_exemplar_concept == "fish"
    assert view._sam_pending_concept is None


def test_start_sam_candidates_from_exemplars_queries_with_xyxy_boxes(monkeypatch):
    import vars_localize.ui.ImageView as image_view_module
    from vars_localize.ui.ImageView import ImageView

    captured = {}

    def _fake_run_async(owner, fn, *args, on_result=None, on_error=None, **kwargs):
        captured["fn"] = fn
        captured["args"] = args
        captured["on_result"] = on_result

    monkeypatch.setattr(image_view_module, "run_async", _fake_run_async)

    box = _make_box(10, 20, 30, 40)
    view = ImageView.__new__(ImageView)
    view._sam_assist_enabled = True
    view._sam_semantic_enabled = True
    view.moment = SimpleNamespace(imaged_moment=SimpleNamespace(uuid="im-1"))
    view._exemplar_boxes_for_active_concept = lambda: [box]
    view._sam_ready_image_uuid = "im-1"
    view._sam_failed_image_uuid = None
    view._sam_candidate_observation_uuid = "stale"
    view._sam_candidate_concept = None
    view._active_annotation_concept = "fish"
    view._notify_sam_status = lambda _status: None
    view._sam_query_boxes = lambda boxes_xyxy: []

    view._start_sam_candidates_from_exemplars("fish")

    assert captured["args"] == ([(10, 20, 40, 60)],)
    assert view._sam_candidate_observation_uuid is None
    assert view._sam_candidate_concept == "fish"


def test_start_sam_candidates_from_exemplars_builds_candidates_on_result(monkeypatch):
    import vars_localize.ui.ImageView as image_view_module
    from vars_localize.ui.ImageView import ImageView

    captured = {}

    def _fake_run_async(owner, fn, *args, on_result=None, on_error=None, **kwargs):
        captured["on_result"] = on_result

    monkeypatch.setattr(image_view_module, "run_async", _fake_run_async)

    box = _make_box(10, 20, 30, 40)
    view = ImageView.__new__(ImageView)
    view._sam_assist_enabled = True
    view._sam_semantic_enabled = True
    view.moment = SimpleNamespace(imaged_moment=SimpleNamespace(uuid="im-1"))
    view._exemplar_boxes_for_active_concept = lambda: [box]
    view._sam_ready_image_uuid = "im-1"
    view._sam_failed_image_uuid = None
    view._active_annotation_concept = "fish"
    view._notify_sam_status = lambda _status: None
    view._notify_sam_candidate_state = lambda: None
    view._point_capability_text = lambda: "point ready"
    view.redraw = lambda: None
    view._make_candidate_boxes = lambda boxes, obs_uuid, concept: ["candidate-1"]

    view._start_sam_candidates_from_exemplars("fish")
    captured["on_result"]([(1, 2, 3, 4)])

    assert view._sam_candidate_boxes == ["candidate-1"]
    assert view._sam_candidate_index == 0


def test_start_sam_candidates_from_exemplars_discards_stale_result(monkeypatch):
    import vars_localize.ui.ImageView as image_view_module
    from vars_localize.ui.ImageView import ImageView

    captured = {}

    def _fake_run_async(owner, fn, *args, on_result=None, on_error=None, **kwargs):
        captured["on_result"] = on_result

    monkeypatch.setattr(image_view_module, "run_async", _fake_run_async)

    box = _make_box(10, 20, 30, 40)
    view = ImageView.__new__(ImageView)
    view._sam_assist_enabled = True
    view._sam_semantic_enabled = True
    view.moment = SimpleNamespace(imaged_moment=SimpleNamespace(uuid="im-1"))
    view._exemplar_boxes_for_active_concept = lambda: [box]
    view._sam_ready_image_uuid = "im-1"
    view._sam_failed_image_uuid = None
    view._active_annotation_concept = "fish"
    view._notify_sam_status = lambda _status: None
    view._notify_sam_candidate_state = lambda: None
    view._sam_candidate_boxes = []
    view._make_candidate_boxes = lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("should not build candidates for stale result")
    )

    view._start_sam_candidates_from_exemplars("fish")

    # Active concept changed away before the async query returned.
    view._active_annotation_concept = "sponge"
    captured["on_result"]([(1, 2, 3, 4)])

    assert view._sam_candidate_boxes == []


def test_pending_exemplar_concept_resumes_after_embedding_ready():
    from vars_localize.ui.ImageView import ImageView

    calls = {"exemplars": []}

    view = ImageView.__new__(ImageView)
    view.moment = SimpleNamespace(imaged_moment=SimpleNamespace(uuid="im-1"))
    view._sam_pending_concept = None
    view._sam_pending_exemplar_concept = "fish"
    view._sam_ready_image_uuid = None
    view._sam_failed_image_uuid = "old"
    view._sam_last_error_message = "old error"
    view._notify_sam_status = lambda _status: None
    view._build_sam_status = lambda: "status"
    view._start_sam_candidates_for_concept = lambda concept: None
    view._start_sam_candidates_from_exemplars = lambda concept: calls[
        "exemplars"
    ].append(concept)

    # Simulate the embedding-ready `_on_result` closure body directly, since
    # `_maybe_start_sam_embedding` builds it as a local function.
    embedded_uuid = "im-1"
    current_uuid = view.moment.imaged_moment.uuid
    assert current_uuid == embedded_uuid
    view._sam_ready_image_uuid = embedded_uuid
    view._sam_failed_image_uuid = None
    view._sam_last_error_message = None
    view._notify_sam_status(view._build_sam_status())
    pending_concept = view._sam_pending_concept
    if pending_concept:
        view._sam_pending_concept = None
        view._start_sam_candidates_for_concept(pending_concept)
    pending_exemplar_concept = view._sam_pending_exemplar_concept
    if pending_exemplar_concept:
        view._sam_pending_exemplar_concept = None
        view._start_sam_candidates_from_exemplars(pending_exemplar_concept)

    assert calls["exemplars"] == ["fish"]
    assert view._sam_pending_exemplar_concept is None


def test_clear_sam_state_resets_pending_exemplar_concept():
    from vars_localize.ui.ImageView import ImageView

    view = ImageView.__new__(ImageView)
    view._sam_pending_exemplar_concept = "fish"
    view._sam_candidate_boxes = ["x"]
    view._sam_candidate_index = 1
    view._sam_candidate_observation_uuid = "obs-1"
    view._sam_candidate_concept = "fish"
    view._sam_pending_concept = "fish"
    view._sam_hover_box = object()
    view._sam_hover_inflight = True
    view._sam_last_hover_point = object()
    view._notify_sam_candidate_state = lambda: None
    view._notify_sam_status = lambda _status: None
    view._build_sam_status = lambda: "status"

    view._clear_sam_state(reset_embedding=False)

    assert view._sam_pending_exemplar_concept is None


def test_set_sam_prompt_modes_resets_pending_exemplar_concept_when_semantic_disabled():
    from vars_localize.ui.ImageView import ImageView

    view = ImageView.__new__(ImageView)
    view._sam_pending_exemplar_concept = "fish"
    view._sam_pending_concept = "fish"
    view._sam_candidate_boxes = ["x"]
    view._sam_candidate_index = 1
    view._sam_hover_box = object()
    view._sam_hover_inflight = True
    view._sam_last_hover_point = object()
    view._notify_sam_candidate_state = lambda: None
    view._notify_sam_status = lambda _status: None
    view._build_sam_status = lambda: "status"
    view.redraw = lambda: None

    view.set_sam_prompt_modes(semantic_enabled=False, point_enabled=True)

    assert view._sam_pending_exemplar_concept is None


def test_start_sam_candidates_for_concept_clears_pending_exemplar_concept(monkeypatch):
    import vars_localize.ui.ImageView as image_view_module
    from vars_localize.ui.ImageView import ImageView

    monkeypatch.setattr(image_view_module, "run_async", lambda *a, **k: None)

    view = ImageView.__new__(ImageView)
    view._sam_assist_enabled = True
    view._sam_semantic_enabled = True
    view.moment = SimpleNamespace(imaged_moment=SimpleNamespace(uuid="im-1"))
    view._sam_ready_image_uuid = None
    view._sam_failed_image_uuid = None
    view._sam_pending_exemplar_concept = "sponge"
    view._notify_sam_status = lambda _status: None
    view._build_sam_status = lambda: "status"
    view._maybe_start_sam_embedding = lambda: None

    view._start_sam_candidates_for_concept("fish")

    assert view._sam_pending_concept == "fish"
    assert view._sam_pending_exemplar_concept is None


def test_find_similar_from_exemplars_uses_active_concept():
    from vars_localize.ui.ImageView import ImageView

    calls = []
    view = ImageView.__new__(ImageView)
    view._active_annotation_concept = "fish"
    view._start_sam_candidates_from_exemplars = lambda concept: calls.append(concept)

    view.find_similar_from_exemplars()

    assert calls == ["fish"]


def test_right_click_sam_accept_defers_handle_new_box_to_release(monkeypatch):
    """Regression test for mbari-org/vars-feedback#317.

    handle_new_box() can open a modal "Specify a concept" dialog (when no
    concept/observation is active, e.g. "All concepts" selected). Opening
    that dialog while the right mouse button is still physically down
    corrupts the view's mouse grab on some platforms (observed on macOS),
    freezing the canvas to further mouse input.

    A same-tick QTimer.singleShot(0, ...) fired from mousePressEvent isn't
    enough: it runs microseconds later, long before the physical button-up.
    The accept must wait for the matching mouseReleaseEvent (which only
    fires once Qt has actually processed the button-up) before running,
    with a further deferral there as an extra safety margin.
    """
    from PyQt6.QtCore import QEvent, QPointF, Qt, QTimer
    from PyQt6.QtGui import QMouseEvent
    from vars_localize.ui.ImageView import ImageView

    scheduled = []
    monkeypatch.setattr(
        QTimer, "singleShot", staticmethod(lambda msec, cb: scheduled.append(cb))
    )

    view = ImageView.__new__(ImageView)
    view._sam_assist_enabled = True
    view._panning = False
    hover_box = object()
    view._sam_hover_box = hover_box
    view.redraw = lambda: None
    calls = []
    view.handle_new_box = lambda box, preserve_sam_state=False: calls.append(box)

    press = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(0, 0),
        QPointF(0, 0),
        QPointF(0, 0),
        Qt.MouseButton.RightButton,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier,
    )
    view.mousePressEvent(press)

    assert view._sam_hover_box is None
    assert view._pending_sam_right_click_accept is hover_box
    assert calls == [], "handle_new_box must not run at press time"
    assert scheduled == [], "must not schedule anything before the button is released"

    release = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        QPointF(0, 0),
        QPointF(0, 0),
        QPointF(0, 0),
        Qt.MouseButton.RightButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    view.mouseReleaseEvent(release)

    assert view._pending_sam_right_click_accept is None
    assert (
        calls == []
    ), "handle_new_box must not run synchronously inside mouseReleaseEvent either"
    assert len(scheduled) == 1

    scheduled[0]()
    assert calls == [hover_box]
