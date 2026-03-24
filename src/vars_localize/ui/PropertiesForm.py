"""
Form for inputting and displaying properties about localizations and annotations.
"""

from PyQt6.QtWidgets import QComboBox, QGroupBox, QFormLayout, QSpinBox, QLabel

from vars_localize.ui.BoundingBox import SourceBoundingBox


class PropertiesForm(QGroupBox):
    def __init__(self, source: SourceBoundingBox, parent=None):
        super(PropertiesForm, self).__init__(parent)

        self.setTitle("Selected Localization Properties")

        self.source = source

        self.form = QFormLayout()
        self.setLayout(self.form)

        self.concept_field = QLabel()
        self.concept_field.setText(source.label)
        self.part_field = QComboBox()
        self.x_field = QSpinBox()
        self.y_field = QSpinBox()
        self.w_field = QSpinBox()
        self.h_field = QSpinBox()

        self.x_field.valueChanged.connect(self.source.setX)
        self.y_field.valueChanged.connect(self.source.setY)
        self.w_field.valueChanged.connect(self.source.setWidth)
        self.h_field.valueChanged.connect(self.source.setHeight)

        self.x_field.valueChanged.connect(self.x_changed)
        self.y_field.valueChanged.connect(self.y_changed)
        self.part_field.currentTextChanged.connect(self.part_changed)

        self.form.addRow("Concept", self.concept_field)
        self.form.addRow("Part", self.part_field)
        self.form.addRow("X-Position", self.x_field)
        self.form.addRow("Y-Position", self.y_field)
        self.form.addRow("Width", self.w_field)
        self.form.addRow("Height", self.h_field)

    def set_part_options(self, options):
        current = self.source.part or "self"
        valid_options = [
            str(opt).strip() for opt in (options or []) if str(opt).strip()
        ]
        valid_options = list(dict.fromkeys(["self"] + valid_options))

        if current not in valid_options:
            valid_options.append(current)

        self.part_field.clear()
        self.part_field.addItems(valid_options)
        self.part_field.setCurrentText(current)

    def part_changed(self, value: str):
        self.source.part = value or "self"

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
        self.part_field.currentTextChanged.connect(update_callback)
