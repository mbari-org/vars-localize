from __future__ import annotations

from types import SimpleNamespace
import importlib

import pytest

pytest.importorskip("PyQt6")


def test_load_page_ignores_stale_results(monkeypatch):
    search_panel_module = importlib.import_module("vars_localize.ui.SearchPanel")
    from vars_localize.ui.SearchPanel import SearchPanel

    loaded = []
    queued_callbacks = []

    def fake_run_async(
        owner,
        fn,
        *args,
        on_result=None,
        on_error=None,
        on_finished=None,
        **kwargs,
    ):
        queued_callbacks.append((on_result, on_finished))

    monkeypatch.setattr(search_panel_module, "run_async", fake_run_async)

    panel = SearchPanel.__new__(SearchPanel)
    panel.uuids = ["im-1", "im-2"]
    panel.paginator = SimpleNamespace(slice=slice(0, 2))
    panel._request_seq = 0
    panel._active_page_request_id = 0
    panel._loading_ops = 0
    panel._state = SimpleNamespace(loading=False)
    panel.entry_tree = SimpleNamespace(load_page_data=lambda data: loaded.append(data))
    panel._m3 = object()
    panel._show_error = lambda *_: None

    panel.load_page()
    panel.load_page()

    first_result, first_finished = queued_callbacks[0]
    second_result, second_finished = queued_callbacks[1]

    first_result(["stale"])
    first_finished()
    second_result(["fresh"])
    second_finished()

    assert loaded == [["fresh"]]
    assert panel._loading_ops == 0


def test_observation_dialog_concepts_uses_catalog_when_search_mode_is_video_sequence():
    from vars_localize.ui.SearchPanel import SearchPanel

    panel = SearchPanel.__new__(SearchPanel)
    panel._state = SimpleNamespace(concepts=["Actiniaria", "Cnidaria"])
    panel.search_mode = "video_sequence_name"
    panel.search_bar = SimpleNamespace(
        get_concepts=lambda: ["CIC 2023 ArcticRays Survey"]
    )

    assert panel.get_concept_catalog() == ["Actiniaria", "Cnidaria"]


def test_observation_dialog_concepts_falls_back_to_search_bar_when_catalog_empty():
    from vars_localize.ui.SearchPanel import SearchPanel

    panel = SearchPanel.__new__(SearchPanel)
    panel._state = SimpleNamespace(concepts=[])
    panel.search_mode = "concept"
    panel.search_bar = SimpleNamespace(get_concepts=lambda: ["Actiniaria"])

    assert panel.get_concept_catalog() == ["Actiniaria"]
