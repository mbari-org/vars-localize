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
