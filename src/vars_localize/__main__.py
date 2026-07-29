"""
Main entry point for the VARS Localize application.
"""

import argparse
import sys
from typing import Optional, Sequence

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from vars_localize.assets import get_asset_path
from vars_localize.ui.AppWindow import AppWindow
from vars_localize.util.desktop_entry import (
    install_desktop_entry,
    uninstall_desktop_entry,
)
from vars_localize.util.logging import configure_logging, get_logger

logger = get_logger("Main")


def _build_app_icon() -> QIcon:
    """Build a multi-resolution app icon from packaged PNG assets."""
    icon = QIcon()
    for size in (16, 32, 64, 128, 256, 512):
        icon_path = get_asset_path(f"icons/VARSLocalize.iconset/icon_{size}.png")
        icon.addFile(str(icon_path), QSize(size, size))
    return icon


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vars-localize",
        description="VARS Localize desktop application.",
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser(
        "install-desktop",
        help="Install user-level Linux desktop entry and icons.",
    )
    subparsers.add_parser(
        "uninstall-desktop",
        help="Remove user-level Linux desktop entry and icons.",
    )

    parser.add_argument(
        "--debug-input",
        action="store_true",
        help=(
            "Enable verbose mouse/dialog/SAM-async lifecycle diagnostics for "
            "tracking down input-freeze-style bugs (implies DEBUG log level; "
            "very noisy, logs on every mouse move)."
        ),
    )

    return parser


def main(argv: Optional[Sequence[str]] = None):
    """
    Main entry point for the VARS Localize application.
    """
    parser = _build_arg_parser()
    cli_args = list(argv) if argv is not None else sys.argv[1:]
    args, qt_args = parser.parse_known_args(cli_args)

    if args.command == "install-desktop":
        return install_desktop_entry()
    if args.command == "uninstall-desktop":
        return uninstall_desktop_entry()

    configure_logging(debug_input=getattr(args, "debug_input", False))
    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName("VARS Localize")
    app.setApplicationDisplayName("VARS Localize")
    app.setDesktopFileName("vars-localize")
    app.setWindowIcon(_build_app_icon())

    try:
        window = AppWindow()
    except RuntimeError as exc:
        logger.error("{}", exc)
        return 1

    window.setWindowIcon(app.windowIcon())
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
