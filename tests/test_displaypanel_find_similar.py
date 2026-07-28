from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("PyQt6")


class _FakeButton:
    def __init__(self):
        self._enabled = True
        self._visible = True

    def setEnabled(self, enabled: bool):
        self._enabled = bool(enabled)

    def isEnabled(self) -> bool:
        return self._enabled

    def setVisible(self, visible: bool):
        self._visible = bool(visible)

    def isVisible(self) -> bool:
        return self._visible


def _make_panel():
    from vars_localize.ui.DisplayPanel import DisplayPanel

    panel = DisplayPanel.__new__(DisplayPanel)
    panel.sam_accept = _FakeButton()
    panel.sam_reject = _FakeButton()
    panel.sam_find_similar = _FakeButton()
    panel.sam_label = SimpleNamespace(setText=lambda _text: None)
    panel.sam_status_label = SimpleNamespace(setText=lambda _text: None)
    return panel


def test_find_similar_button_invokes_image_view():
    panel = _make_panel()
    calls = {"count": 0}
    panel.image_view = SimpleNamespace(
        find_similar_from_exemplars=lambda: calls.__setitem__(
            "count", calls["count"] + 1
        )
    )

    panel._find_similar()

    assert calls["count"] == 1


def test_set_sam_status_syncs_find_similar_enabled():
    panel = _make_panel()

    panel.image_view = SimpleNamespace(can_find_similar=lambda: True)
    panel._set_sam_status("ready")
    assert panel.sam_find_similar.isEnabled() is True

    panel.image_view = SimpleNamespace(can_find_similar=lambda: False)
    panel._set_sam_status("disabled")
    assert panel.sam_find_similar.isEnabled() is False


def test_set_sam_candidate_state_syncs_find_similar_and_leaves_accept_reject_independent():
    panel = _make_panel()

    panel.image_view = SimpleNamespace(can_find_similar=lambda: False)
    panel._set_sam_candidate_state(True, 0, 1)
    assert panel.sam_accept.isEnabled() is True
    assert panel.sam_reject.isEnabled() is True
    assert panel.sam_find_similar.isEnabled() is False

    panel.image_view = SimpleNamespace(can_find_similar=lambda: True)
    panel._set_sam_candidate_state(False, 0, 0)
    assert panel.sam_accept.isEnabled() is False
    assert panel.sam_reject.isEnabled() is False
    assert panel.sam_find_similar.isEnabled() is True
