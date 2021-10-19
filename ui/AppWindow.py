# AppWindow.py (vars-localize)
import os
import sys

from ui.EntryTree import EntryTreeItem

__author__ = "Kevin Barnard"
__copyright__ = "Copyright 2019, Monterey Bay Aquarium Research Institute"
__credits__ = ["MBARI"]
__license__ = "GPL"
__maintainer__ = "Kevin Barnard"
__email__ = "kbarnard@mbari.org"
__doc__ = '''

Application Window.

@author: __author__
@status: __status__
@license: __license__
'''
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QCloseEvent, QIcon
from PyQt5.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QDialog, QVBoxLayout, QFormLayout, QLineEdit, \
    QPushButton, QCompleter, QMessageBox, QAction, QInputDialog

from ui.ConceptEntry import ConceptEntry
from ui.DisplayPanel import DisplayPanel
from ui.SearchPanel import SearchPanel

from util.requests import check_connection, get_all_users, get_imaged_moments_by_image_reference
from util.utils import log, split_comma_list


class AppWindow(QMainWindow):

    def __init__(self, parent=None):
        super(AppWindow, self).__init__(parent)

        self.setWindowTitle('VARS Localize')
        self.setWindowIcon(QIcon('images/Icon.ico'))

        log('Checking connection to M3...')
        if not check_connection():
            log('You are not connected to M3. Check your internet connection and/or VPN.', level=2)
            QMessageBox.critical(self,
                                 'No connection to M3',
                                 'You are not connected to M3. Check your internet connection and/or VPN.')
            exit(1)
        log('Connected.')

        self.central_container = QWidget()
        self.central_container.setLayout(QHBoxLayout())

        self.search_panel = SearchPanel(parent=self)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.search_panel)

        self.display_panel = DisplayPanel(parent=self)
        self.central_container.layout().addWidget(self.display_panel)

        self.observer = None
        self.observer_role = None
        self.admin_mode = False

        self.setCentralWidget(self.central_container)

        self.login()
        if not self.observer:
            log('You must login to use this tool.', level=2)
            exit(1)

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
        login_dialog = QDialog()
        login_dialog.setModal(True)
        login_dialog.setWindowTitle('Login')

        login_dialog.setLayout(QVBoxLayout())

        form_widget = QWidget()
        form = QFormLayout()
        form_widget.setLayout(form)
        observer_field = QLineEdit()
        all_valid_users = get_all_users()
        users_dict = {user_data['username']: user_data for user_data in all_valid_users}
        observer_completer = QCompleter(users_dict.keys())
        observer_completer.setCaseSensitivity(Qt.CaseInsensitive)
        observer_field.setCompleter(observer_completer)

        login_button = QPushButton('Login')
        login_button.setEnabled(False)
        login_button.pressed.connect(login_dialog.close)

        def observer_field_updated(text):
            nonlocal login_button
            if text in users_dict:
                self.observer = text
                self.observer_role = users_dict[text]['role']
                login_button.setEnabled(True)
            else:
                login_button.setEnabled(False)

        observer_field.textChanged.connect(observer_field_updated)

        form.addRow('Observer: ', observer_field)

        login_dialog.layout().addWidget(form_widget)
        login_dialog.layout().addWidget(login_button)

        login_dialog.exec_()

        if self.observer_role in ('Maint', 'Admin'):
            self.add_admin_menu()

        self.add_search_menu()

    def add_admin_menu(self):
        """
        Add the admin menu for observation modification/deletion
        """
        main_menu = self.menuBar()
        options_menu = main_menu.addMenu('&Options')

        admin_mode_action = QAction('Admin Mode', options_menu, checkable=True)

        def set_admin_mode(val):
            if val:
                QMessageBox.warning(self, 'Entering Admin Mode', 'WARNING: You are now entering administrator mode. This mode allows modification and deletion of observations within VARS.')
            self.admin_mode = val

        admin_mode_action.toggled.connect(set_admin_mode)
        options_menu.addAction(admin_mode_action)

    def add_search_menu(self):
        """
        Add the Go menu for non-concept searches
        """
        main_menu = self.menuBar()
        search_menu = main_menu.addMenu('&Search')

        def search_imaged_moment():
            imaged_moment_uuid_list, ok = QInputDialog.getText(self, 'Imaged Moment UUID Search', 'Imaged Moment UUID (or comma-separated list)')
            if ok:
                imaged_moment_uuids = split_comma_list(imaged_moment_uuid_list)
                imaged_moment_uuids = list(set(imaged_moment_uuids))  # Ensure no duplicates
                
                # Set the UUIDs and load the first page
                self.search_panel.set_uuids(imaged_moment_uuids)
                self.search_panel.load_page()

        search_imaged_moment_action = QAction('Imaged Moment UUID', search_menu)
        search_imaged_moment_action.triggered.connect(search_imaged_moment)
        search_menu.addAction(search_imaged_moment_action)

        def search_image_reference():
            image_reference_uuid_list, ok = QInputDialog.getText(self, 'Image Reference UUID Search', 'Image Reference UUID (or comma-separated list)')
            if ok:
                all_image_reference_uuids = split_comma_list(image_reference_uuid_list)
                imaged_moment_uuids = []
                for image_reference_uuid in all_image_reference_uuids:
                    res = get_imaged_moments_by_image_reference(image_reference_uuid)
                    if res:
                        imaged_moment_uuids.extend([item['imaged_moment_uuid'] for item in res])
                imaged_moment_uuids = list(set(imaged_moment_uuids))  # Ensure no duplicates
                
                # Set the UUIDs and load the first page
                self.search_panel.set_uuids(imaged_moment_uuids)
                self.search_panel.load_page()

        search_image_reference_action = QAction('Image Reference UUID', search_menu)
        search_image_reference_action.triggered.connect(search_image_reference)
        search_menu.addAction(search_image_reference_action)

    def closeEvent(self, a0: QCloseEvent) -> None:
        """
        Detect window close and tear down components
        :param a0: Close event
        :return: None
        """
        self.deleteLater()
