# BoundingBox.py (vars-localize)
import typing

from PyQt5.QtCore import Qt, QRectF, QPoint, QSizeF, QRect, QPointF
from PyQt5.QtGui import QColor, QPainter, QPen, QFont
from PyQt5.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem, QWidget

import util.requests
import util.utils

__author__ = "Kevin Barnard"
__copyright__ = "Copyright 2019, Monterey Bay Aquarium Research Institute"
__credits__ = ["MBARI"]
__license__ = "GPL"
__maintainer__ = "Kevin Barnard"
__email__ = "kbarnard@mbari.org"
__doc__ = '''

Bounding box data structure and manager helper class.

@author: __author__
@status: __status__
@license: __license__
'''


class SourceBoundingBox(QRect):
    """ Bounding box VARS source data structure """

    def __init__(self, box_json, label, observer, strength, observation_uuid=None, association_uuid=None, part=None):
        super(SourceBoundingBox, self).__init__(
            box_json['x'],
            box_json['y'],
            box_json['width'],
            box_json['height']
        )
        self.image_reference_uuid = box_json['image_reference_uuid']
        self.observation_uuid = observation_uuid
        self.association_uuid = association_uuid
        self.part = part
        self.label = label
        self.observer = observer
        self.strength = strength

    def set_label(self, label):
        if label in util.requests.get_all_concepts():
            self.label = label

    def get_json(self):
        return {
            'x': self.x(),
            'y': self.y(),
            'width': self.width(),
            'height': self.height(),
            'observer': self.observer,
            'strength': self.strength,
            'generator': 'vars-localize',
            'project': 'FathomNet',
            'image_reference_uuid': self.image_reference_uuid
        }


class GraphicsBoundingBox(QGraphicsItem):
    """ Graphical bounding box representation """

    def __init__(self, source: SourceBoundingBox):
        super(GraphicsBoundingBox, self).__init__()

        self.source = source

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
        self.color.setHsv(*util.utils.n_split_hash(label, 1), 255, 255)

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
        return self.x() <= pt.x() <= self.x() + self.width and self.y() <= pt.y() <= self.y() + self.height

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem,
              widget: typing.Optional[QWidget] = ...) -> None:
        """
        Paint the item within the scene
        :param painter: Painter object
        :param option: Style object
        :param widget: Optional widget
        :return:
        """
        pen = QPen(self.color.lighter(), 4 if self.highlighted else 2)
        painter.setPen(pen)
        painter.drawRect(0, 0, self.width, self.height)

        painter.setFont(QFont('Helvetica', 12, QFont.Bold))
        draw_text = self.label if self.label else 'No label'
        if self.source.part is not None and self.source.part != 'self':
            draw_text += ' ' + self.source.part
        painter.drawText(0, self.height,
                         self.width, 20,
                         Qt.AlignCenter | Qt.TextDontClip,
                         draw_text)


class BoundingBoxManager:
    """ Manages a list of graphical bounding box objects """

    def __init__(self, bounding_boxes: list = None):
        if bounding_boxes:
            self.bounding_boxes = bounding_boxes
        else:
            self.bounding_boxes = []

        self.box_click_callback = None

    def make_box(self, x, y, w, h, label, src):
        """
        Create a box and add it to the manager
        :param x: x position
        :param y: y position
        :param w: Width
        :param h: Height
        :param label: Bounding box label
        :param src: Source bounding box
        :return: Graphical bounding box item
        """
        box = GraphicsBoundingBox(src)
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

    def check_box_click(self, pt: QPoint):
        """
        Check managed boxes for point containment, process callbacks
        :param pt: Point to process
        :return: None
        """
        selected_box = None
        for box in self.bounding_boxes:
            if box.contains(pt):
                if not selected_box or box.area() < selected_box.area():
                    selected_box = box
        if self.box_click_callback:
            if selected_box:
                self.box_click_callback(selected_box)

    def get_box_hovered(self, pt: QPoint):
        """
        Check managed boxes for point containment, return hovered box if any
        :param pt: Point to process
        :return: Hovered box, if any
        """
        hovered_box = None
        for box in self.bounding_boxes:
            if box.contains(pt):
                if not hovered_box or box.area() < hovered_box.area():
                    hovered_box = box
        return hovered_box

    def boxes(self):
        return self.bounding_boxes

    def clear(self):
        self.bounding_boxes.clear()
