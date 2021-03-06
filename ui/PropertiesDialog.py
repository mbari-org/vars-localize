# PropertiesDialog.py (vars-localize)

__author__ = "Kevin Barnard"
__copyright__ = "Copyright 2019, Monterey Bay Aquarium Research Institute"
__credits__ = ["MBARI"]
__license__ = "GPL"
__maintainer__ = "Kevin Barnard"
__email__ = "kbarnard@mbari.org"
__doc__ = '''

Dialog box for viewing/modifying bounding box properties.

@author: __author__
@status: __status__
@license: __license__
'''
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QPushButton

from ui.BoundingBox import SourceBoundingBox
from ui.PropertiesForm import PropertiesForm


class PropertiesDialog(QDialog):

    def __init__(self, source: SourceBoundingBox, parent=None):
        super(PropertiesDialog, self).__init__(parent)

        self.setLayout(QVBoxLayout())

        self.box = source

        self.form = PropertiesForm(self.box)
        self.layout().addWidget(self.form)

        self.delete_button = QPushButton('Delete')
        self.delete_button.setStyleSheet('background-color: rgb(255, 150, 150)')
        self.delete_button.setDefault(False)
        self.layout().addWidget(self.delete_button)

    def setup_form(self, pixmap_src: QPixmap, callback):
        self.form.set_bounds(pixmap_src.width(), pixmap_src.height(),
                             pixmap_src.width() - self.box.x() + 1, pixmap_src.height() - self.box.y() + 1)
        self.form.update_box_fields()
        self.form.link_callback(callback)

    def set_delete_callback(self, callback):
        def sequence():
            callback(self.box)
            self.close()
        self.delete_button.pressed.connect(sequence)
