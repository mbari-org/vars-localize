# ConceptSearchbar.py (vars-localize)
import util.requests

__author__ = "Kevin Barnard"
__copyright__ = "Copyright 2019, Monterey Bay Aquarium Research Institute"
__credits__ = ["MBARI"]
__license__ = "GPL"
__maintainer__ = "Kevin Barnard"
__email__ = "kbarnard@mbari.org"
__doc__ = '''

QLineEdit custom widget for searching concepts.

@author: __author__
@status: __status__
@license: __license__
'''
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QLineEdit, QCompleter

from util import utils


class ConceptSearchbar(QLineEdit):

    conceptSelected = pyqtSignal()

    def __init__(self, parent=None):
        super(ConceptSearchbar, self).__init__(parent)

        self.setPlaceholderText('Search for concept')

        self.concept_completer = QCompleter(util.requests.get_all_concepts())
        self.concept_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.setCompleter(self.concept_completer)

    def set_callback(self, func):
        """
        Set callback on completer activation (concept selected)
        :param func: Activation callback
        :return: None
        """
        self.concept_completer.activated.connect(func)
