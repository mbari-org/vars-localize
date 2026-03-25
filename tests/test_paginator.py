from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")


def test_prompt_jump_allows_lower_page_numbers(monkeypatch):
    from vars_localize.ui import Paginator as paginator_module
    from vars_localize.ui.Paginator import Paginator

    paginator = Paginator.__new__(Paginator)
    paginator.limit = 25
    paginator.count = 100
    paginator.offset = 50  # page 3
    paginator.update_nav = lambda: None

    class DummySignal:
        def __init__(self):
            self.count = 0

        def emit(self):
            self.count += 1

    paginator.jump_signal = DummySignal()

    captured = {}

    def fake_get_int(*args, **kwargs):
        captured.update(kwargs)
        return (1, True)

    monkeypatch.setattr(paginator_module.QInputDialog, "getInt", fake_get_int)

    paginator.prompt_jump()

    assert captured["min"] == 1
    assert captured["max"] == paginator.page_count
    assert paginator.offset == 0
    assert paginator.jump_signal.count == 1
