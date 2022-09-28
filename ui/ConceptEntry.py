# ConceptEntry.py (vars-localize)

__author__ = "Kevin Barnard"
__copyright__ = "Copyright 2019, Monterey Bay Aquarium Research Institute"
__credits__ = ["MBARI"]
__license__ = "GPL"
__maintainer__ = "Kevin Barnard"
__email__ = "kbarnard@mbari.org"
__doc__ = '''

Custom QListWidgetItem for displaying concept information

@author: __author__
@status: __status__
@license: __license__
'''
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QListWidgetItem


class ConceptEntry(QListWidgetItem):

    def __init__(self, data=None, parent=None):
        super(ConceptEntry, self).__init__(parent)

        self.setFont(QFont('Courier New'))
        self.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)

        self.ann_data = data
        if data:
            self.update_message()

    def set_ann_data(self, data):
        self.ann_data = data

    def get_data(self):
        return self.ann_data

    def update_message(self):
        """
        Set message based on annotation data
        :return: None
        """
        str_rep = '{0}: {1}'.format(self.ann_data['concept'], self.ann_data['timecode'])
        self.setText(str_rep)
