"""
Bounding box data structure and manager helper class.
"""

import typing

from PyQt6.QtCore import Qt, QRectF, QPoint, QSizeF, QRect, QPointF
from PyQt6.QtGui import QColor, QPainter, QPen, QFont
from PyQt6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem, QWidget

from vars_localize.util import m3, utils


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
        if label in m3.get_all_concepts():
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
        """
        Update box position and dimensions
        :param x: x position
        :param y: y position
        :param w: Width
        :param h: Height
        :return: None
        """
        self.prepareGeometryChange()
        self.setPos(x, y)
        self.width = w
        self.height = h

    def set_label(self, label):
        """
        Set the label of the bounding box
        :param label: Bounding box label
        :return: None
        """
        self.label = label
        if self.editable:
            self.color.setHsv(*utils.n_split_hash(label, 1), 255, 255)
        else:
            # If not editable, set color to gray with 50% opacity
            self.color.setHsv(0, 0, 128, alpha=128)

    def set_highlighted(self, highlighted: bool):
        """
        Set the highlight status of the bounding box
        :param highlighted: Highlight on or off
        :return: None
        """
        self.highlighted = highlighted

    def area(self):
        """
        Compute the area of the box
        :return: Box area
        """
        return self.width * self.height

    def boundingRect(self) -> QRectF:
        """
        Give the bounding rectangle of the graphics item
        :return: Bounding rectangle of box (not including label)
        """
        return QRectF(QPointF(0, 0), QSizeF(self.width, self.height))

    def contains(self, pt: QPoint):
        """
        Check if the given point lies within the bounding box
        :param pt: Point to check
        :return: True if point within box, else False
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
        """
        Paint the item within the scene
        :param painter: Painter object
        :param option: Style object
        :param widget: Optional widget
        :return:
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
        """
        Create a box and add it to the manager
        :param x: x position
        :param y: y position
        :param w: Width
        :param h: Height
        :param label: Bounding box label
        :param src: Source bounding box
        :param editable: Whether the box is editable
        :return: Graphical bounding box item
        """
        box = GraphicsBoundingBox(src, editable=editable)
        box.set_box(x, y, w, h)
        box.set_label(label)
        self.bounding_boxes.append(box)
        return box

    def set_box_click_callback(self, func):
        """
        Set the callback function for when the box is clicked
        :param func: Callback function
        :return: None
        """
        self.box_click_callback = func

    def set_box_right_click_callback(self, func):
        """
        Set the callback function for when the box is clicked
        :param func: Callback function
        :return: None
        """
        self.box_right_click_callback = func

    def check_box_click(self, pt: QPoint, right_click: bool):
        """
        Check managed boxes for point containment, process callbacks
        :param pt: Point to process
        :return: None
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
        """
        Check managed boxes for point containment, return hovered box if any
        :param pt: Point to process
        :return: Hovered box, if any
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
