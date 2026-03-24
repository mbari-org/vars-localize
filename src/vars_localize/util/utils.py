"""
Utility functions for the application.
"""

from functools import reduce
import json
import urllib.parse

from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QApplication, QWidget


def n_split_hash(string: str, n: int, maxval: int = 255):
    """Hash a string into `n` integer values.

    Args:
        string: String to hash.
        n: Number of output values.
        maxval: Upper bound for each hash component.

    Returns:
        tuple[int, ...]: Tuple of hashed integer values.
    """
    if not string:
        return tuple([127] * n)

    part_len = len(string) // n
    parts = [string[i * part_len : (i + 1) * part_len] for i in range(n - 1)]
    parts.append(string[(n - 1) * part_len :])

    return tuple(
        [
            reduce(
                lambda a, b: a * b % maxval,
                [ord(letter) for letter in sorted(part.replace(" ", ""))],
            )
            % maxval
            for part in parts
        ]
    )


def encode_form(json_obj):
    """Encode JSON-like data for x-www-form-urlencoded requests.

    Args:
        json_obj: JSON object.

    Returns:
        bytearray: URL-encoded form payload.
    """
    return bytearray(urllib.parse.urlencode(json_obj).replace("%27", "%22"), "utf-8")


def extract_bounding_boxes(associations: list, concept: str, observation_uuid: str):
    """Yield source bounding boxes from association payloads.

    Args:
        associations: JSON list of associations.
        concept: Concept attached to each source bounding box.
        observation_uuid: Observation UUID attached to each box.

    Yields:
        SourceBoundingBox: Parsed source bounding box instances.
    """
    # Delayed import avoids import cycle with ui.BoundingBox -> util.utils.
    from vars_localize.ui.BoundingBox import SourceBoundingBox

    for association in associations:  # Generate source bounding boxes
        if association.get("link_name") != "bounding box":
            continue

        link_value = association.get("link_value", "")
        try:
            box_json = json.loads(link_value)
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(box_json, dict):
            continue
        if not all(key in box_json for key in ("x", "y", "width", "height")):
            continue
        yield SourceBoundingBox(  # Create source box
            box_json,
            concept,
            observer=box_json.get("observer", None),
            observation_uuid=observation_uuid,
            association_uuid=association.get("uuid"),
            part=association.get("to_concept"),
        )


def split_comma_list(comma_str: str):
    """Split a comma-separated list, stripping surrounding whitespace."""
    return [item.strip() for item in comma_str.split(",")]


def center_window(widget: QWidget, parent: QWidget | None = None):
    """Center a window on its parent, or on the current screen when no parent exists."""
    target_rect = None

    if parent is not None and parent.isVisible():
        target_rect = parent.frameGeometry()

    if target_rect is None:
        screen = widget.screen()
        if screen is None:
            screen = QApplication.primaryScreen() or QGuiApplication.primaryScreen()
        if screen is None:
            return
        target_rect = screen.availableGeometry()

    frame = widget.frameGeometry()
    frame.moveCenter(target_rect.center())
    widget.move(frame.topLeft())
