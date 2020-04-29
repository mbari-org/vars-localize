# SearchPanel.py (vars-localize)
from ui.EntryTree import ImagedMomentTree, EntryTreeItem
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
from PyQt5.QtWidgets import QDockWidget, QVBoxLayout, QWidget, QHBoxLayout, QSpinBox, QLabel

from ui.ConceptSearchbar import ConceptSearchbar

from util.requests import concept_count, get_all_concepts


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
        self.entry_tree.time_window = 0
        self.time_window.valueChanged.connect(self.entry_tree.set_time_window)

        self.paginator = Paginator()
        self.paginator.set_limit(25)
        self.paginator.left_signal.connect(self.load_page)
        self.paginator.right_signal.connect(self.load_page)

        self.contents.layout().addWidget(self.top_bar)
        self.contents.layout().addWidget(self.entry_tree, stretch=1)
        self.contents.layout().addWidget(self.paginator)

    def concept_selected(self, concept):
        if concept in get_all_concepts():
            self.concept = concept
            self.load_results()

    def load_results(self):
        self.parent().display_panel.image_view.set_pixmap(None)
        self.paginator.set_offset(0)
        self.load_page()
        self.parent().display_panel.image_view.redraw()

    def load_page(self):
        if self.concept:
            self.entry_tree.query(self.concept, self.paginator.offset, self.paginator.limit)  # Get imaged moments
            self.paginator.set_count(len(self.entry_tree.loaded_uuids))  # Set count

    def select_next(self):
        self.entry_tree.setCurrentIndex(self.entry_tree.indexBelow(self.entry_tree.currentIndex()))

    def select_prev(self):
        self.entry_tree.setCurrentIndex(self.entry_tree.indexAbove(self.entry_tree.currentIndex()))
