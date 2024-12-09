"""
Container widget used do display images + localizations and process input.
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout

from vars_localize.ui.ImageView import ImageView
from vars_localize.ui.EntryTree import EntryTreeItem


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
