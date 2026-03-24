"""
Main entry point for the VARS Localize application.
"""

import sys

from PyQt6.QtWidgets import QApplication

from vars_localize.ui.AppWindow import AppWindow


def main():
    """
    Main entry point for the VARS Localize application.
    """
    app = QApplication(sys.argv)

    window = AppWindow()
    window.show()

    exit_code = app.exec()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
