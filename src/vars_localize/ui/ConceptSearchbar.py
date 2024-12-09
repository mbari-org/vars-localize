"""
Custom QLineEdit widget for searching concepts.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QLineEdit, QCompleter

from vars_localize.util import m3


class ConceptSearchbar(QLineEdit):
    conceptSelected = pyqtSignal()

    def __init__(self, parent=None):
        super(ConceptSearchbar, self).__init__(parent)

        self.setPlaceholderText("Search for concept")

        self.concept_completer = QCompleter(m3.get_all_concepts())
        self.concept_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setCompleter(self.concept_completer)

    def set_callback(self, func):
        """
        Set callback on completer activation (concept selected)
        :param func: Activation callback
        :return: None
        """
        self.concept_completer.activated.connect(func)
