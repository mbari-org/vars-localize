"""
Custom QLineEdit widget for searching concepts.
"""

from PyQt6.QtCore import Qt, pyqtSignal, QStringListModel
from PyQt6.QtWidgets import QLineEdit, QCompleter


class ConceptSearchbar(QLineEdit):
    conceptSelected = pyqtSignal()

    def __init__(self, parent=None):
        super(ConceptSearchbar, self).__init__(parent)

        self.setPlaceholderText("Search for concept")

        self._concept_model = QStringListModel([])
        self.concept_completer = QCompleter(self._concept_model, self)
        self.concept_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setCompleter(self.concept_completer)

    def set_concepts(self, concepts):
        """Update concept values used by the completer.

        Args:
            concepts: Sequence of concept names.
        """
        values = sorted(set(concepts or []))
        self._concept_model.setStringList(values)

    def get_concepts(self):
        return self._concept_model.stringList()

    def set_callback(self, func):
        """Set callback invoked when a concept is selected.

        Args:
            func: Activation callback.
        """
        self.concept_completer.activated.connect(func)
