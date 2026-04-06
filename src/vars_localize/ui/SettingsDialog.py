"""Settings dialog with tabbed configuration for app, connection, and SAM3."""

from __future__ import annotations

import os

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from vars_localize.state import AppSettings
from vars_localize.util.utils import center_window


class SettingsDialog(QDialog):
    def __init__(self, app_settings: AppSettings, parent=None):
        super(SettingsDialog, self).__init__(parent)
        self._settings = app_settings

        self.setWindowTitle("Settings")
        self.setMinimumSize(700, 480)

        self.setLayout(QVBoxLayout())
        layout = self.layout()
        if not isinstance(layout, QVBoxLayout):
            raise RuntimeError("Unexpected layout type")

        self.tabs = QTabWidget(self)
        layout.addWidget(self.tabs)

        self._general_tab = self._build_general_tab()
        self._connection_tab = self._build_connection_tab()
        self._sam_tab = self._build_sam_tab()

        self.tabs.addTab(self._general_tab, "General")
        self.tabs.addTab(self._connection_tab, "Connection")
        self.tabs.addTab(self._sam_tab, "SAM3 / AI")

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self._save)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        self._load_from_settings()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        center_window(self, self.parentWidget())

    def _build_general_tab(self) -> QWidget:
        tab = QWidget(self)
        tab.setLayout(QVBoxLayout())

        shortcuts_group = QGroupBox("Keyboard Shortcuts")
        shortcuts_group.setLayout(QFormLayout())
        shortcut_form = shortcuts_group.layout()
        if not isinstance(shortcut_form, QFormLayout):
            raise RuntimeError("Unexpected layout type")

        self.focus_search_shortcut = QLineEdit()
        self.clear_results_shortcut = QLineEdit()
        self.open_settings_shortcut = QLineEdit()

        self.focus_search_shortcut.setPlaceholderText("Ctrl+F")
        self.clear_results_shortcut.setPlaceholderText("Ctrl+L")
        self.open_settings_shortcut.setPlaceholderText("Ctrl+,")

        shortcut_form.addRow("Focus Search", self.focus_search_shortcut)
        shortcut_form.addRow("Clear Results", self.clear_results_shortcut)
        shortcut_form.addRow("Open Settings", self.open_settings_shortcut)

        search_group = QGroupBox("Search")
        search_group.setLayout(QFormLayout())
        search_form = search_group.layout()
        if not isinstance(search_form, QFormLayout):
            raise RuntimeError("Unexpected layout type")

        self.search_page_size = QSpinBox()
        self.search_page_size.setRange(1, 500)
        self.search_page_size.setSingleStep(5)
        search_form.addRow("Results per page", self.search_page_size)

        note = QLabel(
            "Shortcuts and page size changes are applied immediately after saving."
        )
        note.setObjectName("secondaryText")
        note.setWordWrap(True)

        tab_layout = tab.layout()
        if not isinstance(tab_layout, QVBoxLayout):
            raise RuntimeError("Unexpected layout type")

        tab_layout.addWidget(shortcuts_group)
        tab_layout.addWidget(search_group)
        tab_layout.addWidget(note)
        tab_layout.addStretch(1)
        return tab

    def _build_connection_tab(self) -> QWidget:
        tab = QWidget(self)
        tab.setLayout(QVBoxLayout())

        connection_group = QGroupBox("M3 Connection")
        connection_group.setLayout(QFormLayout())
        connection_form = connection_group.layout()
        if not isinstance(connection_form, QFormLayout):
            raise RuntimeError("Unexpected layout type")

        self.m3_url_field = QLineEdit()
        self.m3_url_field.setPlaceholderText("https://m3.shore.mbari.org")

        self.connection_timeout_secs = QSpinBox()
        self.connection_timeout_secs.setRange(1, 30)

        connection_form.addRow("Default M3 URL", self.m3_url_field)
        connection_form.addRow(
            "Connection Check Timeout (seconds)", self.connection_timeout_secs
        )

        note = QLabel(
            "The default M3 URL is used to prefill the login dialog. "
            "Changing it updates the default for future logins."
        )
        note.setObjectName("secondaryText")
        note.setWordWrap(True)

        tab_layout = tab.layout()
        if not isinstance(tab_layout, QVBoxLayout):
            raise RuntimeError("Unexpected layout type")

        tab_layout.addWidget(connection_group)
        tab_layout.addWidget(note)
        tab_layout.addStretch(1)
        return tab

    def _build_sam_tab(self) -> QWidget:
        tab = QWidget(self)
        tab.setLayout(QVBoxLayout())

        sam_group = QGroupBox("SAM3")
        sam_group.setLayout(QFormLayout())
        sam_form = sam_group.layout()
        if not isinstance(sam_form, QFormLayout):
            raise RuntimeError("Unexpected layout type")

        self.sam_enabled = QCheckBox("Enable SAM3 Assist")
        self.sam_semantic_enabled = QCheckBox("Enable semantic text prompts")
        self.sam_point_enabled = QCheckBox("Enable point prompts")

        model_row = QWidget()
        model_row.setLayout(QHBoxLayout())
        model_row_layout = model_row.layout()
        if not isinstance(model_row_layout, QHBoxLayout):
            raise RuntimeError("Unexpected layout type")
        model_row_layout.setContentsMargins(0, 0, 0, 0)

        self.sam_model_path = QLineEdit()
        self.sam_model_path.setPlaceholderText("Path to local SAM3 model (required)")
        self.sam_model_browse_button = QPushButton("Browse...")
        self.sam_model_browse_button.clicked.connect(self._browse_sam_model)

        model_row_layout.addWidget(self.sam_model_path, 1)
        model_row_layout.addWidget(self.sam_model_browse_button)

        self.sam_confidence = QDoubleSpinBox()
        self.sam_confidence.setRange(0.0, 1.0)
        self.sam_confidence.setDecimals(3)
        self.sam_confidence.setSingleStep(0.05)

        self.sam_image_size = QSpinBox()
        self.sam_image_size.setRange(64, 4096)
        self.sam_image_size.setSingleStep(32)

        self.sam_min_area = QSpinBox()
        self.sam_min_area.setRange(1, 1000000)

        self.sam_overlap_iou = QDoubleSpinBox()
        self.sam_overlap_iou.setRange(0.0, 1.0)
        self.sam_overlap_iou.setDecimals(3)
        self.sam_overlap_iou.setSingleStep(0.05)

        sam_form.addRow(self.sam_enabled)
        sam_form.addRow(self.sam_semantic_enabled)
        sam_form.addRow(self.sam_point_enabled)
        sam_form.addRow("Model file", model_row)
        sam_form.addRow("Confidence", self.sam_confidence)
        sam_form.addRow("Image size", self.sam_image_size)
        sam_form.addRow("Candidate min area", self.sam_min_area)
        sam_form.addRow("Overlap IoU filter", self.sam_overlap_iou)

        note = QLabel(
            "SAM3 model files are not downloaded automatically. "
            "Download the model yourself, then set the local model path here."
        )
        note.setObjectName("secondaryText")
        note.setWordWrap(True)

        tab_layout = tab.layout()
        if not isinstance(tab_layout, QVBoxLayout):
            raise RuntimeError("Unexpected layout type")

        tab_layout.addWidget(sam_group)
        tab_layout.addWidget(note)
        tab_layout.addStretch(1)
        return tab

    def _load_from_settings(self):
        self.search_page_size.setValue(self._settings.search_page_size)

        self.focus_search_shortcut.setText(self._settings.focus_search_shortcut)
        self.clear_results_shortcut.setText(self._settings.clear_results_shortcut)
        self.open_settings_shortcut.setText(self._settings.open_settings_shortcut)

        self.m3_url_field.setText(self._settings.m3_url)
        self.connection_timeout_secs.setValue(self._settings.connection_timeout_secs)

        self.sam_enabled.setChecked(self._settings.sam3_enabled)
        self.sam_semantic_enabled.setChecked(self._settings.sam3_semantic_enabled)
        self.sam_point_enabled.setChecked(self._settings.sam3_point_enabled)
        self.sam_model_path.setText(self._settings.sam3_model_path)
        self.sam_confidence.setValue(self._settings.sam3_confidence)
        self.sam_image_size.setValue(self._settings.sam3_image_size)
        self.sam_min_area.setValue(self._settings.sam3_min_area)
        self.sam_overlap_iou.setValue(self._settings.sam3_overlap_iou)

    def _browse_sam_model(self):
        model_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select SAM3 Model",
            self.sam_model_path.text().strip(),
            "Model Files (*.pt *.pth *.onnx);;All Files (*)",
        )
        if model_path:
            self.sam_model_path.setText(model_path)

    def _save(self):
        model_path = self.sam_model_path.text().strip()
        if self.sam_enabled.isChecked():
            if (
                not self.sam_semantic_enabled.isChecked()
                and not self.sam_point_enabled.isChecked()
            ):
                QMessageBox.warning(
                    self,
                    "SAM3 mode required",
                    "Enable at least one SAM3 prompt mode (semantic or point).",
                )
                self.tabs.setCurrentWidget(self._sam_tab)
                return
            if not model_path:
                QMessageBox.warning(
                    self,
                    "SAM3 model required",
                    "Enable SAM3 Assist requires a local model file path.",
                )
                self.tabs.setCurrentWidget(self._sam_tab)
                return
            if not os.path.isfile(model_path):
                QMessageBox.warning(
                    self,
                    "SAM3 model not found",
                    "The configured SAM3 model path does not point to a file.",
                )
                self.tabs.setCurrentWidget(self._sam_tab)
                return

        m3_url = self.m3_url_field.text().strip()
        if not m3_url:
            QMessageBox.warning(
                self,
                "M3 URL required",
                "Default M3 URL cannot be empty.",
            )
            self.tabs.setCurrentWidget(self._connection_tab)
            return

        self._settings.search_page_size = self.search_page_size.value()
        self._settings.focus_search_shortcut = self.focus_search_shortcut.text().strip()
        self._settings.clear_results_shortcut = (
            self.clear_results_shortcut.text().strip()
        )
        self._settings.open_settings_shortcut = (
            self.open_settings_shortcut.text().strip()
        )

        self._settings.m3_url = m3_url
        self._settings.connection_timeout_secs = self.connection_timeout_secs.value()

        self._settings.sam3_enabled = self.sam_enabled.isChecked()
        self._settings.sam3_semantic_enabled = self.sam_semantic_enabled.isChecked()
        self._settings.sam3_point_enabled = self.sam_point_enabled.isChecked()
        self._settings.sam3_model_path = model_path
        self._settings.sam3_confidence = self.sam_confidence.value()
        self._settings.sam3_image_size = self.sam_image_size.value()
        self._settings.sam3_min_area = self.sam_min_area.value()
        self._settings.sam3_overlap_iou = self.sam_overlap_iou.value()

        self.accept()
