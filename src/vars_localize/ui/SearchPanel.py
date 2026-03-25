"""Dock widget used to search for concepts and select frame grabs."""

from datetime import datetime
from typing import Any, Optional, cast

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from vars_localize.models import ObservationEntry
from vars_localize.ui.ConceptSearchbar import ConceptSearchbar
from vars_localize.ui.EntryTree import (
    EntryTreeItem,
    ImagedMomentTree,
    hydrate_imaged_moment_data,
)
from vars_localize.ui.JSONTree import JSONTree
from vars_localize.ui.Paginator import Paginator
from vars_localize.util.qt_async import run_async
from vars_localize.util.utils import center_window


SEARCH_MODE_ORDER = [
    "concept",
    "imaged_moment_uuid",
    "image_reference_uuid",
    "video_reference_uuid",
]

SEARCH_MODE_CONFIG = {
    "concept": {
        "label": "Concept",
        "placeholder": "Search by concept",
        "hint": "Use concept autocomplete to load all matching imaged moments.",
    },
    "imaged_moment_uuid": {
        "label": "Imaged Moment UUID",
        "placeholder": "Paste one UUID or comma-separated UUIDs",
        "hint": "Directly open specific imaged moment UUIDs.",
    },
    "image_reference_uuid": {
        "label": "Image Reference UUID",
        "placeholder": "Paste one UUID or comma-separated UUIDs",
        "hint": "Resolve image reference UUIDs into imaged moments.",
    },
    "video_reference_uuid": {
        "label": "Video Reference UUID",
        "placeholder": "Paste one UUID or comma-separated UUIDs",
        "hint": "Resolve video reference UUIDs into timeline-sorted imaged moments.",
    },
}


class SearchPanel(QDockWidget):
    def __init__(self, app_state, m3_service, page_size: int = 25, parent=None):
        super(SearchPanel, self).__init__(parent)

        self._state = app_state
        self._m3 = m3_service

        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea)

        self.contents = QWidget()
        self.contents.setMinimumSize(430, 320)
        self._contents_layout = QVBoxLayout()
        self._contents_layout.setContentsMargins(4, 4, 4, 4)
        self._contents_layout.setSpacing(6)
        self.contents.setLayout(self._contents_layout)
        self.setWidget(self.contents)

        self.concept = None
        self.uuids = []
        self.search_mode = "concept"
        self.active_query = ""
        self._loading_ops = 0
        self._request_seq = 0
        self._active_search_request_id = 0
        self._active_page_request_id = 0

        self.controls_card = QFrame()
        self.controls_card.setObjectName("controlsCard")
        self.controls_card.setFrameShape(QFrame.Shape.StyledPanel)
        self._controls_layout = QVBoxLayout()
        self._controls_layout.setContentsMargins(8, 8, 8, 8)
        self._controls_layout.setSpacing(8)
        self.controls_card.setLayout(self._controls_layout)

        self.mode_row = QWidget()
        self._mode_row_layout = QHBoxLayout()
        self._mode_row_layout.setContentsMargins(0, 0, 0, 0)
        self._mode_row_layout.setSpacing(6)
        self.mode_row.setLayout(self._mode_row_layout)

        self.mode_combo = QComboBox()
        self.mode_combo.setMinimumWidth(180)
        self.mode_combo.setToolTip("Choose how to interpret the search query")
        for mode_key in SEARCH_MODE_ORDER:
            self.mode_combo.addItem(SEARCH_MODE_CONFIG[mode_key]["label"], mode_key)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)

        self.mode_hint_button = QToolButton()
        self.mode_hint_button.setText("?")
        self.mode_hint_button.setToolTipDuration(10000)
        self.mode_hint_button.setToolTip("Search mode help")
        self.mode_hint_button.setFixedWidth(24)

        self._mode_row_layout.addWidget(QLabel("Mode"))
        self._mode_row_layout.addWidget(self.mode_combo)
        self._mode_row_layout.addWidget(self.mode_hint_button)
        self._mode_row_layout.addStretch(1)

        self.search_row = QWidget()
        self._search_row_layout = QHBoxLayout()
        self._search_row_layout.setContentsMargins(0, 0, 0, 0)
        self.search_row.setLayout(self._search_row_layout)

        self.search_bar = ConceptSearchbar()
        self.search_bar.set_callback(self.concept_selected)
        self.search_bar.returnPressed.connect(self._search_from_input)

        self.search_button = QPushButton("Go")
        self.search_button.setObjectName("primaryButton")
        self.search_button.pressed.connect(self._search_from_input)
        self.search_button.setToolTip("Execute search")

        self.clear_button = QPushButton("Reset")
        self.clear_button.pressed.connect(self._clear_results)
        self.clear_button.setToolTip("Clear query and loaded results")

        self.open_video_button = QPushButton("Open Video")
        self.open_video_button.pressed.connect(self.open_video)
        self.open_video_button.setToolTip(
            "Open source video at the selected annotation time"
        )
        self.open_video_button.setDisabled(True)

        self._search_row_layout.addWidget(self.search_bar, 1)
        self._search_row_layout.addWidget(self.search_button)
        self._search_row_layout.addWidget(self.clear_button)
        self._search_row_layout.addWidget(self.open_video_button)

        self.status_row = QWidget()
        self._status_row_layout = QHBoxLayout()
        self._status_row_layout.setContentsMargins(0, 0, 0, 0)
        self.status_row.setLayout(self._status_row_layout)

        self.results_label = QLabel("No results loaded")
        self.results_label.setObjectName("secondaryText")

        self.loading_bar = QProgressBar()
        self.loading_bar.setRange(0, 0)
        self.loading_bar.setTextVisible(False)
        self.loading_bar.setMaximumHeight(8)
        self.loading_bar.setVisible(False)

        self._status_row_layout.addWidget(self.results_label, 1)
        self._status_row_layout.addWidget(self.loading_bar)

        self._controls_layout.addWidget(self.mode_row)
        self._controls_layout.addWidget(self.search_row)
        self._controls_layout.addWidget(self.status_row)

        self.entry_tree = ImagedMomentTree(self._m3, parent=self)
        root = cast(Any, self.parent())
        self.entry_tree.currentItemChanged.connect(root.load_entry)
        self.entry_tree.currentItemChanged.connect(
            lambda current, _: self._sync_video_button_state(current)
        )
        self.entry_tree.associationActivated.connect(self._on_association_activated)
        self.entry_tree.itemDoubleClicked.connect(self.show_popup)

        self.paginator = Paginator()
        self.paginator.set_limit(page_size)
        self.paginator.left_button.setDisabled(True)
        self.paginator.right_button.setDisabled(True)
        self.paginator.left_signal.connect(self.load_page)
        self.paginator.right_signal.connect(self.load_page)
        self.paginator.jump_signal.connect(self.load_page)

        self._contents_layout.addWidget(self.controls_card)
        self._contents_layout.addWidget(self.entry_tree, 1)
        self._contents_layout.addWidget(self.paginator)

        self.observer = ""

        self._state.observerChanged.connect(self._on_observer_changed)
        self._state.conceptsChanged.connect(self.search_bar.set_concepts)
        self._state.loadingChanged.connect(self._set_loading_state)
        self._state.conceptChanged.connect(lambda _: self._update_results_label())
        self._state.uuidsChanged.connect(lambda _: self._update_results_label())

        self.set_search_mode("concept")
        self._load_concepts_async()

    def set_page_size(self, page_size: int):
        self.paginator.set_limit(page_size)
        if self.uuids:
            self.load_page()

    def _on_observer_changed(self, observer: str):
        self.observer = observer

    def _set_loading_state(self, loading: bool):
        self.loading_bar.setVisible(loading)
        self.search_button.setDisabled(loading)
        self.clear_button.setDisabled(loading)
        self.search_bar.setDisabled(loading)
        self.mode_combo.setDisabled(loading)
        self.mode_hint_button.setDisabled(loading)
        self.paginator.left_button.setDisabled(loading)
        self.paginator.right_button.setDisabled(loading)
        self.open_video_button.setDisabled(
            loading or not self._video_available_for_item(self.entry_tree.currentItem())
        )
        if not loading:
            self.paginator.update_nav()

    def _video_available_for_item(self, item: Optional[EntryTreeItem] = None) -> bool:
        if item is None:
            return False

        if item.is_imaged_moment:
            return bool(item.imaged_moment.video_reference_uuid)

        if item.is_observation:
            parent = item.parent()
            return bool(
                parent
                and parent.is_imaged_moment
                and parent.imaged_moment.video_reference_uuid
            )

        return False

    def _sync_video_button_state(self, current: Optional[EntryTreeItem] = None):
        if self._state.loading:
            self.open_video_button.setDisabled(True)
            return
        self.open_video_button.setDisabled(not self._video_available_for_item(current))

    def _show_error(self, message: str):
        QMessageBox.critical(self, "Operation Failed", message)

    def _begin_loading(self):
        self._loading_ops += 1
        if self._loading_ops == 1:
            self._state.loading = True

    def _end_loading(self):
        self._loading_ops = max(0, self._loading_ops - 1)
        if self._loading_ops == 0:
            self._state.loading = False

    def _next_request_id(self) -> int:
        self._request_seq += 1
        return self._request_seq

    def _update_results_label(self):
        total = len(self.uuids)
        mode_label = SEARCH_MODE_CONFIG[self.search_mode]["label"]
        if not self.active_query:
            self.results_label.setText("No results loaded")
            return
        self.results_label.setText(
            "{}: {} | {} result{}".format(
                mode_label,
                self.active_query,
                total,
                "" if total == 1 else "s",
            )
        )

    def set_search_mode(self, mode: str):
        if mode not in SEARCH_MODE_CONFIG:
            return

        self.search_mode = mode
        config = SEARCH_MODE_CONFIG[mode]
        self.search_bar.setPlaceholderText(config["placeholder"])
        self.search_bar.setToolTip(config["hint"])
        self.mode_hint_button.setToolTip(config["hint"])

        target_index = self.mode_combo.findData(mode)
        if target_index >= 0 and self.mode_combo.currentIndex() != target_index:
            self.mode_combo.setCurrentIndex(target_index)

    def _on_mode_changed(self, index: int):
        mode = self.mode_combo.itemData(index)
        if isinstance(mode, str):
            self.set_search_mode(mode)

    def _parse_query_values(self, query: str):
        values = [val.strip() for val in query.split(",")]
        values = [val for val in values if val]
        return list(dict.fromkeys(values))

    def _resolve_imaged_moments_by_image_reference(self, uuids):
        imaged_moment_uuids = []
        for image_reference_uuid in uuids:
            res = self._m3.get_imaged_moments_by_image_reference(image_reference_uuid)
            if not res:
                continue
            imaged_moment_uuids.extend(
                [
                    item["imaged_moment_uuid"]
                    for item in res
                    if "imaged_moment_uuid" in item
                ]
            )
        return list(dict.fromkeys(imaged_moment_uuids))

    def _resolve_imaged_moments_by_video_reference(self, uuids):
        timestamp_uuid_tuples = set()
        for video_reference_uuid in uuids:
            res = self._m3.get_annotations_by_video_reference(video_reference_uuid)
            if not res:
                continue

            for item in res:
                if "imaged_moment_uuid" not in item:
                    continue
                timestamp = datetime.now()
                if "recorded_timestamp" in item:
                    try:
                        timestamp = datetime.strptime(
                            item["recorded_timestamp"], "%Y-%m-%dT%H:%M:%S.%fZ"
                        )
                    except ValueError:
                        timestamp = datetime.strptime(
                            item["recorded_timestamp"], "%Y-%m-%dT%H:%M:%SZ"
                        )
                timestamp_uuid_tuples.add((timestamp, item["imaged_moment_uuid"]))

        return [item[1] for item in sorted(timestamp_uuid_tuples)]

    def _resolve_uuids(self, mode: str, query: str):
        values = self._parse_query_values(query)
        if not values:
            return []

        if mode == "imaged_moment_uuid":
            return values
        if mode == "image_reference_uuid":
            return self._resolve_imaged_moments_by_image_reference(values)
        if mode == "video_reference_uuid":
            return self._resolve_imaged_moments_by_video_reference(values)
        return []

    def _set_search_results(self, mode: str, query: str, uuids):
        self.active_query = query
        if mode == "concept":
            self.concept = query
            self._state.concept = query
        else:
            self.concept = None
            self._state.concept = ""

        self.set_uuids(uuids)
        self.load_page()

    def _search_from_input(self):
        query = self.search_bar.text().strip()
        if not query:
            return
        mode = self.search_mode
        if mode == "concept":
            self.load_concept(query)
            return

        root = cast(Any, self.parent())
        root.display_panel.image_view.set_pixmap(None)
        root.display_panel.image_view.redraw()
        request_id = self._next_request_id()
        self._active_search_request_id = request_id
        self._begin_loading()
        run_async(
            self,
            self._resolve_uuids,
            mode,
            query,
            on_result=lambda uuids: (
                self._set_search_results(mode, query, uuids)
                if request_id == self._active_search_request_id
                else None
            ),
            on_error=lambda err: self._show_error(
                "Failed to resolve {} search.\n\n{}".format(
                    SEARCH_MODE_CONFIG[mode]["label"],
                    err,
                )
            )
            if request_id == self._active_search_request_id
            else None,
            on_finished=self._end_loading,
        )

    def _clear_results(self):
        self.concept = None
        self.active_query = ""
        self._state.concept = ""
        self.search_bar.clear()
        self.entry_tree.clear()
        root = cast(Any, self.parent())
        root.display_panel.image_view.set_pixmap(None)
        root.display_panel.image_view.redraw()
        self.set_uuids([])
        self._sync_video_button_state(None)
        self._update_results_label()

    def _load_concepts_async(self):
        self._begin_loading()

        def _on_result(concepts):
            self._state.concepts = concepts

        run_async(
            self,
            self._m3.get_all_concepts,
            on_result=_on_result,
            on_error=lambda err: self._show_error(
                "Failed to load concepts from M3.\n\n{}".format(err)
            ),
            on_finished=self._end_loading,
        )

    def concept_selected(self, concept):
        self.set_search_mode("concept")
        if concept == self.concept and self.search_mode == "concept":
            return
        self.load_concept(concept)

    def set_uuids(self, uuids):
        self.uuids = uuids
        self._state.uuids = uuids

        self.paginator.set_offset(0)
        self.paginator.set_count(len(uuids))
        self._sync_video_button_state(self.entry_tree.currentItem())
        self._update_results_label()

    def load_concept(self, concept):
        concept = (concept or "").strip()
        if concept not in self.search_bar.get_concepts():
            QMessageBox.warning(
                self, "Invalid Concept", 'Concept "{}" is invalid.'.format(concept)
            )
            return

        self.set_search_mode("concept")
        self.concept = concept

        root = cast(Any, self.parent())
        root.display_panel.image_view.set_pixmap(None)
        root.display_panel.image_view.redraw()

        request_id = self._next_request_id()
        self._active_search_request_id = request_id
        self._begin_loading()

        def _on_result(concept_uuids):
            if request_id != self._active_search_request_id:
                return
            self._set_search_results("concept", concept, concept_uuids)

        run_async(
            self,
            self._m3.get_imaged_moment_uuids,
            concept,
            on_result=_on_result,
            on_error=lambda err: self._show_error(
                "Failed to load imaged moments for concept {}.\n\n{}".format(
                    concept, err
                )
            )
            if request_id == self._active_search_request_id
            else None,
            on_finished=self._end_loading,
        )

    def load_page(self):
        page_uuids = self.uuids[self.paginator.slice]

        request_id = self._next_request_id()
        self._active_page_request_id = request_id
        self._begin_loading()

        def _fetch_page_data():
            return [hydrate_imaged_moment_data(self._m3, uuid) for uuid in page_uuids]

        run_async(
            self,
            _fetch_page_data,
            on_result=lambda data: self.entry_tree.load_page_data(data)
            if request_id == self._active_page_request_id
            else None,
            on_error=lambda err: self._show_error(
                "Failed to load imaged moment page data.\n\n{}".format(err)
            )
            if request_id == self._active_page_request_id
            else None,
            on_finished=self._end_loading,
        )

    def select_next(self):
        self.entry_tree.select_next_item()

    def select_prev(self):
        self.entry_tree.select_prev_item()

    def select_entry(self, item: EntryTreeItem):
        self.entry_tree.setCurrentItem(item)

    def _on_association_activated(self, observation_uuid: str, association_uuid: str):
        root = cast(Any, self.parent())
        try:
            root.display_panel.image_view.focus_association_box(
                observation_uuid, association_uuid
            )
        except LookupError as exc:
            self._show_error(str(exc))

    def show_popup(self, item: EntryTreeItem, col: int):
        if item is None or not item.is_observation:
            return

        observation: ObservationEntry = item.observation
        observation_uuid = observation.uuid

        editable = observation_uuid in self.entry_tree.editable_uuids
        root = cast(Any, self.parent())
        admin_mode = root.admin_mode

        dialog = QDialog(root)
        dialog.setMinimumSize(600, 300)
        dialog.setLayout(QVBoxLayout())
        dialog.setWindowTitle("Observation Information")
        dialog.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)

        json_tree = JSONTree(observation.to_dict())
        concept_widget = QWidget()
        concept_widget.setLayout(QHBoxLayout())
        delete_button = QPushButton("Delete")
        delete_button.setObjectName("dangerButton")
        delete_button.setDisabled(not editable and not admin_mode)
        delete_lock = False

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save)
        button_box.accepted.connect(dialog.accept)

        def do_delete_observation():
            nonlocal dialog
            nonlocal delete_lock
            dialog.close()

            def _on_done(_):
                nonlocal delete_lock
                delete_lock = True
                parent_item = item.parent()
                if isinstance(parent_item, EntryTreeItem):
                    root.display_panel.image_view.set_entry(parent_item)
                root.display_panel.image_view.reload_moment()

            run_async(
                self,
                self._m3.delete_observation,
                observation_uuid,
                on_result=_on_done,
                on_error=lambda err: self._show_error(
                    "Failed to delete observation.\n\n{}".format(err)
                ),
            )

        def set_dialog_saveable(saveable: bool):
            save_button = button_box.button(QDialogButtonBox.StandardButton.Save)
            if save_button is not None:
                save_button.setDisabled(not saveable)

        set_dialog_saveable(False)

        delete_button.pressed.connect(do_delete_observation)

        dialog_layout = cast(QVBoxLayout, dialog.layout())
        dialog_layout.addWidget(json_tree)
        dialog_layout.addWidget(concept_widget)
        dialog_layout.addWidget(delete_button)
        dialog_layout.addWidget(button_box)

        concept_field = ConceptSearchbar()
        concept_field.set_concepts(self.search_bar.get_concepts())
        concept_field.setText(observation.concept)
        concept_field.setDisabled(not editable and not admin_mode)
        concept_field.textChanged.connect(lambda _: set_dialog_saveable(False))
        concept_field.set_callback(lambda _: set_dialog_saveable(True))

        concept_layout = cast(QHBoxLayout, concept_widget.layout())
        concept_layout.addWidget(QLabel("Concept:"))
        concept_layout.addWidget(concept_field)

        concept_before = concept_field.text()

        dialog.setModal(True)
        center_window(dialog, root)
        accepted = dialog.exec()

        concept_after = concept_field.text()
        if accepted and not delete_lock and concept_after != concept_before:

            def _on_done(_):
                moment = item.parent()
                if isinstance(moment, EntryTreeItem):
                    self.entry_tree.load_imaged_moment_entry_async(
                        moment,
                        on_error=lambda err: self._show_error(
                            "Failed to refresh imaged moment.\n\n{}".format(err)
                        ),
                        on_finished=lambda: root.display_panel.image_view.set_entry(
                            moment
                        ),
                    )

            run_async(
                self,
                self._m3.rename_observation,
                observation_uuid,
                concept_after,
                self.observer,
                on_result=_on_done,
                on_error=lambda err: self._show_error(
                    "Failed to rename observation.\n\n{}".format(err)
                ),
            )

    def open_video(self):
        current_item = self.entry_tree.currentItem()
        if isinstance(current_item, EntryTreeItem):
            try:
                self.entry_tree.open_video_for_item(current_item)
            except Exception as exc:
                self._show_error(str(exc))
