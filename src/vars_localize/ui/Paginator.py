"""Pagination controller widget."""

from math import ceil
from typing import Optional

from PyQt6 import QtGui
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QInputDialog, QLabel, QPushButton, QWidget


class Paginator(QWidget):
    left_signal = pyqtSignal()
    right_signal = pyqtSignal()
    jump_signal = pyqtSignal()

    def __init__(self, parent=None):
        super(Paginator, self).__init__(parent)

        self.setObjectName("paginatorBar")

        self._layout = QHBoxLayout()
        self._layout.setContentsMargins(2, 2, 2, 2)
        self._layout.setSpacing(6)
        self.setLayout(self._layout)

        self.offset = 0
        self.limit = 25
        self.count = 0

        self.summary_label = QLabel("No results")
        self.summary_label.setObjectName("secondaryText")

        self.first_button = QPushButton("<<")
        self.first_button.setToolTip("First page")
        self.first_button.pressed.connect(self.first_press)

        self.left_button = QPushButton("<")
        self.left_button.setToolTip("Previous page")
        self.left_button.pressed.connect(self.left_press)

        self.page_button = QPushButton("Page 0 / 0")
        self.page_button.setToolTip("Jump to page")
        self.page_button.pressed.connect(self.prompt_jump)

        self.right_button = QPushButton(">")
        self.right_button.setToolTip("Next page")
        self.right_button.pressed.connect(self.right_press)

        self.last_button = QPushButton(">>")
        self.last_button.setToolTip("Last page")
        self.last_button.pressed.connect(self.last_press)

        self._layout.addWidget(self.summary_label, 1)
        self._layout.addWidget(self.first_button)
        self._layout.addWidget(self.left_button)
        self._layout.addWidget(self.page_button)
        self._layout.addWidget(self.right_button)
        self._layout.addWidget(self.last_button)

        self.update_nav()

    @property
    def page_count(self) -> int:
        if self.count <= 0 or self.limit <= 0:
            return 0
        return int(ceil(self.count / float(self.limit)))

    @property
    def current_page(self) -> int:
        if self.limit <= 0:
            return 0
        return int(self.offset // self.limit) + 1

    @property
    def slice(self):
        return slice(self.offset, self.offset + self.limit)

    def _last_page_offset(self) -> int:
        pages = self.page_count
        if pages <= 1:
            return 0
        return (pages - 1) * self.limit

    def _emit_for_step(self, old_offset: int):
        if self.offset == old_offset:
            return
        if self.offset < old_offset:
            self.left_signal.emit()
        else:
            self.right_signal.emit()

    def first_press(self):
        old_offset = self.offset
        self.offset = 0
        self.update_nav()
        self._emit_for_step(old_offset)

    def left_press(self):
        old_offset = self.offset
        self.offset = max(0, self.offset - self.limit)
        self.update_nav()
        self._emit_for_step(old_offset)

    def right_press(self):
        old_offset = self.offset
        self.offset = min(self._last_page_offset(), self.offset + self.limit)
        self.update_nav()
        self._emit_for_step(old_offset)

    def last_press(self):
        old_offset = self.offset
        self.offset = self._last_page_offset()
        self.update_nav()
        self._emit_for_step(old_offset)

    def prompt_jump(self):
        if self.page_count <= 1:
            return

        page, ok = QInputDialog.getInt(
            self,
            "Jump to page",
            "Page number:",
            min=1,
            max=self.page_count,
        )
        if not ok:
            return

        self.offset = (page - 1) * self.limit
        self.update_nav()
        self.jump_signal.emit()

    def update_nav(self):
        if self.limit <= 0:
            self.limit = 25

        if self.count <= 0:
            self.offset = 0
            self.summary_label.setText("No results")
            self.page_button.setText("Page 0 / 0")
            for btn in (
                self.first_button,
                self.left_button,
                self.page_button,
                self.right_button,
                self.last_button,
            ):
                btn.setEnabled(False)
            return

        self.offset = max(0, min(self.offset, self._last_page_offset()))

        left_bound = self.offset + 1
        right_bound = min(self.offset + self.limit, self.count)
        self.summary_label.setText(
            "Showing {} - {} of {}".format(left_bound, right_bound, self.count)
        )

        pages = self.page_count
        current = self.current_page
        self.page_button.setText("Page {} / {}".format(current, pages))

        self.first_button.setEnabled(current > 1)
        self.left_button.setEnabled(current > 1)
        self.page_button.setEnabled(pages > 1)
        self.right_button.setEnabled(current < pages)
        self.last_button.setEnabled(current < pages)

    def set_offset(self, offset: int):
        self.offset = max(0, int(offset))
        self.update_nav()

    def set_limit(self, limit: int):
        self.limit = max(1, int(limit))
        self.update_nav()

    def set_count(self, count: int):
        self.count = max(0, int(count))
        self.update_nav()

    def mouseDoubleClickEvent(self, a0: Optional[QtGui.QMouseEvent]) -> None:
        if a0 is None:
            return
        self.prompt_jump()
