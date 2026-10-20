from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("PyQt6")


def _make_view(box_item):
    from vars_localize.ui.ImageView import ImageView

    opened = []
    view = ImageView.__new__(ImageView)
    view.focus_association_box = lambda obs, assoc: box_item
    view.show_box_properties_dialog = lambda item: opened.append(item)
    return view, opened


def test_edit_association_box_opens_dialog_for_editable_box():
    box_item = SimpleNamespace(editable=True)
    view, opened = _make_view(box_item)

    view.edit_association_box("obs-1", "assoc-1")

    assert opened == [box_item]


@pytest.mark.parametrize("box_item", [None, SimpleNamespace(editable=False)])
def test_edit_association_box_rejects_missing_or_readonly_box(box_item):
    view, opened = _make_view(box_item)

    with pytest.raises(LookupError):
        view.edit_association_box("obs-1", "assoc-1")
    assert opened == []


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (
            {"is_box": True, "observation_uuid": "obs-1", "uuid": "a-1"},
            ("obs-1", "a-1"),
        ),
        ({"is_box": False, "observation_uuid": "obs-1", "uuid": "a-1"}, None),
        ({"is_box": True, "observation_uuid": "", "uuid": "a-1"}, None),
        (None, None),
    ],
)
def test_box_association_uuids(payload, expected):
    from vars_localize.ui.EntryTree import ImagedMomentTree

    tree = ImagedMomentTree.__new__(ImagedMomentTree)
    tree.associations_table = object()
    tree._row_payload = lambda table, row: payload

    assert tree._box_association_uuids(0) == expected
    assert tree._box_association_uuids(-1) is None
