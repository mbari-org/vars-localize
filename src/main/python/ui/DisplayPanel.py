# DisplayPanel.py (vars-localize)

__author__ = "Kevin Barnard"
__copyright__ = "Copyright 2019, Monterey Bay Aquarium Research Institute"
__credits__ = ["MBARI"]
__license__ = "GPL"
__maintainer__ = "Kevin Barnard"
__email__ = "kbarnard@mbari.org"
__doc__ = '''

Container widget used do display images + localizations and process input.

@author: __author__
@status: __status__
@license: __license__
'''
from PyQt5.QtWidgets import QWidget, QVBoxLayout

from ui.ImageView import ImageView
from ui.EntryTree import EntryTreeItem


class DisplayPanel(QWidget):

    def __init__(self, parent=None):
        super(DisplayPanel, self).__init__(parent)

        self.setLayout(QVBoxLayout())

        self.image_view = ImageView(parent=self)

        self.layout().addWidget(self.image_view, stretch=1)

    def load_entry(self, entry: EntryTreeItem):
        """
        Load an entry into the image view, redraw
        :param entry: Concept entry
        :return: None
        """
        self.image_view.set_entry(entry)
        self.image_view.redraw()
