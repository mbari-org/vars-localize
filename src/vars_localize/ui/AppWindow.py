"""
Main application window.
"""

from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCloseEvent, QIcon, QAction
from PyQt6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QMessageBox, QInputDialog

from vars_localize.ui.EntryTree import EntryTreeItem
from vars_localize.ui.LoginDialog import LoginDialog
from vars_localize.ui.DisplayPanel import DisplayPanel
from vars_localize.ui.SearchPanel import SearchPanel
from vars_localize.util.m3 import (
    check_connection,
    get_all_users,
    get_annotations_by_video_refernce,
    get_imaged_moments_by_image_reference,
)
from vars_localize.util.utils import log, split_comma_list


class AppWindow(QMainWindow):
    def __init__(self, m3_url: str, parent=None):
        super(AppWindow, self).__init__(parent)
        self._m3_url = m3_url.rstrip("/")

        self.setWindowTitle("VARS Localize")

        log(f"Checking connection to M3 at {self._m3_url}...")
        if not check_connection(self._m3_url):
            log(
                "You are not connected to M3. Check your internet connection and/or VPN.",
                level=2,
            )
            QMessageBox.critical(
                self,
                "No connection to M3",
                "You are not connected to M3. Check your internet connection and/or VPN.",
            )
            exit(1)
        log("Connected.")

        self.observer = None
        self.observer_role = None
        self.admin_mode = False

        login_ok = self.login()
        if not login_ok:
            log("You must log in to use this tool.", level=2)
            exit(1)

        self.central_container = QWidget()
        self.central_container.setLayout(QHBoxLayout())

        self.search_panel = SearchPanel(parent=self)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.search_panel)

        self.display_panel = DisplayPanel(parent=self)
        self.central_container.layout().addWidget(self.display_panel)

        self.setCentralWidget(self.central_container)

        # Add admin menu if available to user
        if self.observer_role in ("Maint", "Admin"):
            self.add_admin_menu()

        self.add_search_menu()
        self.add_video_menu()

        self.display_panel.image_view.observer = self.observer
        self.display_panel.image_view.select_next = self.search_panel.select_next
        self.display_panel.image_view.select_prev = self.search_panel.select_prev

        self.search_panel.observer = self.observer

    def load_entry(self, current: EntryTreeItem, previous: EntryTreeItem):
        """
        Load the current entry into the display panel
        :param current: Current selected entry
        :param previous: Previously selected entry
        :return: None
        """
        if current and current.metadata:
            self.display_panel.load_entry(current)

    def login(self):
        """
        Prompt for observer login
        :return: None
        """
        login_dialog = LoginDialog(parent=self)
        login_dialog._login_form._username_line_edit.setFocus()
        ok = login_dialog.exec()

        if ok:
            # Get the username/password from the dialog
            username, password = login_dialog.credentials

            # Set up the M3 configuration, returning False if login fails
            if not self.configure_m3(username, password):
                return False

            all_valid_users = get_all_users()
            users_dict = {
                user_data["username"]: user_data for user_data in all_valid_users
            }

            # Set the observer and role
            self.observer = username
            self.observer_role = users_dict[username]["role"]
        else:  # Login cancel, return failure
            return False

        return True  # Return success

    def configure_m3(self, username, password) -> bool:
        """
        Configure endpoints and set up Annosaurus auth
        """
        from vars_localize.util.endpoints import configure as configure_endpoints
        from vars_localize.util.m3 import configure_anno_session

        try:
            configure_endpoints(self._m3_url, username, password)
        except Exception as e:
            log("Login failed.", level=2)
            log(e, level=2)
            return False

        configure_anno_session()

        return True

    def add_admin_menu(self):
        """
        Add the admin menu for observation modification/deletion
        """
        main_menu = self.menuBar()
        options_menu = main_menu.addMenu("&Options")

        admin_mode_action = QAction("Admin Mode", options_menu, checkable=True)

        def set_admin_mode(val):
            if val:
                QMessageBox.warning(
                    self,
                    "Entering Admin Mode",
                    "WARNING: You are now entering administrator mode. This mode allows modification and deletion of observations within VARS.",
                )
            self.admin_mode = val

        admin_mode_action.toggled.connect(set_admin_mode)
        options_menu.addAction(admin_mode_action)

    def add_search_menu(self):
        """
        Add the Go menu for non-concept searches
        """
        main_menu = self.menuBar()
        search_menu = main_menu.addMenu("&Search")

        def search_imaged_moment():
            imaged_moment_uuid_list, ok = QInputDialog.getText(
                self,
                "Imaged Moment UUID Search",
                "Imaged Moment UUID (or comma-separated list)",
            )
            if ok:
                imaged_moment_uuids = split_comma_list(imaged_moment_uuid_list)
                imaged_moment_uuids = list(
                    set(imaged_moment_uuids)
                )  # Ensure no duplicates

                # Set the UUIDs and load the first page
                self.search_panel.set_uuids(imaged_moment_uuids)
                self.search_panel.load_page()

        search_imaged_moment_action = QAction("Imaged Moment UUID", search_menu)
        search_imaged_moment_action.triggered.connect(search_imaged_moment)
        search_menu.addAction(search_imaged_moment_action)

        def search_image_reference():
            image_reference_uuid_list, ok = QInputDialog.getText(
                self,
                "Image Reference UUID Search",
                "Image Reference UUID (or comma-separated list)",
            )
            if ok:
                all_image_reference_uuids = split_comma_list(image_reference_uuid_list)
                imaged_moment_uuids = []
                for image_reference_uuid in all_image_reference_uuids:
                    res = get_imaged_moments_by_image_reference(image_reference_uuid)
                    if res:
                        imaged_moment_uuids.extend(
                            [item["imaged_moment_uuid"] for item in res]
                        )
                imaged_moment_uuids = list(
                    set(imaged_moment_uuids)
                )  # Ensure no duplicates

                # Set the UUIDs and load the first page
                self.search_panel.set_uuids(imaged_moment_uuids)
                self.search_panel.load_page()

        search_image_reference_action = QAction("Image Reference UUID", search_menu)
        search_image_reference_action.triggered.connect(search_image_reference)
        search_menu.addAction(search_image_reference_action)

        def search_video_reference():
            video_reference_uuid, ok = QInputDialog.getText(
                self, "Video Reference UUID Search", "Video Reference UUID"
            )
            if ok:
                res = get_annotations_by_video_refernce(video_reference_uuid)
                if res:
                    timestamp_uuid_tuples = set()
                    for item in res:
                        timestamp = datetime.now()
                        if "recorded_timestamp" in item:
                            try:
                                timestamp = datetime.strptime(
                                    item["recorded_timestamp"], "%Y-%m-%dT%H:%M:%S.%fZ"
                                )
                            except ValueError:
                                timestamp = datetime.strptime(
                                    item["recorded_timestamp"], "%Y-%m-%dT%H:%M:%SZ"
                                )

                        timestamp_uuid_tuples.add(
                            (timestamp, item["imaged_moment_uuid"])
                        )

                    # Sort by timestamp, then UUID
                    timestamp_uuid_tuples = sorted(timestamp_uuid_tuples)
                    imaged_moment_uuids = [item[1] for item in timestamp_uuid_tuples]

                    # Set the UUIDs and load the first page
                    self.search_panel.set_uuids(imaged_moment_uuids)
                    self.search_panel.load_page()
                else:
                    # No results, warning dialog
                    QMessageBox.warning(
                        self,
                        "No Results",
                        "No results found for video reference UUID: {}".format(
                            video_reference_uuid
                        ),
                    )

        search_video_reference_action = QAction("Video Reference UUID", search_menu)
        search_video_reference_action.triggered.connect(search_video_reference)
        search_menu.addAction(search_video_reference_action)

    def add_video_menu(self):
        """
        Add the Video menu for video-level operations
        """
        main_menu = self.menuBar()
        video_menu = main_menu.addMenu("&Video")

        def open_video():
            self.search_panel.open_video()

        open_video_action = QAction("Open Video", video_menu)
        open_video_action.triggered.connect(open_video)
        video_menu.addAction(open_video_action)

    def closeEvent(self, a0: QCloseEvent) -> None:
        """
        Detect window close and tear down components
        :param a0: Close event
        :return: None
        """
        self.deleteLater()
