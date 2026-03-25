from __future__ import annotations

from typing import Any, cast

import pytest

pytest.importorskip("PyQt6")


class DummyTree:
    def __init__(self):
        self._selected_moment = None
        self.refreshed = False
        self.repopulated = False

    def _refresh_moment_row(self, entry):
        self.refreshed = True

    def _populate_observations(self, entry):
        self.repopulated = True


def test_update_imaged_moment_entry_recomputes_status_and_refreshes_tree():
    from vars_localize.models import ImagedMomentEntry, ObservationEntry
    from vars_localize.ui.EntryTree import EntryTreeItem, update_imaged_moment_entry

    tree = DummyTree()
    moment = ImagedMomentEntry(
        uuid="im-1",
        observations=[],
        image_reference_uuid=None,
        image_url=None,
        video_reference_uuid=None,
    )
    moment_item = EntryTreeItem(moment, parent=None, tree=cast(Any, tree))
    tree._selected_moment = moment_item

    obs1 = EntryTreeItem(
        ObservationEntry(uuid="obs-1", concept="fish", observer="u", boxes=[]),
        parent=moment_item,
        tree=cast(Any, tree),
    )
    obs2 = EntryTreeItem(
        ObservationEntry(
            uuid="obs-2",
            concept="fish",
            observer="u",
            boxes=[{"x": 1}],
        ),
        parent=moment_item,
        tree=cast(Any, tree),
    )
    moment_item.add_child(obs1)
    moment_item.add_child(obs2)

    update_imaged_moment_entry(moment_item)

    assert obs1.observation.status == 0
    assert obs2.observation.status == 1
    assert moment.status == "Partial (1/2)"
    assert len(moment.observations) == 2
    assert tree.refreshed is True
    assert tree.repopulated is True
