"""
Main entry point for the VARS Localize application.
"""

import sys

from PyQt6.QtWidgets import QApplication

from vars_localize.ui.AppWindow import AppWindow
from vars_localize.util.logging import configure_logging, get_logger

logger = get_logger("Main")


def main():
    """
    Main entry point for the VARS Localize application.
    """
    configure_logging()
    app = QApplication(sys.argv)

    try:
        window = AppWindow()
    except RuntimeError as exc:
        logger.error("{}", exc)
        return 1

    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
