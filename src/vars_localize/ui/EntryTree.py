"""Unified browser for imaged moments, observations, and associations."""

import json
import webbrowser
from datetime import datetime, timedelta
from enum import Enum
from http.client import HTTPException
from typing import Any, List, Optional, cast

from PyQt6.QtCore import QSettings, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vars_localize.models import ImagedMomentEntry, ObservationEntry
from vars_localize.services import M3Service
from vars_localize.ui.ConceptSearchbar import ConceptSearchbar
from vars_localize.ui.theme import status_brush
from vars_localize.util.logging import get_logger
from vars_localize.util.qt_async import run_async

logger = get_logger("EntryTree")


class StatusRole(str, Enum):
    UNKNOWN = "unknown"
    EMPTY = "empty"
    UNLOCALIZED = "unlocalized"
    PARTIAL = "partial"
    LOCALIZED = "localized"


class EntryTreeItem:
    """Lightweight payload wrapper retained for compatibility with existing flows."""

    __slots__ = ["payload", "_parent", "_children", "_tree"]

    def __init__(
        self,
        payload: object,
        parent: Optional["EntryTreeItem"],
        tree: "ImagedMomentTree",
    ):
        self.payload = payload
        self._parent = parent
        self._children: List[EntryTreeItem] = []
        self._tree = tree

    @property
    def is_imaged_moment(self) -> bool:
        return isinstance(self.payload, ImagedMomentEntry)

    @property
    def is_observation(self) -> bool:
        return isinstance(self.payload, ObservationEntry)

    @property
    def imaged_moment(self) -> ImagedMomentEntry:
        if not isinstance(self.payload, ImagedMomentEntry):
            raise TypeError("EntryTreeItem payload is not ImagedMomentEntry")
        return self.payload

    @property
    def observation(self) -> ObservationEntry:
        if not isinstance(self.payload, ObservationEntry):
            raise TypeError("EntryTreeItem payload is not ObservationEntry")
        return self.payload

    def parent(self) -> Optional["EntryTreeItem"]:
        return self._parent

    def child(self, idx: int) -> "EntryTreeItem":
        return self._children[idx]

    def childCount(self) -> int:
        return len(self._children)

    def add_child(self, child: "EntryTreeItem"):
        self._children.append(child)

    def clear_children(self):
        self._children.clear()

    def treeWidget(self) -> "ImagedMomentTree":
        return self._tree

    def setExpanded(self, expanded: bool):
        _ = expanded


def _uuid_from_payload(payload: object) -> Optional[str]:
    if isinstance(payload, ImagedMomentEntry):
        return payload.uuid
    if isinstance(payload, ObservationEntry):
        return payload.uuid
    return None


class ImagedMomentTree(QWidget):
    currentItemChanged = pyqtSignal(object, object)
    itemDoubleClicked = pyqtSignal(object, int)
    associationActivated = pyqtSignal(str, str)
    annotationFocusChanged = pyqtSignal(object, object)

    def __init__(self, m3_service: M3Service, parent=None):
        super(ImagedMomentTree, self).__init__(parent)

        self._m3 = m3_service
        self._settings = QSettings("MBARI", "VARSLocalize")

        self.uuids: List[str] = []
        self.editable_uuids = set()

        self._moment_items: List[EntryTreeItem] = []
        self._current_item: Optional[EntryTreeItem] = None
        self._selected_moment: Optional[EntryTreeItem] = None
        self._selected_observation: Optional[EntryTreeItem] = None
        self._active_concept_filter: Optional[str] = None
        self._observation_rows: List[EntryTreeItem] = []

        self.setLayout(QVBoxLayout())
        layout = cast(QVBoxLayout, self.layout())
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.annotation_controls = QWidget()
        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(6)
        self.annotation_controls.setLayout(controls_layout)

        self.concept_filter_combo = QComboBox()
        self.concept_filter_combo.setMinimumWidth(220)
        self.concept_filter_combo.setToolTip(
            "Filter observations by concept for annotation focus"
        )
        self.concept_filter_combo.currentIndexChanged.connect(
            self._on_concept_filter_changed
        )

        self.clear_concept_button = QPushButton("Clear Concept")
        self.clear_concept_button.setToolTip(
            "Show all concepts and clear concept-based annotation focus"
        )
        self.clear_concept_button.clicked.connect(self.clear_concept_filter)

        self.clear_observation_button = QPushButton("Clear Observation")
        self.clear_observation_button.setToolTip(
            "Deselect the current observation and hide associations"
        )
        self.clear_observation_button.clicked.connect(self.clear_observation_selection)

        controls_layout.addWidget(QLabel("Annotate Concept"))
        controls_layout.addWidget(self.concept_filter_combo)
        controls_layout.addWidget(self.clear_concept_button)
        controls_layout.addWidget(self.clear_observation_button)
        controls_layout.addStretch(1)

        self._populate_concept_filter_options([])
        self.clear_concept_button.setEnabled(False)
        self.clear_observation_button.setEnabled(False)

        self.moments_table = self._build_table(
            ["#", "Observations", "Status"],
            QAbstractItemView.SelectionMode.SingleSelection,
        )
        self.observations_table = self._build_table(
            ["#", "Concept", "Observer", "Status"],
            QAbstractItemView.SelectionMode.ExtendedSelection,
        )
        self.associations_table = self._build_table(
            ["#", "Type", "Target", "Summary"],
            QAbstractItemView.SelectionMode.SingleSelection,
        )

        self._set_resize_modes(
            self.moments_table,
            [
                QHeaderView.ResizeMode.ResizeToContents,
                QHeaderView.ResizeMode.ResizeToContents,
                QHeaderView.ResizeMode.Stretch,
            ],
        )
        self._set_resize_modes(
            self.observations_table,
            [
                QHeaderView.ResizeMode.ResizeToContents,
                QHeaderView.ResizeMode.ResizeToContents,
                QHeaderView.ResizeMode.ResizeToContents,
                QHeaderView.ResizeMode.Stretch,
            ],
        )
        self._set_resize_modes(
            self.associations_table,
            [
                QHeaderView.ResizeMode.ResizeToContents,
                QHeaderView.ResizeMode.ResizeToContents,
                QHeaderView.ResizeMode.ResizeToContents,
                QHeaderView.ResizeMode.Stretch,
            ],
        )

        self.stacked_splitter = QSplitter(Qt.Orientation.Vertical)
        self.stacked_splitter.addWidget(self.moments_table)
        self.stacked_splitter.addWidget(self.observations_table)
        self.stacked_splitter.addWidget(self.associations_table)
        layout.addWidget(self.annotation_controls)
        layout.addWidget(self.stacked_splitter, 1)

        self._restore_splitter_sizes()
        self.stacked_splitter.splitterMoved.connect(self._persist_splitter_sizes)

        self.moments_table.itemSelectionChanged.connect(
            self._on_moment_selection_changed
        )
        self.observations_table.itemSelectionChanged.connect(
            self._on_observation_selection_changed
        )
        self.observations_table.itemDoubleClicked.connect(
            self._on_observation_double_clicked
        )
        self.associations_table.itemSelectionChanged.connect(
            self._on_association_selection_changed
        )

        self._attach_context_copy_menu(self.moments_table)
        self._attach_context_copy_menu(self.observations_table)
        self._attach_context_copy_menu(self.associations_table)

        self._delete_shortcut = QShortcut(
            QKeySequence("Delete"), self.observations_table
        )
        self._delete_shortcut.activated.connect(self._handle_delete_shortcut)

        self._rename_shortcut = QShortcut(
            QKeySequence("Ctrl+R"), self.observations_table
        )
        self._rename_shortcut.activated.connect(self._handle_rename_shortcut)

    def _build_table(self, headers: List[str], selection_mode) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(selection_mode)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        vheader = table.verticalHeader()
        if vheader is not None:
            vheader.setVisible(False)
        return table

    def _set_resize_modes(
        self, table: QTableWidget, modes: List[QHeaderView.ResizeMode]
    ):
        header = table.horizontalHeader()
        if header is None:
            return
        for idx, mode in enumerate(modes):
            header.setSectionResizeMode(idx, mode)

    def _attach_context_copy_menu(self, table: QTableWidget):
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(
            lambda point, t=table: self._show_copy_uuid_menu(t, point)
        )

    def _restore_splitter_sizes(self):
        raw = self._settings.value("ui/entry_browser_splitter_sizes")
        if isinstance(raw, list) and raw:
            try:
                self.stacked_splitter.setSizes([int(v) for v in raw])
                return
            except (TypeError, ValueError):
                pass
        self.stacked_splitter.setSizes([250, 260, 220])

    def _persist_splitter_sizes(self):
        self._settings.setValue(
            "ui/entry_browser_splitter_sizes", self.stacked_splitter.sizes()
        )

    def _show_copy_uuid_menu(self, table: QTableWidget, point):
        item = table.itemAt(point)
        if item is None:
            return

        row = item.row()
        if row < 0:
            return

        payload = self._row_payload(table, row)
        if payload is None:
            return

        uuid = None
        if isinstance(payload, EntryTreeItem):
            uuid = _uuid_from_payload(payload.payload)
        elif isinstance(payload, dict):
            uuid = payload.get("uuid")

        if not uuid:
            return

        menu = QMenu("Context menu", self)
        copy_action = QAction("Copy UUID")

        def do_copy():
            clipboard = QApplication.clipboard()
            if clipboard is not None:
                clipboard.setText(str(uuid))

        copy_action.triggered.connect(do_copy)
        menu.addAction(copy_action)

        viewport = table.viewport()
        if viewport is not None:
            menu.exec(viewport.mapToGlobal(point))

    def _set_row_payload(self, table: QTableWidget, row: int, payload: object):
        key_item = table.item(row, 0)
        if key_item is None:
            key_item = QTableWidgetItem()
            table.setItem(row, 0, key_item)
        key_item.setData(Qt.ItemDataRole.UserRole, payload)

    def _row_payload(self, table: QTableWidget, row: int):
        key_item = table.item(row, 0)
        if key_item is None:
            return None
        return key_item.data(Qt.ItemDataRole.UserRole)

    def _moment_status(self, moment: ImagedMomentEntry) -> tuple[str, str, StatusRole]:
        total = len(moment.observations)
        localized = sum(1 for obs in moment.observations if obs.boxes)
        if total <= 0:
            return ("Empty", "No observations in this imaged moment", StatusRole.EMPTY)
        if localized <= 0:
            return (
                "Unlocalized (0/{})".format(total),
                "None of {} observations are localized".format(total),
                StatusRole.UNLOCALIZED,
            )
        if localized < total:
            return (
                "Partial ({}/{})".format(localized, total),
                "{} of {} observations are localized".format(localized, total),
                StatusRole.PARTIAL,
            )
        return (
            "Localized ({}/{})".format(localized, total),
            "All {} observations are localized".format(total),
            StatusRole.LOCALIZED,
        )

    def _observation_status(self, obs: ObservationEntry) -> tuple[str, str, StatusRole]:
        box_count = len(obs.boxes)
        if box_count <= 0:
            return ("Open", "No localized bounding boxes yet", StatusRole.UNLOCALIZED)
        return (
            "Localized ({})".format(box_count),
            "Observation has {} localized bounding box(es)".format(box_count),
            StatusRole.LOCALIZED,
        )

    def _set_status_cell(
        self,
        table: QTableWidget,
        row: int,
        col: int,
        text: str,
        tooltip: str,
        role: StatusRole,
    ):
        item = table.item(row, col)
        if item is None:
            item = QTableWidgetItem()
            table.setItem(row, col, item)
        item.setText(text)
        item.setToolTip(tooltip)
        item.setForeground(status_brush(role.value))

    def clear(self):
        self._moment_items = []
        self._selected_moment = None
        self._selected_observation = None
        self._observation_rows = []
        self._active_concept_filter = None
        self._set_current_item(None)
        self.moments_table.setRowCount(0)
        self.observations_table.setRowCount(0)
        self.associations_table.setRowCount(0)
        self._populate_concept_filter_options([])
        self.clear_concept_button.setEnabled(False)
        self.clear_observation_button.setEnabled(False)

    def _set_current_item(self, item: Optional[EntryTreeItem]):
        previous = self._current_item
        self._current_item = item
        self.currentItemChanged.emit(item, previous)

    def currentItem(self) -> Optional[EntryTreeItem]:
        return self._current_item

    def setCurrentItem(self, item: EntryTreeItem):
        if item.is_imaged_moment:
            self._select_moment_item(item)
            return

        if item.is_observation:
            parent = item.parent()
            if parent is not None:
                self._select_moment_item(parent)
                for row in range(self.observations_table.rowCount()):
                    row_payload = self._row_payload(self.observations_table, row)
                    if row_payload is item:
                        self.observations_table.selectRow(row)
                        break

    def selectedItems(self) -> List[EntryTreeItem]:
        selection_model = self.observations_table.selectionModel()
        if selection_model is None:
            return []

        rows = sorted({idx.row() for idx in selection_model.selectedRows()})
        selected: List[EntryTreeItem] = []
        for row in rows:
            payload = self._row_payload(self.observations_table, row)
            if isinstance(payload, EntryTreeItem):
                selected.append(payload)
        return selected

    def select_next_item(self):
        if (
            self.observations_table.rowCount() > 0
            and self._current_item is not None
            and self._current_item.is_observation
        ):
            row = self.observations_table.currentRow()
            if row < self.observations_table.rowCount() - 1:
                self.observations_table.selectRow(row + 1)
            return

        row = self.moments_table.currentRow()
        if row < self.moments_table.rowCount() - 1:
            self.moments_table.selectRow(row + 1)

    def select_prev_item(self):
        if (
            self.observations_table.rowCount() > 0
            and self._current_item is not None
            and self._current_item.is_observation
        ):
            row = self.observations_table.currentRow()
            if row > 0:
                self.observations_table.selectRow(row - 1)
            return

        row = self.moments_table.currentRow()
        if row > 0:
            self.moments_table.selectRow(row - 1)

    def load_page_data(self, imaged_moment_data: List[ImagedMomentEntry]):
        self.clear()
        if not imaged_moment_data:
            return

        for metadata in imaged_moment_data:
            self._add_moment(metadata)

        if self.moments_table.rowCount() > 0:
            self.moments_table.selectRow(0)

    def _add_moment(self, metadata: ImagedMomentEntry):
        moment_item = EntryTreeItem(metadata, parent=None, tree=self)
        for obs in metadata.observations:
            moment_item.add_child(EntryTreeItem(obs, parent=moment_item, tree=self))

        self._moment_items.append(moment_item)

        row = self.moments_table.rowCount()
        self.moments_table.insertRow(row)

        self.moments_table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
        self._set_row_payload(self.moments_table, row, moment_item)

        obs_count_text = "{}".format(len(metadata.observations))
        self.moments_table.setItem(row, 1, QTableWidgetItem(obs_count_text))

        status_text, tooltip, role = self._moment_status(metadata)
        self._set_status_cell(self.moments_table, row, 2, status_text, tooltip, role)

    def _select_moment_item(self, moment_item: EntryTreeItem):
        self._selected_moment = moment_item
        self._selected_observation = None
        self._refresh_concept_filter_options(moment_item)
        self._populate_observations(moment_item)
        self.associations_table.setRowCount(0)
        self._set_current_item(moment_item)
        self.clear_observation_button.setEnabled(False)
        self._emit_annotation_focus_changed()

        for row in range(self.moments_table.rowCount()):
            row_payload = self._row_payload(self.moments_table, row)
            if row_payload is moment_item:
                self.moments_table.selectRow(row)
                break

    def _populate_observations(self, moment_item: EntryTreeItem):
        self.observations_table.setRowCount(0)
        self._observation_rows = []

        visible_observations = [
            child
            for child in moment_item._children
            if child.is_observation
            and (
                self._active_concept_filter is None
                or child.observation.concept == self._active_concept_filter
            )
        ]

        for row, obs_item in enumerate(visible_observations):
            obs = obs_item.observation
            self.observations_table.insertRow(row)
            self._observation_rows.append(obs_item)

            self.observations_table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
            self._set_row_payload(self.observations_table, row, obs_item)

            concept_item = QTableWidgetItem(obs.concept)
            if obs.uuid in self.editable_uuids:
                concept_item.setForeground(status_brush("editable"))
            self.observations_table.setItem(row, 1, concept_item)

            self.observations_table.setItem(row, 2, QTableWidgetItem(obs.observer))

            status_text, tooltip, role = self._observation_status(obs)
            self._set_status_cell(
                self.observations_table, row, 3, status_text, tooltip, role
            )

    def _populate_associations(self, obs_item: EntryTreeItem):
        self.associations_table.setRowCount(0)
        observation = obs_item.observation

        for row, assoc in enumerate(observation.associations):
            self.associations_table.insertRow(row)
            self.associations_table.setItem(row, 0, QTableWidgetItem(str(row + 1)))

            is_box = assoc.link_name == "bounding box"
            assoc_type = "Bounding Box" if is_box else assoc.link_name
            target = assoc.to_concept or "-"

            summary = assoc.link_value
            if is_box:
                try:
                    parsed = json.loads(assoc.link_value or "{}")
                except json.JSONDecodeError:
                    parsed = {}
                x = parsed.get("x", "?")
                y = parsed.get("y", "?")
                w = parsed.get("width", "?")
                h = parsed.get("height", "?")
                summary = "{}x{} @ ({},{})".format(w, h, x, y)
            elif len(summary or "") > 80:
                summary = (summary or "")[:77] + "..."

            self.associations_table.setItem(row, 1, QTableWidgetItem(assoc_type))
            self.associations_table.setItem(row, 2, QTableWidgetItem(target))

            summary_item = QTableWidgetItem(summary or "")
            summary_item.setToolTip(assoc.link_value or "")
            self.associations_table.setItem(row, 3, summary_item)

            self._set_row_payload(
                self.associations_table,
                row,
                {
                    "uuid": assoc.uuid,
                    "observation_uuid": observation.uuid,
                    "is_box": is_box,
                },
            )

    def _on_moment_selection_changed(self):
        row = self.moments_table.currentRow()
        if row < 0:
            return

        payload = self._row_payload(self.moments_table, row)
        if not isinstance(payload, EntryTreeItem):
            return

        self._select_moment_item(payload)

    def _on_observation_selection_changed(self):
        row = self.observations_table.currentRow()
        if row < 0:
            self._selected_observation = None
            self.associations_table.setRowCount(0)
            if self._selected_moment is not None:
                self._set_current_item(self._selected_moment)
            self.clear_observation_button.setEnabled(False)
            self._emit_annotation_focus_changed()
            return

        if row >= len(self._observation_rows):
            return

        payload = self._observation_rows[row]
        self._selected_observation = payload
        self._populate_associations(payload)
        self._set_current_item(payload)
        self.clear_observation_button.setEnabled(True)
        self._emit_annotation_focus_changed()

    def _populate_concept_filter_options(self, concepts: List[str]):
        old_data = self.concept_filter_combo.currentData()
        self.concept_filter_combo.blockSignals(True)
        self.concept_filter_combo.clear()
        self.concept_filter_combo.addItem("All concepts", None)
        for concept in sorted(set(concepts)):
            self.concept_filter_combo.addItem(concept, concept)
        idx = self.concept_filter_combo.findData(old_data)
        if idx < 0:
            idx = 0
        self.concept_filter_combo.setCurrentIndex(idx)
        self.concept_filter_combo.blockSignals(False)

    def _refresh_concept_filter_options(self, moment_item: EntryTreeItem):
        concepts = [
            child.observation.concept
            for child in moment_item._children
            if child.is_observation
        ]
        previous_filter = self._active_concept_filter
        self._populate_concept_filter_options(concepts)
        if previous_filter is not None and previous_filter in set(concepts):
            self._active_concept_filter = previous_filter
            idx = self.concept_filter_combo.findData(previous_filter)
            if idx >= 0:
                self.concept_filter_combo.setCurrentIndex(idx)
        else:
            self._active_concept_filter = None
            self.concept_filter_combo.setCurrentIndex(0)
        self.clear_concept_button.setEnabled(self._active_concept_filter is not None)

    def _on_concept_filter_changed(self, _index: int):
        data = self.concept_filter_combo.currentData()
        self._active_concept_filter = str(data) if isinstance(data, str) else None
        self.clear_concept_button.setEnabled(self._active_concept_filter is not None)

        if self._selected_moment is None:
            return

        selected_uuid = (
            self._selected_observation.observation.uuid
            if self._selected_observation is not None
            else None
        )
        self._populate_observations(self._selected_moment)

        if selected_uuid is not None:
            for row, obs_item in enumerate(self._observation_rows):
                if obs_item.observation.uuid == selected_uuid:
                    self.observations_table.selectRow(row)
                    return

        self.clear_observation_selection()

    def clear_concept_filter(self):
        if self.concept_filter_combo.currentIndex() == 0:
            return
        self.concept_filter_combo.setCurrentIndex(0)

    def clear_observation_selection(self):
        if self.observations_table.selectionModel() is not None:
            self.observations_table.clearSelection()
        self.observations_table.setCurrentCell(-1, -1)
        self._selected_observation = None
        self.associations_table.setRowCount(0)
        self.clear_observation_button.setEnabled(False)
        if self._selected_moment is not None:
            self._set_current_item(self._selected_moment)
        self._emit_annotation_focus_changed()

    def _emit_annotation_focus_changed(self):
        observation_uuid = None
        if self._selected_observation is not None:
            observation_uuid = self._selected_observation.observation.uuid
        self.annotationFocusChanged.emit(self._active_concept_filter, observation_uuid)

    def _on_association_selection_changed(self):
        row = self.associations_table.currentRow()
        if row < 0:
            return

        payload = self._row_payload(self.associations_table, row)
        if not isinstance(payload, dict):
            return

        if bool(payload.get("is_box")):
            obs_uuid = str(payload.get("observation_uuid", ""))
            assoc_uuid = str(payload.get("uuid", ""))
            if obs_uuid and assoc_uuid:
                self.associationActivated.emit(obs_uuid, assoc_uuid)

    def _on_observation_double_clicked(self, table_item: QTableWidgetItem):
        row = table_item.row()
        payload = self._row_payload(self.observations_table, row)
        if isinstance(payload, EntryTreeItem):
            self.itemDoubleClicked.emit(payload, table_item.column())

    def load_imaged_moment_entry(self, entry: EntryTreeItem):
        """Synchronously refresh an imaged moment entry."""
        uuid = _uuid_from_payload(entry.payload)
        if not uuid:
            return

        selected_observation_uuid = None
        if (
            self._selected_observation is not None
            and self._selected_observation.is_observation
        ):
            selected_observation_uuid = self._selected_observation.observation.uuid

        previous_payload = (
            entry.payload if isinstance(entry.payload, ImagedMomentEntry) else None
        )
        meta = hydrate_imaged_moment_data(self._m3, uuid)
        if previous_payload is not None:
            meta.cached_image = previous_payload.cached_image
            meta.video_data = previous_payload.video_data

        self._apply_loaded_imaged_moment_entry(entry, meta, selected_observation_uuid)

    def _apply_loaded_imaged_moment_entry(
        self,
        entry: EntryTreeItem,
        meta: ImagedMomentEntry,
        selected_observation_uuid: Optional[str] = None,
    ):
        entry.payload = meta
        entry.clear_children()
        for obs in meta.observations:
            entry.add_child(EntryTreeItem(obs, parent=entry, tree=self))

        self._selected_observation = None
        if selected_observation_uuid is not None:
            for child in entry._children:
                if (
                    child.is_observation
                    and child.observation.uuid == selected_observation_uuid
                ):
                    self._selected_observation = child
                    break

        self._refresh_moment_row(entry)
        if self._selected_moment is entry:
            self._refresh_concept_filter_options(entry)
            self._populate_observations(entry)
            if self._selected_observation is not None:
                self._populate_associations(self._selected_observation)
                self.clear_observation_button.setEnabled(True)
            else:
                self.associations_table.setRowCount(0)
                self.clear_observation_button.setEnabled(False)
            self._emit_annotation_focus_changed()

    def load_imaged_moment_entry_async(
        self,
        entry: EntryTreeItem,
        on_error=None,
        on_finished=None,
    ):
        """Refresh an imaged moment entry without blocking the UI thread."""
        uuid = _uuid_from_payload(entry.payload)
        if not uuid:
            return

        selected_observation_uuid = None
        if (
            self._selected_observation is not None
            and self._selected_observation.is_observation
        ):
            selected_observation_uuid = self._selected_observation.observation.uuid

        previous_payload = (
            entry.payload if isinstance(entry.payload, ImagedMomentEntry) else None
        )

        run_async(
            self,
            hydrate_imaged_moment_data,
            self._m3,
            uuid,
            on_result=lambda meta: self._apply_loaded_imaged_moment_entry(
                entry,
                _copy_payload_cache(meta, previous_payload),
                selected_observation_uuid,
            ),
            on_error=on_error,
            on_finished=on_finished,
        )

    def _refresh_moment_row(self, entry: EntryTreeItem):
        for row in range(self.moments_table.rowCount()):
            row_payload = self._row_payload(self.moments_table, row)
            if row_payload is not entry:
                continue

            moment = entry.imaged_moment
            obs_count_cell = self.moments_table.item(row, 1)
            if obs_count_cell is not None:
                obs_count_cell.setText("{}".format(len(moment.observations)))

            status_text, tooltip, role = self._moment_status(moment)
            self._set_status_cell(
                self.moments_table, row, 2, status_text, tooltip, role
            )
            break

    def open_video_for_item(self, item: EntryTreeItem) -> None:
        if item.is_imaged_moment:
            im_item = item
        elif item.is_observation:
            parent_item = item.parent()
            if parent_item is None:
                raise ValueError(
                    "Could not resolve imaged moment for this observation."
                )
            im_item = parent_item
        else:
            raise ValueError("Selected item does not have an associated video.")

        moment = im_item.imaged_moment
        video_reference_uuid = moment.video_reference_uuid
        if not video_reference_uuid:
            raise ValueError("No video reference found for this imaged moment.")

        try:
            video_data = self._m3.get_video_by_video_reference_uuid(
                video_reference_uuid
            )
        except HTTPException:
            raise RuntimeError("Failed to fetch video data from M3.")

        video_references = video_data["video_references"]
        video_start_timestamp = video_data.get("start_timestamp", None)
        if not video_start_timestamp:
            raise ValueError("No video start timestamp found for this video reference.")

        try:
            video_start_datetime = datetime.strptime(
                video_start_timestamp, "%Y-%m-%dT%H:%M:%S.%fZ"
            )
        except ValueError:
            video_start_datetime = datetime.strptime(
                video_start_timestamp, "%Y-%m-%dT%H:%M:%SZ"
            )

        annotation_timedelta = None
        if moment.recorded_timestamp:
            try:
                recorded_datetime = datetime.strptime(
                    moment.recorded_timestamp, "%Y-%m-%dT%H:%M:%S.%fZ"
                )
            except ValueError:
                recorded_datetime = datetime.strptime(
                    moment.recorded_timestamp, "%Y-%m-%dT%H:%M:%SZ"
                )
            annotation_timedelta = recorded_datetime - video_start_datetime
        elif moment.timecode:
            hours, minutes, seconds, _ = map(int, moment.timecode.split(":"))
            annotation_timedelta = timedelta(
                hours=hours, minutes=minutes, seconds=seconds
            )
        elif moment.elapsed_time_millis is not None:
            annotation_timedelta = timedelta(milliseconds=moment.elapsed_time_millis)
        else:
            raise ValueError("No annotation timestamp found for this imaged moment.")

        video_url = None
        for video_reference in video_references:
            video_uri = video_reference.get("uri", None)
            if not video_uri:
                continue
            if video_uri.startswith("http") and video_uri.endswith(".mp4"):
                video_url = video_uri
                break

        if not video_url:
            raise ValueError("No valid video URL found for this video reference.")

        annotation_seconds = annotation_timedelta.total_seconds()
        video_url_fragment = video_url + "#t={},{}".format(
            annotation_seconds, annotation_seconds + 1e-3
        )
        webbrowser.open(video_url_fragment)

    def _handle_delete_shortcut(self):
        root = self.window()
        admin_mode = bool(getattr(root, "admin_mode", False))
        if not admin_mode:
            return

        observations_to_delete = [
            el for el in self.selectedItems() if el.is_observation
        ]
        if not observations_to_delete:
            return

        observation_uuids = [obs.observation.uuid for obs in observations_to_delete]
        res = QMessageBox.warning(
            self,
            "Confirm Observation Bulk Delete",
            "Are you sure you want to delete the following observation(s)?\n\t"
            + "\n\t".join(observation_uuids),
            buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if res == QMessageBox.StandardButton.Yes:
            for observation_uuid in observation_uuids:
                self._m3.delete_observation(observation_uuid)
            cast(Any, root).display_panel.image_view.reload_moment()

    def _handle_rename_shortcut(self):
        root = self.window()
        admin_mode = bool(getattr(root, "admin_mode", False))
        if not admin_mode:
            return

        observations_to_rename = [
            el for el in self.selectedItems() if el.is_observation
        ]
        if not observations_to_rename:
            return

        observation_uuids = [obs.observation.uuid for obs in observations_to_rename]

        dialog = QDialog(self)
        dialog.setWindowTitle("Rename Observations")
        dialog_layout = QVBoxLayout()
        dialog_layout.addWidget(QLabel("Enter new name for observation(s):"))
        concept_searchbar = ConceptSearchbar(dialog)
        try:
            root_any = cast(Any, root)
            concept_searchbar.set_concepts(
                root_any.search_panel.search_bar.get_concepts()
            )
        except Exception:
            concept_searchbar.set_concepts([])

        dialog_layout.addWidget(concept_searchbar)
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setEnabled(False)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        concept_to_set = None

        def on_concept_update(concept: str):
            nonlocal concept_to_set
            valid = concept in concept_searchbar.get_concepts()
            if ok_button is not None:
                ok_button.setEnabled(valid)
            if valid:
                concept_to_set = concept

        concept_searchbar.set_callback(on_concept_update)
        dialog_layout.addWidget(button_box)
        dialog.setLayout(dialog_layout)
        result = dialog.exec()

        if result != QDialog.DialogCode.Accepted or concept_to_set is None:
            return

        confirmed = QMessageBox.warning(
            self,
            "Confirm Observation Bulk Rename",
            f"Are you sure you want to rename the following observation(s) to {concept_to_set}?\n\t"
            + "\n\t".join(observation_uuids),
            buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if confirmed == QMessageBox.StandardButton.Yes:
            for observation_uuid in observation_uuids:
                self._m3.rename_observation(
                    observation_uuid,
                    concept_to_set,
                    cast(Any, root).observer,
                )
            cast(Any, root).display_panel.image_view.reload_moment()


def update_imaged_moment_entry(entry: EntryTreeItem):
    """Refresh in-memory status values and table rows for a moment entry."""
    if not entry.is_imaged_moment:
        return

    moment = entry.imaged_moment
    observations: List[ObservationEntry] = []
    localized = 0

    for idx in range(entry.childCount()):
        obs_item = entry.child(idx)
        if not obs_item.is_observation:
            continue

        obs = obs_item.observation
        obs.status = len(obs.boxes)
        if obs.boxes:
            localized += 1
        observations.append(obs)

    total = len(observations)
    moment.observations = observations
    if total <= 0:
        moment.status = "Empty"
    elif localized <= 0:
        moment.status = "Unlocalized (0/{})".format(total)
    elif localized < total:
        moment.status = "Partial ({}/{})".format(localized, total)
    else:
        moment.status = "Localized ({}/{})".format(localized, total)

    tree = entry.treeWidget()
    if tree is not None:
        tree._refresh_moment_row(entry)
        if tree._selected_moment is entry:
            tree._populate_observations(entry)


def _copy_payload_cache(
    meta: ImagedMomentEntry,
    previous_payload: Optional[ImagedMomentEntry],
) -> ImagedMomentEntry:
    if previous_payload is None:
        return meta
    meta.cached_image = previous_payload.cached_image
    meta.video_data = previous_payload.video_data
    return meta


def hydrate_imaged_moment_data(
    m3_service: M3Service, imaged_moment_uuid: str
) -> ImagedMomentEntry:
    """Fetch and normalize imaged moment metadata for browser rendering."""
    raw = m3_service.get_imaged_moment(imaged_moment_uuid)
    moment = ImagedMomentEntry.from_dict(raw)

    if moment.image_reference_uuid is None:
        logger.warning(
            "No valid image reference found for imaged moment {}".format(
                imaged_moment_uuid
            )
        )

    return moment
