"""
Entry point module.
"""

import sys

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QSettings
from PyQt5.QtGui import QIcon
import qdarkstyle

import vars_localize.lib.resources
from vars_localize.ui.AppWindow import AppWindow
from vars_localize.lib.constants import APP_NAME, APP_ORGANIZATION


def main():
    """
    Entry point for the application.
    """
    # Create the Qt Application
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ORGANIZATION)
    app.setStyleSheet(qdarkstyle.load_stylesheet_pyqt5())
    app.setWindowIcon(QIcon(':icons/mbari_icon.ico'))
    
    # Initialize settings
    settings = QSettings()
    settings.setDefaultFormat(QSettings.IniFormat)

    # Create and show the main window
    window = AppWindow()
    window.show()

    # Run the main Qt loop
    app.exec()


if __name__ == '__main__':
    main()
