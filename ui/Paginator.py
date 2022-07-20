# Paginator.py (vars-localize)
from PyQt5 import QtGui
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel, QInputDialog

__author__ = "Kevin Barnard"
__copyright__ = "Copyright 2019, Monterey Bay Aquarium Research Institute"
__credits__ = ["MBARI"]
__license__ = "GPL"
__maintainer__ = "Kevin Barnard"
__email__ = "kbarnard@mbari.org"
__doc__ = '''

Pagination controller widget.

@author: __author__
@status: __status__
@license: __license__
'''


class Paginator(QWidget):

    left_signal = pyqtSignal()
    right_signal = pyqtSignal()
    jump_signal = pyqtSignal()

    def __init__(self, parent=None):
        super(Paginator, self).__init__(parent)

        self.setLayout(QHBoxLayout())

        self.offset = 0
        self.limit = 0
        self.count = 0

        self.nav_label = QLabel()

        self.left_button = QPushButton()
        self.left_button.setIcon(QIcon('images/arrow_left.png'))
        self.left_button.pressed.connect(self.left_press)

        self.right_button = QPushButton()
        self.right_button.setIcon(QIcon('images/arrow_right.png'))
        self.right_button.pressed.connect(self.right_press)

        self.layout().addWidget(self.nav_label, stretch=1)
        self.layout().addWidget(self.left_button)
        self.layout().addWidget(self.right_button)

        self.update_nav()

    def left_press(self):
        self.offset -= self.limit
        self.update_nav()
        self.left_signal.emit()

    def right_press(self):
        self.offset += self.limit
        self.update_nav()
        self.right_signal.emit()

    def update_nav(self):
        self.offset = max(0, self.offset)  # If < 0, fixes
        left_bound = self.offset + 1
        right_bound = self.offset + self.limit
        count_msg = ''

        if self.count:
            right_bound = min(right_bound, self.count)  # Limit to count
            count_msg = ' of {}'.format(self.count)

        self.nav_label.setText('{} - {}'.format(left_bound, right_bound) + count_msg)

        # Disable buttons if hit boundaries
        self.left_button.setEnabled(left_bound > 1)
        if self.count:
            self.right_button.setEnabled(right_bound < self.count)

    def set_offset(self, offset):
        self.offset = offset
        self.update_nav()

    def set_limit(self, limit):
        self.limit = limit
        self.update_nav()

    def set_count(self, count):
        self.count = count
        self.update_nav()
    
    @property
    def slice(self):
        return slice(self.offset, self.offset + self.limit)

    def mouseDoubleClickEvent(self, a0: QtGui.QMouseEvent) -> None:
        if not self.left_button.isEnabled() and not self.right_button.isEnabled():
            return

        imaged_moment_desired, ok = QInputDialog.getInt(self, 'Jump to imaged moment', 'Jump to imaged moment:')
        if ok and 0 < imaged_moment_desired <= self.count:
            self.set_offset(imaged_moment_desired - 1)
            self.jump_signal.emit()
