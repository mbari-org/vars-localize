"""
Dialog box for viewing/modifying bounding box properties.
"""

from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QPushButton

from vars_localize.ui.BoundingBox import SourceBoundingBox
from vars_localize.ui.PropertiesForm import PropertiesForm


class PropertiesDialog(QDialog):
    def __init__(self, source: SourceBoundingBox, parent=None):
        super(PropertiesDialog, self).__init__(parent)

        self.setLayout(QVBoxLayout())

        self.box = source

        self.form = PropertiesForm(self.box)
        self.layout().addWidget(self.form)

        self.delete_button = QPushButton("Delete")
        self.delete_button.setStyleSheet("background-color: darkred")
        self.delete_button.setDefault(False)
        self.layout().addWidget(self.delete_button)

    def setup_form(self, pixmap_src: QPixmap, callback):
        self.form.set_bounds(
            pixmap_src.width(),
            pixmap_src.height(),
            pixmap_src.width() - self.box.x() + 1,
            pixmap_src.height() - self.box.y() + 1,
        )
        self.form.update_box_fields()
        self.form.link_callback(callback)

    def set_delete_callback(self, callback):
        def sequence():
            callback(self.box)
            self.close()

        self.delete_button.pressed.connect(sequence)
