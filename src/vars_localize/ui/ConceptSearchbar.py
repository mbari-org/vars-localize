"""
Custom QLineEdit widget for searching concepts.
"""

from bisect import bisect_left

from PyQt6.QtCore import QStringListModel, Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QCompleter, QLineEdit

_NO_COMPLETE_MODIFIERS = (
    Qt.KeyboardModifier.ControlModifier
    | Qt.KeyboardModifier.AltModifier
    | Qt.KeyboardModifier.MetaModifier
)


class ConceptSearchbar(QLineEdit):
    conceptSelected = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setPlaceholderText("Search for concept")

        self._concept_model = QStringListModel([])
        self._lower_index: list[tuple[str, str]] = []
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
        self._lower_index = sorted((c.lower(), c) for c in values)

    def get_concepts(self):
        return self._concept_model.stringList()

    def find_concept(self, text: str) -> str:
        """Return the correctly-cased concept matching *text* exactly
        (case-insensitive, whitespace-trimmed), or an empty string."""
        key = (text or "").strip().lower()
        i = bisect_left(self._lower_index, (key,))
        if i < len(self._lower_index) and self._lower_index[i][0] == key:
            return self._lower_index[i][1]
        return ""

    def first_prefix_match(self, prefix: str) -> str:
        """Return the first concept (case-insensitive order) starting with
        *prefix*, or an empty string."""
        key = (prefix or "").lower()
        if not key:
            return ""
        i = bisect_left(self._lower_index, (key,))
        if i < len(self._lower_index) and self._lower_index[i][0].startswith(key):
            return self._lower_index[i][1]
        return ""

    def keyPressEvent(self, event: QKeyEvent):
        super().keyPressEvent(event)
        text = event.text()
        if (
            text
            and text.isprintable()
            and not (event.modifiers() & _NO_COMPLETE_MODIFIERS)
        ):
            self._complete_inline()

    def _complete_inline(self):
        """Fill in the best matching concept after the cursor and select the
        untyped remainder, so Enter accepts it and further typing replaces it.
        The typed portion is re-cased to match the concept name."""
        typed = self.text()
        if self.hasSelectedText() or self.cursorPosition() != len(typed):
            return
        match = self.first_prefix_match(typed)
        if not match:
            return
        if match != typed:
            self.setText(match)
        self.setSelection(len(typed), len(match) - len(typed))

    def set_callback(self, func):
        """Set callback invoked when a concept is selected.

        Args:
            func: Activation callback.
        """
        self.concept_completer.activated.connect(func)
