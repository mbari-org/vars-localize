# AppWindow.py (vars-localize)
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
from PyQt5.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QDialog, QVBoxLayout, QFormLayout, QLineEdit, QPushButton, QCompleter

from ui.ConceptEntry import ConceptEntry
from ui.DisplayPanel import DisplayPanel
from ui.SearchPanel import SearchPanel

from util.requests import get_all_users


class AppWindow(QMainWindow):

    def __init__(self, parent=None):
        super(AppWindow, self).__init__(parent)

        self.setWindowTitle('VARS Localization Tool')
        self.setWindowIcon(QIcon('images/logo.png'))

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
            print('You must login to use this tool.')
            exit(1)

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
        observer_completer = QCompleter(get_all_users())
        observer_completer.setCaseSensitivity(Qt.CaseInsensitive)
        observer_field.setCompleter(observer_completer)

        login_button = QPushButton('Login')
        login_button.pressed.connect(login_dialog.close)

        def observer_field_updated(text):
            self.observer = text
            nonlocal login_button
            login_button.setEnabled(bool(text))

        observer_completer.activated.connect(observer_field_updated)

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
