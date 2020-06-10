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
    QPushButton, QCompleter, QMessageBox

from ui.ConceptEntry import ConceptEntry
from ui.DisplayPanel import DisplayPanel
from ui.SearchPanel import SearchPanel

from util.requests import check_connection, get_all_users
from util.utils import log


class AppWindow(QMainWindow):

    def __init__(self, appctxt, parent=None):
        super(AppWindow, self).__init__(parent)

        self.setWindowTitle('VARS Anchor')
        self.setWindowIcon(QIcon(appctxt.get_resource('images/Icon.ico')))

        if not check_connection():
            log('You are not connected to M3. Check your internet connection and/or VPN.', level=2)
            QMessageBox.critical(self,
                                 'No connection to M3',
                                 'You are not connected to M3. Check your internet connection and/or VPN.')
            exit(1)

        self.central_container = QWidget()
        self.central_container.setLayout(QHBoxLayout())

        self.search_panel = SearchPanel(parent=self)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.search_panel)

        self.display_panel = DisplayPanel(parent=self)
        self.central_container.layout().addWidget(self.display_panel)

        self.observer = None

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
        observer_completer = QCompleter(all_valid_users)
        observer_completer.setCaseSensitivity(Qt.CaseInsensitive)
        observer_field.setCompleter(observer_completer)

        login_button = QPushButton('Login')
        login_button.setEnabled(False)
        login_button.pressed.connect(login_dialog.close)

        def observer_field_updated(text):
            nonlocal login_button
            if text in all_valid_users:
                self.observer = text
                login_button.setEnabled(True)
            else:
                login_button.setEnabled(False)

        observer_field.textChanged.connect(observer_field_updated)

        form.addRow('Observer: ', observer_field)

        login_dialog.layout().addWidget(form_widget)
        login_dialog.layout().addWidget(login_button)

        login_dialog.exec_()

    def closeEvent(self, a0: QCloseEvent) -> None:
        """
        Detect window close and tear down components
        :param a0: Close event
        :return: None
        """
        self.deleteLater()
