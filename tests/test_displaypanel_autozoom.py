from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("PyQt6")


class _FakeCheckBox:
    def __init__(self, checked: bool = True):
        self._checked = checked

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool):
        self._checked = bool(checked)


def _make_panel(checked: bool = True, app_settings=None):
    from vars_localize.ui.DisplayPanel import DisplayPanel

    panel = DisplayPanel.__new__(DisplayPanel)
    panel._app_settings = app_settings
    panel.sam_autozoom = _FakeCheckBox(checked)
    return panel


def test_preview_sam_candidate_zooms_when_autozoom_enabled():
    panel = _make_panel(checked=True)
    calls = {"preview": 0}
    panel.image_view = SimpleNamespace(
        preview_focus_on_sam_candidate=lambda: calls.__setitem__(
            "preview", calls["preview"] + 1
        )
    )

    panel._preview_sam_candidate()

    assert calls["preview"] == 1


def test_preview_sam_candidate_skips_zoom_when_autozoom_disabled():
    panel = _make_panel(checked=False)
    calls = {"preview": 0}
    panel.image_view = SimpleNamespace(
        preview_focus_on_sam_candidate=lambda: calls.__setitem__(
            "preview", calls["preview"] + 1
        )
    )

    panel._preview_sam_candidate()

    assert calls["preview"] == 0


def test_accept_and_reject_only_re_zoom_when_autozoom_enabled():
    panel = _make_panel(checked=False)
    calls = {"preview": 0}
    panel.image_view = SimpleNamespace(
        accept_sam_candidate=lambda: None,
        reject_sam_candidate=lambda: None,
        preview_focus_on_sam_candidate=lambda: calls.__setitem__(
            "preview", calls["preview"] + 1
        ),
    )

    panel._accept_sam_candidate()
    panel._reject_sam_candidate()

    assert calls["preview"] == 0

    panel.sam_autozoom.setChecked(True)
    panel._accept_sam_candidate()
    panel._reject_sam_candidate()

    assert calls["preview"] == 2


def test_toggling_autozoom_off_clears_active_preview():
    panel = _make_panel(checked=True)
    calls = {"clear": 0}
    panel.image_view = SimpleNamespace(
        clear_focus_preview=lambda: calls.__setitem__("clear", calls["clear"] + 1)
    )

    panel._on_autozoom_toggled(False)

    assert calls["clear"] == 1


def test_toggling_autozoom_persists_to_app_settings():
    settings = SimpleNamespace(sam_autozoom_enabled=True)
    panel = _make_panel(checked=True, app_settings=settings)
    panel.image_view = SimpleNamespace(clear_focus_preview=lambda: None)

    panel._on_autozoom_toggled(False)

    assert settings.sam_autozoom_enabled is False
