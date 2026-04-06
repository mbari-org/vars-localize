"""
Main application window.
"""

from typing import Any, Optional, cast

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QMessageBox,
    QLabel,
    QStatusBar,
)

from vars_localize.ui.EntryTree import EntryTreeItem
from vars_localize.ui.LoginDialog import LoginDialog
from vars_localize.ui.DisplayPanel import DisplayPanel
from vars_localize.ui.SettingsDialog import SettingsDialog
from vars_localize.ui.SearchPanel import SearchPanel
from vars_localize.ui.theme import app_stylesheet
from vars_localize.services import M3Service, SAM3Service
from vars_localize.services.M3Service import DEFAULT_M3_URL
from vars_localize.state import AppSettings, AppStateStore
from vars_localize.util.logging import get_logger
from vars_localize.util.utils import center_window

logger = get_logger("AppWindow")


class AppWindow(QMainWindow):
    def __init__(self, parent=None):
        super(AppWindow, self).__init__(parent)
        self._has_centered_on_show = False
        self._settings = AppSettings()
        self._m3_url = self._settings.m3_url.rstrip("/")
        self._state = AppStateStore(self)
        self._m3: Optional[M3Service] = None
        self._sam3 = SAM3Service(
            model_path=self._settings.sam3_model_path,
            conf=self._settings.sam3_confidence,
            imgsz=self._settings.sam3_image_size,
        )
        self._sam_enabled = self._settings.sam3_enabled
        self._sam_semantic_enabled = self._settings.sam3_semantic_enabled
        self._sam_point_enabled = self._settings.sam3_point_enabled
        self._settings_action = None
        self._admin_mode_action = None
        self._focus_shortcut = None
        self._clear_shortcut = None

        self._activity_label = None
        self._observer_label = None
        self._role_label = None
        self._mode_label = None
        self._concept_label = None
        self._result_label = None

        self.setWindowTitle("VARS Localize")
        self.setStyleSheet(app_stylesheet())

        self.observer = None
        self.observer_role = None
        self.admin_mode = False

        self._state.observerChanged.connect(self._sync_observer)
        self._state.observerRoleChanged.connect(self._sync_observer_role)
        self._state.adminModeChanged.connect(self._sync_admin_mode)
        self._state.loadingChanged.connect(self._sync_loading_state)
        self._state.conceptChanged.connect(self._sync_concept_state)
        self._state.uuidsChanged.connect(self._sync_result_count)

        self.login()

        self.central_container = QWidget()
        self.central_container.setLayout(QHBoxLayout())
        container_layout = cast(QHBoxLayout, self.central_container.layout())
        container_layout.setContentsMargins(4, 4, 4, 4)

        self.search_panel = SearchPanel(
            self._state,
            self._require_m3_service(),
            page_size=self._settings.search_page_size,
            parent=self,
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.search_panel)

        self.display_panel = DisplayPanel(parent=self)
        container_layout.addWidget(self.display_panel)

        self.setCentralWidget(self.central_container)

        self._init_status_bar()

        self._init_options_menu()

        self.display_panel.image_view.observer = self.observer
        self.display_panel.image_view.m3_service = self._require_m3_service()
        self.display_panel.image_view.configure_sam_params(
            self._settings.sam3_min_area,
            self._settings.sam3_overlap_iou,
        )
        self._refresh_sam_service()
        self.display_panel.image_view.set_sam_prompt_modes(
            self._sam_semantic_enabled,
            self._sam_point_enabled,
        )
        self.display_panel.image_view.set_sam_assist_enabled(
            self._sam_enabled and self._sam3.available
        )
        self.display_panel.image_view.select_next = self.search_panel.select_next
        self.display_panel.image_view.select_prev = self.search_panel.select_prev
        self.display_panel.image_view.set_observation_select_callback(
            self.search_panel.select_entry
        )

        self.search_panel.observer = self.observer

        self._sync_result_count(self._state.uuids)

    def _sync_observer(self, value: str):
        self.observer = value
        if self._observer_label is not None:
            self._observer_label.setText("User: {}".format(value or "-"))

    def _sync_observer_role(self, value: str):
        self.observer_role = value
        if self._role_label is not None:
            self._role_label.setText("Role: {}".format(value or "-"))

    def _sync_admin_mode(self, value: bool):
        self.admin_mode = value
        if self._mode_label is not None:
            self._mode_label.setText("Mode: Admin" if value else "Mode: Standard")

    def _sync_loading_state(self, loading: bool):
        if self._activity_label is not None:
            self._activity_label.setText("Loading..." if loading else "Ready")

    def _sync_concept_state(self, concept: str):
        if self._concept_label is not None:
            self._concept_label.setText("Concept: {}".format(concept or "-"))

    def _sync_result_count(self, uuids: list):
        if self._result_label is not None:
            self._result_label.setText("Results: {}".format(len(uuids or [])))

    def _init_status_bar(self):
        status = QStatusBar(self)
        self.setStatusBar(status)

        self._activity_label = QLabel("Ready")
        self._observer_label = QLabel(f"User: {self.observer or '-'}")
        self._role_label = QLabel(f"Role: {self.observer_role or '-'}")
        self._mode_label = QLabel(f"Mode: {self.admin_mode and 'Admin' or 'Standard'}")
        self._concept_label = QLabel("Concept: -")
        self._result_label = QLabel("Results: 0")

        status.addWidget(self._activity_label, 1)
        status.addPermanentWidget(self._observer_label)
        status.addPermanentWidget(self._role_label)
        status.addPermanentWidget(self._mode_label)
        status.addPermanentWidget(self._concept_label)
        status.addPermanentWidget(self._result_label)

        self._configure_shortcuts()

    def _configure_shortcuts(self):
        self._replace_shortcut(
            "_focus_shortcut",
            self._settings.focus_search_shortcut,
            self.search_panel.search_bar.setFocus,
        )
        self._replace_shortcut(
            "_clear_shortcut",
            self._settings.clear_results_shortcut,
            lambda: self.search_panel._clear_results(),
        )

    def _replace_shortcut(self, attr_name: str, sequence: str, callback):
        existing = getattr(self, attr_name, None)
        if existing is not None:
            existing.setParent(None)
            existing.deleteLater()
            setattr(self, attr_name, None)

        key = (sequence or "").strip()
        if not key:
            return

        shortcut = QShortcut(QKeySequence(key), self)
        shortcut.activated.connect(callback)
        setattr(self, attr_name, shortcut)

    def load_entry(self, current: EntryTreeItem, previous: EntryTreeItem):
        """Load the selected tree entry into the display panel.

        Args:
            current: Currently selected entry.
            previous: Previously selected entry.
        """
        if current and current.payload is not None:
            self.display_panel.load_entry(current)

    def login(self) -> None:
        """Prompt for observer login and configure user state."""
        login_dialog = LoginDialog(parent=self, default_m3_url=self._settings.m3_url)
        login_dialog.focus_username()
        login_dialog.adjustSize()
        center_window(login_dialog, self)

        while True:
            ok = login_dialog.exec()
            if not ok:
                raise RuntimeError("Login cancelled by user.")

            login_dialog.clear_error()

            # Get URL/username/password from the dialog
            m3_url, username, password = login_dialog.credentials

            normalized_url = (m3_url or "").strip().rstrip("/") or DEFAULT_M3_URL
            self._m3_url = normalized_url
            self._settings.m3_url = normalized_url
            self._m3 = M3Service(self._m3_url)

            logger.info("Checking connection to M3 at {}", self._m3_url)
            try:
                self._m3.check_connection(
                    timeout_secs=self._settings.connection_timeout_secs
                )
            except ConnectionError as exc:
                logger.error("{}", exc)
                login_dialog.set_error(
                    "Could not connect to M3. Check your internet connection and/or VPN, then try again.",
                )
                continue

            logger.info("Connected.")

            # Set up the M3 configuration, retrying in the same dialog on failure.
            try:
                self.configure_m3(username, password)
            except RuntimeError:
                login_dialog.set_error(
                    "Login failed. Check your username and password, then try again.",
                )
                continue

            all_valid_users = self._require_m3_service().get_all_users()
            users_dict = {
                user_data["username"]: user_data for user_data in all_valid_users
            }

            # Set the observer and role
            self._state.observer = username
            user_record = users_dict.get(username) or {}
            self._state.observer_role = str(user_record.get("role", "User"))
            return

    def configure_m3(self, username: str, password: str) -> None:
        """
        Configure endpoints and set up Annosaurus auth
        """
        try:
            self._require_m3_service().configure(username, password)
        except Exception as exc:
            logger.exception("Login failed.")
            raise RuntimeError("Login failed.") from exc

    def _require_m3_service(self) -> M3Service:
        if self._m3 is None:
            raise RuntimeError("M3 service has not been initialized")
        return self._m3

    def _init_options_menu(self):
        """Initialize global options menu and optional admin controls."""
        main_menu = cast(Any, self.menuBar())
        options_menu = main_menu.addMenu("&Options")

        self._settings_action = QAction("Settings...", self)
        self._settings_action.setShortcut(
            QKeySequence(self._settings.open_settings_shortcut)
        )
        self._settings_action.triggered.connect(self._open_settings)
        options_menu.addAction(self._settings_action)

        # Add admin mode only for privileged roles.
        if self.observer_role not in ("Maint", "Admin"):
            return

        self._admin_mode_action = QAction("Admin Mode", self)
        self._admin_mode_action.setCheckable(True)

        def set_admin_mode(val):
            if val:
                QMessageBox.warning(
                    self,
                    "Entering Admin Mode",
                    "WARNING: You are now entering administrator mode. This mode allows modification and deletion of observations within VARS.",
                )
            self._state.admin_mode = val

        self._admin_mode_action.toggled.connect(set_admin_mode)
        options_menu.addAction(self._admin_mode_action)

    def _refresh_sam_service(self) -> None:
        self._sam3.configure_runtime(
            model_path=self._settings.sam3_model_path,
            conf=self._settings.sam3_confidence,
            imgsz=self._settings.sam3_image_size,
        )
        self.display_panel.image_view.sam3_service = self._sam3
        self.display_panel.image_view.configure_sam_params(
            self._settings.sam3_min_area,
            self._settings.sam3_overlap_iou,
        )
        try:
            self._sam3.ensure_loaded(
                semantic_enabled=self._settings.sam3_semantic_enabled,
                point_enabled=self._settings.sam3_point_enabled,
            )
        except Exception as exc:
            logger.warning("SAM3 assist unavailable: {}", exc)

    def _open_settings(self):
        previous = self._settings.snapshot()
        dialog = SettingsDialog(self._settings, parent=self)
        dialog.adjustSize()
        center_window(dialog, self)
        ok = dialog.exec()
        if not ok:
            return

        current = self._settings.snapshot()

        self.search_panel.set_page_size(current.search_page_size)
        self._configure_shortcuts()

        if self._settings_action is not None:
            self._settings_action.setShortcut(
                QKeySequence(current.open_settings_shortcut)
            )

        self._sam_enabled = current.sam3_enabled
        self._sam_semantic_enabled = current.sam3_semantic_enabled
        self._sam_point_enabled = current.sam3_point_enabled
        self._sam3.configure_runtime(
            model_path=current.sam3_model_path,
            conf=current.sam3_confidence,
            imgsz=current.sam3_image_size,
        )
        self.display_panel.image_view.configure_sam_params(
            current.sam3_min_area,
            current.sam3_overlap_iou,
        )

        if self._sam_enabled and not self._sam3.available:
            try:
                self._sam3.ensure_loaded(
                    semantic_enabled=self._sam_semantic_enabled,
                    point_enabled=self._sam_point_enabled,
                )
            except Exception as exc:
                logger.warning("SAM3 assist unavailable: {}", exc)
        elif self._sam_enabled:
            try:
                self._sam3.ensure_loaded(
                    semantic_enabled=self._sam_semantic_enabled,
                    point_enabled=self._sam_point_enabled,
                )
            except Exception as exc:
                logger.warning("SAM3 assist unavailable: {}", exc)

        self.display_panel.image_view.set_sam_prompt_modes(
            self._sam_semantic_enabled,
            self._sam_point_enabled,
        )
        self.display_panel.image_view.set_sam_assist_enabled(
            self._sam_enabled and self._sam3.available
        )

        if previous.m3_url != current.m3_url:
            QMessageBox.information(
                self,
                "M3 URL updated",
                "The default M3 URL has been updated. The new value will be used for your next login.",
            )

    def closeEvent(self, a0) -> None:
        """Handle window close and tear down components.

        Args:
            a0: Close event payload.
        """
        self.deleteLater()
        super().closeEvent(a0)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._has_centered_on_show:
            center_window(self)
            self._has_centered_on_show = True
