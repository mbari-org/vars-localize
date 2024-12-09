"""
Main entry point for the VARS Localize application.
"""

import argparse
import sys

from PyQt6.QtWidgets import QApplication

from vars_localize.ui.AppWindow import AppWindow
from vars_localize.util.endpoints import DEFAULT_M3_URL


def main():
    """
    Main entry point for the VARS Localize application.
    """
    parser = argparse.ArgumentParser(description="VARS Localize")
    parser.add_argument(
        "-u", "--url", type=str, default=DEFAULT_M3_URL, help="URL of M3 server"
    )
    args = parser.parse_args()

    app = QApplication(sys.argv)

    window = AppWindow(args.url)
    window.show()

    exit_code = app.exec()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
