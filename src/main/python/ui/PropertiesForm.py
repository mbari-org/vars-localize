# PropertiesForm.py (vars-localize)

__author__ = "Kevin Barnard"
__copyright__ = "Copyright 2019, Monterey Bay Aquarium Research Institute"
__credits__ = ["MBARI"]
__license__ = "GPL"
__maintainer__ = "Kevin Barnard"
__email__ = "kbarnard@mbari.org"
__doc__ = '''

Form for inputting and displaying properties about localizations and annotations.

@author: __author__
@status: __status__
@license: __license__
'''
from PyQt5.QtWidgets import QGroupBox, QFormLayout, QSpinBox, QLineEdit, QLabel

from ui.BoundingBox import SourceBoundingBox
from ui.ConceptSearchbar import ConceptSearchbar


class PropertiesForm(QGroupBox):

    def __init__(self, source: SourceBoundingBox, parent=None):
        super(PropertiesForm, self).__init__(parent)

        self.setTitle('Selected Localization Properties')

        self.source = source

        self.form = QFormLayout()
        self.setLayout(self.form)

        self.concept_field = QLabel()
        self.concept_field.setText(source.label)
        self.x_field = QSpinBox()
        self.y_field = QSpinBox()
        self.w_field = QSpinBox()
        self.h_field = QSpinBox()

        self.concept_field.set_callback(self.source.set_label)
        self.x_field.valueChanged.connect(self.source.setX)
        self.y_field.valueChanged.connect(self.source.setY)
        self.w_field.valueChanged.connect(self.source.setWidth)
        self.h_field.valueChanged.connect(self.source.setHeight)

        self.x_field.valueChanged.connect(self.x_changed)
        self.y_field.valueChanged.connect(self.y_changed)

        self.form.addRow('Concept', self.concept_field)
        self.form.addRow('X-Position', self.x_field)
        self.form.addRow('Y-Position', self.y_field)
        self.form.addRow('Width', self.w_field)
        self.form.addRow('Height', self.h_field)

    def update_box_fields(self):
        self.x_field.setValue(self.source.x())
        self.y_field.setValue(self.source.y())
        self.w_field.setValue(self.source.width())
        self.h_field.setValue(self.source.height())

    def set_bounds(self, x_max, y_max, w_max, h_max):
        self.x_field.setMaximum(x_max)
        self.y_field.setMaximum(y_max)
        self.w_field.setMaximum(w_max)
        self.h_field.setMaximum(h_max)

    def x_changed(self, new_x):
        self.w_field.setMaximum(self.x_field.maximum() - new_x)
        self.update_box_fields()

    def y_changed(self, new_y):
        self.h_field.setMaximum(self.y_field.maximum() - new_y)
        self.update_box_fields()

    def link_callback(self, update_callback):
        self.x_field.valueChanged.connect(update_callback)
        self.y_field.valueChanged.connect(update_callback)
        self.w_field.valueChanged.connect(update_callback)
        self.h_field.valueChanged.connect(update_callback)
