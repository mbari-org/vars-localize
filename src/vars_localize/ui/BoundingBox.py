"""
Bounding box data structure and manager helper class.
"""

import typing

from PyQt6.QtCore import Qt, QRectF, QPoint, QSizeF, QRect, QPointF
from PyQt6.QtGui import QColor, QPainter, QPen, QFont
from PyQt6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem, QWidget

from vars_localize.ui.theme import PALETTE
from vars_localize.util import utils


class SourceBoundingBox(QRect):
    """Bounding box VARS source data structure"""

    def __init__(
        self,
        box_json,
        label,
        observer=None,
        observation_uuid=None,
        association_uuid=None,
        part=None,
    ):
        super(SourceBoundingBox, self).__init__(
            box_json["x"], box_json["y"], box_json["width"], box_json["height"]
        )
        self.image_reference_uuid = box_json.get("image_reference_uuid", None)
        self.observation_uuid = observation_uuid
        self.association_uuid = association_uuid
        self.part = part
        self.label = label
        self.observer = observer

    def set_label(self, label):
        self.label = label

    def get_json(self):
        d = {
            "x": self.x(),
            "y": self.y(),
            "width": self.width(),
            "height": self.height(),
            "generator": "vars-localize",
            "image_reference_uuid": self.image_reference_uuid,
        }

        if self.observer is not None:
            d["observer"] = self.observer

        return d


class GraphicsBoundingBox(QGraphicsItem):
    """Graphical bounding box representation"""

    def __init__(self, source: SourceBoundingBox, editable: bool = True):
        super(GraphicsBoundingBox, self).__init__()

        self.source = source
        self.editable = editable

        self.width = 0
        self.height = 0
        self.label = None
        self.highlighted = False
        self.color = QColor(0, 0, 0)

    def set_box(self, x, y, w, h):
        """Update box position and dimensions.

        Args:
            x: X position.
            y: Y position.
            w: Width.
            h: Height.
        """
        self.prepareGeometryChange()
        self.setPos(x, y)
        self.width = w
        self.height = h

    def set_label(self, label):
        """Set the display label for the bounding box.

        Args:
            label: Bounding box label.
        """
        self.label = label
        if self.editable:
            hue = utils.n_split_hash(label, 1)[0]
            self.color.setHsv(hue, 150, 230)
        else:
            self.color = QColor(PALETTE["fg_muted"])
            self.color.setAlpha(150)

    def set_highlighted(self, highlighted: bool):
        """Set whether the box is highlighted.

        Args:
            highlighted: Highlight on or off.
        """
        self.highlighted = highlighted

    def area(self):
        """Compute the area of the box.

        Returns:
            int: Box area.
        """
        return self.width * self.height

    def boundingRect(self) -> QRectF:
        """Return the graphics item's bounding rectangle.

        Returns:
            QRectF: Bounding rectangle of box (not including label text).
        """
        return QRectF(QPointF(0, 0), QSizeF(self.width, self.height))

    def contains(self, pt: QPoint):
        """Check whether a point lies within this box.

        Args:
            pt: Point to check.

        Returns:
            bool: True if point is inside this box, else False.
        """
        return (
            self.x() <= pt.x() <= self.x() + self.width
            and self.y() <= pt.y() <= self.y() + self.height
        )

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: typing.Optional[QWidget] = ...,
    ) -> None:
        """Paint the item within the scene.

        Args:
            painter: Painter object.
            option: Style option.
            widget: Optional widget.
        """
        pen = QPen(self.color.lighter(), 4 if self.highlighted else 2)
        painter.setPen(pen)
        painter.drawRect(0, 0, int(self.width), int(self.height))

        painter.setFont(QFont("Helvetica", 12, QFont.Weight.Bold))
        draw_text = self.label if self.label else "No label"
        if self.source.part is not None and self.source.part != "self":
            draw_text += " " + self.source.part
        painter.drawText(
            0,
            int(self.height),
            int(self.width),
            20,
            Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextDontClip,
            draw_text,
        )


class BoundingBoxManager:
    """Manages a list of graphical bounding box objects"""

    def __init__(self, bounding_boxes: list = None):
        if bounding_boxes:
            self.bounding_boxes = bounding_boxes
        else:
            self.bounding_boxes = []

        self.box_click_callback = None
        self.box_right_click_callback = None

    def make_box(self, x, y, w, h, label, src, editable: bool = True):
        """Create a box and add it to this manager.

        Args:
            x: X position.
            y: Y position.
            w: Width.
            h: Height.
            label: Bounding box label.
            src: Source bounding box.
            editable: Whether the box is editable.

        Returns:
            GraphicsBoundingBox: The created graphics item.
        """
        box = GraphicsBoundingBox(src, editable=editable)
        box.set_box(x, y, w, h)
        box.set_label(label)
        self.bounding_boxes.append(box)
        return box

    def set_box_click_callback(self, func):
        """Set callback function invoked on box click.

        Args:
            func: Callback function.
        """
        self.box_click_callback = func

    def set_box_right_click_callback(self, func):
        """Set callback function invoked on box right-click.

        Args:
            func: Callback function.
        """
        self.box_right_click_callback = func

    def check_box_click(self, pt: QPoint, right_click: bool):
        """Check managed boxes for a click and dispatch callbacks.

        Args:
            pt: Point to process.
            right_click: Whether the click is a right click.
        """
        selected_box = None
        for box in self.bounding_boxes:
            if box.contains(pt) and box.editable:
                if not selected_box or box.area() < selected_box.area():
                    selected_box = box
        if self.box_click_callback:
            if selected_box:
                if right_click:
                    self.box_right_click_callback(selected_box)
                else:
                    self.box_click_callback(selected_box)

    def get_box_hovered(self, pt: QPoint):
        """Return the hovered editable box, if any.

        Args:
            pt: Point to process.

        Returns:
            GraphicsBoundingBox | None: Hovered box, if any.
        """
        hovered_box = None
        for box in self.bounding_boxes:
            if box.contains(pt) and box.editable:
                if not hovered_box or box.area() < hovered_box.area():
                    hovered_box = box
        return hovered_box

    def boxes(self):
        return self.bounding_boxes

    def clear(self):
        self.bounding_boxes.clear()
