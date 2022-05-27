from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QLineEdit, QCompleter

from vars_localize.lib import m3


class ConceptSearchbar(QLineEdit):
    """
    QLineEdit custom widget for searching concepts.
    """

    conceptSelected = pyqtSignal()

    def __init__(self, parent=None):
        super(ConceptSearchbar, self).__init__(parent)

        self.setPlaceholderText('Search for concept')

        self.concept_completer = QCompleter(m3.get_all_concepts())
        self.concept_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.setCompleter(self.concept_completer)

    def set_callback(self, func):
        """
        Set callback on completer activation (concept selected)
        :param func: Activation callback
        :return: None
        """
        self.concept_completer.activated.connect(func)
