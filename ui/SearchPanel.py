# SearchPanel.py (vars-localize)
from PyQt5.QtGui import QColor

from ui.EntryTree import ImagedMomentTree
from ui.JSONTree import JSONTree
from ui.Paginator import Paginator

__author__ = "Kevin Barnard"
__copyright__ = "Copyright 2019, Monterey Bay Aquarium Research Institute"
__credits__ = ["MBARI"]
__license__ = "GPL"
__maintainer__ = "Kevin Barnard"
__email__ = "kbarnard@mbari.org"
__doc__ = '''

Dock widget used to search for concepts and select frame grabs.

@author: __author__
@status: __status__
@license: __license__
'''
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDockWidget, QMessageBox, QVBoxLayout, QWidget, QHBoxLayout, QSpinBox, QScrollArea, QTextEdit, QLabel, \
    QSizePolicy, QDialog, QPushButton, QDialogButtonBox

from ui.ConceptSearchbar import ConceptSearchbar

from util.m3 import get_all_concepts, delete_observation, get_imaged_moment_uuids, rename_observation

from ui.EntryTree import EntryTreeItem


class SearchPanel(QDockWidget):

    def __init__(self, parent=None):
        super(SearchPanel, self).__init__(parent)

        self.setFeatures(QDockWidget.DockWidgetMovable |
                         QDockWidget.DockWidgetFloatable)
        self.setAllowedAreas(Qt.LeftDockWidgetArea)

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

        self.time_window = QSpinBox()
        self.time_window.setRange(0, 20000)

        self.top_bar.layout().addWidget(self.search_bar)
        self.top_bar.layout().addWidget(self.time_window)

        self.entry_tree = ImagedMomentTree()
        self.entry_tree.currentItemChanged.connect(self.parent().load_entry)
        self.entry_tree.itemDoubleClicked.connect(self.show_popup)
        self.entry_tree.time_window = 0
        self.time_window.valueChanged.connect(self.entry_tree.set_time_window)

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
        self.association_text.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
        self.association_area.setWidget(self.association_text)
        self.association_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.association_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self.contents.layout().addWidget(self.top_bar)
        self.contents.layout().addWidget(self.entry_tree, stretch=1)
        self.contents.layout().addWidget(self.paginator)
        self.contents.layout().addWidget(self.association_area)

        self.observer = ''

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
            QMessageBox.warning('Concept "" is invalid.'.format(concept))
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
        self.entry_tree.setCurrentIndex(self.entry_tree.indexBelow(self.entry_tree.currentIndex()))

    def select_prev(self):
        self.entry_tree.setCurrentIndex(self.entry_tree.indexAbove(self.entry_tree.currentIndex()))

    def show_popup(self, item: EntryTreeItem, col: int):
        if item is None or item.metadata['type'] == 'imaged_moment':
            return

        observation_uuid = item.metadata['uuid']

        editable = observation_uuid in self.entry_tree.editable_uuids
        admin_mode = self.parent().admin_mode

        dialog = QDialog()
        dialog.setMinimumSize(600, 300)
        dialog.setLayout(QVBoxLayout())
        dialog.setWindowTitle('Observation Information')
        dialog.setWindowFlag(Qt.WindowCloseButtonHint, False)

        json_tree = JSONTree(item.metadata)
        concept_widget = QWidget()
        concept_widget.setLayout(QHBoxLayout())
        delete_button = QPushButton('Delete')
        delete_button.setStyleSheet('background-color: darkred')
        delete_button.setDisabled(not editable and not admin_mode)
        delete_lock = False

        button_box = QDialogButtonBox(QDialogButtonBox.Save)
        button_box.setStyleSheet('background-color: darkgreen')
        button_box.accepted.connect(dialog.accept)

        def do_delete_observation():
            nonlocal dialog
            nonlocal delete_lock
            dialog.close()
            delete_observation(observation_uuid)
            delete_lock = True
            self.parent().display_panel.image_view.set_entry(item.parent())
            self.parent().display_panel.image_view.reload_moment()

        delete_button.pressed.connect(do_delete_observation)

        dialog.layout().addWidget(json_tree)
        dialog.layout().addWidget(concept_widget)
        dialog.layout().addWidget(delete_button)
        dialog.layout().addWidget(button_box)

        concept_field = ConceptSearchbar()
        concept_field.setText(item.metadata['concept'])
        concept_field.setDisabled(not editable and not admin_mode)

        concept_widget.layout().addWidget(QLabel('Concept:'))
        concept_widget.layout().addWidget(concept_field)

        concept_before = concept_field.text()

        dialog.setModal(True)
        dialog.exec_()

        concept_after = concept_field.text()
        if not delete_lock and concept_after != concept_before:  # Rename the observation
            rename_observation(observation_uuid, concept_after, self.observer)
            moment = item.parent()
            self.entry_tree.load_imaged_moment_entry(moment)
            self.parent().display_panel.image_view.set_entry(moment)
