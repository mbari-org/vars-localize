"""
Dock widget used to search for concepts and select frame grabs.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDockWidget,
    QMessageBox,
    QVBoxLayout,
    QWidget,
    QHBoxLayout,
    QScrollArea,
    QLabel,
    QSizePolicy,
    QDialog,
    QPushButton,
    QDialogButtonBox,
    QSplitter,
)

from vars_localize.ui.EntryTree import ImagedMomentTree
from vars_localize.ui.JSONTree import JSONTree
from vars_localize.ui.Paginator import Paginator
from vars_localize.ui.ConceptSearchbar import ConceptSearchbar
from vars_localize.util.m3 import (
    get_all_concepts,
    delete_observation,
    get_imaged_moment_uuids,
    rename_observation,
)
from vars_localize.ui.EntryTree import EntryTreeItem


class SearchPanel(QDockWidget):
    def __init__(self, parent=None):
        super(SearchPanel, self).__init__(parent)

        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea)

        self.contents = QWidget()
        self.contents.setMinimumSize(400, 300)
        self.contents.setLayout(QVBoxLayout())
        self.setWidget(self.contents)

        self.concept = None
        self.uuids = []

        self.top_bar = QWidget()
        self.top_bar.setLayout(QHBoxLayout())

        self.search_bar = ConceptSearchbar()
        self.search_bar.set_callback(self.concept_selected)

        self.top_bar.layout().addWidget(self.search_bar)

        self.bottom_splitter = QSplitter()
        self.bottom_splitter.setOrientation(Qt.Orientation.Vertical)

        self.entry_widget = QWidget()
        self.entry_widget.setLayout(QVBoxLayout())

        self.paginator = Paginator()
        self.paginator.set_limit(25)
        self.paginator.left_button.setDisabled(True)
        self.paginator.right_button.setDisabled(True)
        self.paginator.left_signal.connect(self.load_page)
        self.paginator.right_signal.connect(self.load_page)
        self.paginator.jump_signal.connect(self.load_page)

        self.association_area = QScrollArea()
        self.association_area.setWidgetResizable(True)
        self.association_text = QLabel()
        self.association_text.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum
        )
        self.association_area.setWidget(self.association_text)
        self.association_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.association_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        self.entry_tree = ImagedMomentTree(self.association_text, parent=self)
        self.entry_tree.currentItemChanged.connect(self.parent().load_entry)
        self.entry_tree.itemDoubleClicked.connect(self.show_popup)

        self.contents.layout().addWidget(self.top_bar)
        self.contents.layout().addWidget(self.bottom_splitter)
        self.entry_widget.layout().addWidget(self.entry_tree, stretch=1)
        self.entry_widget.layout().addWidget(self.paginator)
        self.bottom_splitter.addWidget(self.entry_widget)
        self.bottom_splitter.addWidget(self.association_area)

        self.observer = ""

    def concept_selected(self, concept):
        if concept == self.concept:  # No change, don't update results
            return
        else:
            self.load_concept(concept)

    def set_uuids(self, uuids):
        # Update the UUIDs
        self.uuids = uuids

        # Update the paginator
        self.paginator.set_offset(0)
        self.paginator.set_count(len(uuids))

    def load_concept(self, concept):
        if concept not in get_all_concepts():
            QMessageBox.warning('Concept "" is invalid.')
            return

        self.concept = concept

        # Clear the display panel
        self.parent().display_panel.image_view.set_pixmap(None)
        self.parent().display_panel.image_view.redraw()

        # Fetch the list of imaged moment UUIDs for the concept (with images)
        concept_uuids = get_imaged_moment_uuids(self.concept)
        self.set_uuids(concept_uuids)

        # Load the first page
        self.load_page()

    def load_page(self):
        # Specify UUIDs in page from paginator slice
        page_uuids = self.uuids[self.paginator.slice]

        # Do the actual load (takes some time)
        self.entry_tree.load_uuids(page_uuids)

    def select_next(self):
        self.entry_tree.setCurrentIndex(
            self.entry_tree.indexBelow(self.entry_tree.currentIndex())
        )

    def select_prev(self):
        self.entry_tree.setCurrentIndex(
            self.entry_tree.indexAbove(self.entry_tree.currentIndex())
        )

    def select_entry(self, item: EntryTreeItem):
        self.entry_tree.setCurrentItem(item)

    def show_popup(self, item: EntryTreeItem, col: int):
        if item is None or item.metadata["type"] == "imaged_moment":
            return

        observation_uuid = item.metadata["uuid"]

        editable = observation_uuid in self.entry_tree.editable_uuids
        admin_mode = self.parent().admin_mode

        dialog = QDialog()
        dialog.setMinimumSize(600, 300)
        dialog.setLayout(QVBoxLayout())
        dialog.setWindowTitle("Observation Information")
        dialog.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)

        json_tree = JSONTree(item.metadata)
        concept_widget = QWidget()
        concept_widget.setLayout(QHBoxLayout())
        delete_button = QPushButton("Delete")
        delete_button.setStyleSheet("background-color: darkred")
        delete_button.setDisabled(not editable and not admin_mode)
        delete_lock = False

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save)
        button_box.setStyleSheet("background-color: darkgreen")
        button_box.accepted.connect(dialog.accept)

        def do_delete_observation():
            nonlocal dialog
            nonlocal delete_lock
            dialog.close()
            delete_observation(observation_uuid)
            delete_lock = True
            self.parent().display_panel.image_view.set_entry(item.parent())
            self.parent().display_panel.image_view.reload_moment()

        def set_dialog_saveable(saveable: bool):
            button_box.button(QDialogButtonBox.StandardButton.Save).setDisabled(
                not saveable
            )

        set_dialog_saveable(False)

        delete_button.pressed.connect(do_delete_observation)

        dialog.layout().addWidget(json_tree)
        dialog.layout().addWidget(concept_widget)
        dialog.layout().addWidget(delete_button)
        dialog.layout().addWidget(button_box)

        concept_field = ConceptSearchbar()
        concept_field.setText(item.metadata["concept"])
        concept_field.setDisabled(not editable and not admin_mode)
        concept_field.textChanged.connect(lambda: set_dialog_saveable(False))
        concept_field.set_callback(lambda: set_dialog_saveable(True))

        concept_widget.layout().addWidget(QLabel("Concept:"))
        concept_widget.layout().addWidget(concept_field)

        concept_before = concept_field.text()

        dialog.setModal(True)
        accepted = dialog.exec()

        concept_after = concept_field.text()
        if (
            accepted and not delete_lock and concept_after != concept_before
        ):  # Rename the observation
            rename_observation(observation_uuid, concept_after, self.observer)
            moment = item.parent()
            self.entry_tree.load_imaged_moment_entry(moment)
            self.parent().display_panel.image_view.set_entry(moment)

    def open_video(self):
        # Get current item
        current_item: EntryTreeItem = self.entry_tree.currentItem()

        # Open the video
        if current_item:
            self.entry_tree.open_video_for_item(current_item)
