"""
Container widget used do display images + localizations and process input.
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton

from vars_localize.ui.ImageView import ImageView
from vars_localize.ui.EntryTree import EntryTreeItem


class DisplayPanel(QWidget):
    def __init__(self, parent=None):
        super(DisplayPanel, self).__init__(parent)

        self.setLayout(QVBoxLayout())

        self.sam_controls = QWidget()
        self.sam_controls.setLayout(QHBoxLayout())
        self.sam_controls.layout().setContentsMargins(0, 0, 0, 0)
        self.sam_controls.layout().setSpacing(6)

        self.sam_label = QLabel("SAM candidates")
        self.sam_label.setObjectName("secondaryText")

        self.sam_status_label = QLabel("SAM disabled")
        self.sam_status_label.setObjectName("secondaryText")
        self.sam_status_label.setWordWrap(True)

        self.sam_accept = QPushButton("✓")
        self.sam_accept.setToolTip("Accept current SAM candidate")
        self.sam_accept.clicked.connect(self._accept_sam_candidate)

        self.sam_reject = QPushButton("x")
        self.sam_reject.setToolTip("Reject current SAM candidate")
        self.sam_reject.clicked.connect(self._reject_sam_candidate)

        self.sam_controls.layout().addWidget(self.sam_label)
        self.sam_controls.layout().addWidget(self.sam_accept)
        self.sam_controls.layout().addWidget(self.sam_reject)
        self.sam_controls.layout().addStretch(1)

        self.image_view = ImageView(parent=self)
        self.image_view.set_sam_candidate_ui_callback(self._set_sam_candidate_state)
        self.image_view.set_sam_status_ui_callback(self._set_sam_status)

        self.layout().addWidget(self.sam_status_label)
        self.layout().addWidget(self.sam_controls)
        self.layout().addWidget(self.image_view, stretch=1)

        self._set_sam_candidate_state(False, 0, 0)

    def _set_sam_candidate_state(self, visible: bool, index: int, total: int):
        self.sam_controls.setVisible(visible)
        self.sam_accept.setEnabled(visible)
        self.sam_reject.setEnabled(visible)
        if visible:
            self.sam_label.setText("SAM candidate {}/{}".format(index + 1, total))
        else:
            self.sam_label.setText("SAM candidates")

    def _set_sam_status(self, status: str):
        self.sam_status_label.setText("SAM: {}".format(status))

    def _accept_sam_candidate(self):
        self.image_view.accept_sam_candidate()

    def _reject_sam_candidate(self):
        self.image_view.reject_sam_candidate()

    def load_entry(self, entry: EntryTreeItem):
        """Load an entry into the image view and redraw.

        Args:
            entry: Selected tree entry.
        """
        self.image_view.set_entry(entry)
        self.image_view.redraw()
