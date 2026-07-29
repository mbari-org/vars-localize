"""
Bounding box data structure and interactive graphics items.
"""

from typing import Optional

from PyQt6.QtCore import Qt, QRectF, QPointF, QRect, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen, QFont, QFontMetrics
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsObject,
    QStyleOptionGraphicsItem,
    QWidget,
)

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


_EDGE_CURSORS = {
    "tl": Qt.CursorShape.SizeFDiagCursor,
    "br": Qt.CursorShape.SizeFDiagCursor,
    "tr": Qt.CursorShape.SizeBDiagCursor,
    "bl": Qt.CursorShape.SizeBDiagCursor,
    "t": Qt.CursorShape.SizeVerCursor,
    "b": Qt.CursorShape.SizeVerCursor,
    "l": Qt.CursorShape.SizeHorCursor,
    "r": Qt.CursorShape.SizeHorCursor,
}


class BoundingBoxLabelItem(QGraphicsItem):
    """Label chip anchored to the parent box's upper-left corner.

    Ignores the view's zoom transform so the label stays a legible, constant
    on-screen size regardless of how far the image is zoomed.
    """

    def __init__(self, parent: "BoundingBoxItem"):
        super().__init__(parent)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self.setZValue(1)
        self._font = QFont("Helvetica", 10, QFont.Weight.Bold)

    def _text(self) -> str:
        box = self.parentItem()
        text = box.label if box.label else "No label"
        if box.source.part is not None and box.source.part != "self":
            text += " " + box.source.part
        return text

    def _chip_size(self):
        fm = QFontMetrics(self._font)
        text = self._text()
        return fm.horizontalAdvance(text) + 10, fm.height() + 6

    def boundingRect(self) -> QRectF:
        if self.parentItem() is None:
            return QRectF()
        w, h = self._chip_size()
        return QRectF(0, -h, w, h)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        box = self.parentItem()
        if box is None:
            return
        rect = self.boundingRect()
        chip_color = QColor(box.color)
        chip_color.setAlpha(220)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(chip_color)
        painter.drawRect(rect)
        text_color = (
            QColor(PALETTE["bg_subtle"])
            if chip_color.lightnessF() > 0.55
            else QColor(PALETTE["fg_primary"])
        )
        painter.setPen(text_color)
        painter.setFont(self._font)
        painter.drawText(
            rect.adjusted(5, 2, -3, -2),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self._text(),
        )


class BoundingBoxItem(QGraphicsObject):
    """Interactive graphical bounding box.

    Supports native Qt selection and drag-edge/corner-to-resize (dragging the
    box body does not move it -- that instead pans the view, see ImageView).
    Geometry is only written back to `source` (and `geometryCommitted` emitted)
    once a drag completes, matching the "mutate live, persist once" cadence the
    server API expects.
    """

    geometryCommitted = pyqtSignal(object)
    contextMenuRequested = pyqtSignal(object, QPointF)
    resizeStarted = pyqtSignal()
    resizeFinished = pyqtSignal()

    EDGE_MARGIN = 8.0
    MIN_SIZE = 4.0

    def __init__(self, source: SourceBoundingBox, editable: bool = True, parent=None):
        super().__init__(parent)

        self.source = source
        self.editable = editable
        self.label = None
        self.highlighted = False
        self.color = QColor(0, 0, 0)

        self._w = float(source.width())
        self._h = float(source.height())
        self._image_bounds = QRectF(0, 0, 1.0e9, 1.0e9)
        self._resize_edge: Optional[str] = None
        self._press_scene_rect: Optional[QRectF] = None
        self._press_scene_pos: Optional[QPointF] = None
        self._hovered = False

        # Deliberately no ItemIsMovable: dragging a box body pans the view
        # instead (see ImageView.mousePressEvent) -- only the edge/corner
        # handles resize a box. This keeps panning available even when a
        # smaller box sits inside a larger one at high zoom.
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        if editable:
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
            self.setAcceptHoverEvents(True)

        self._label_item = BoundingBoxLabelItem(self)

        self.setPos(float(source.x()), float(source.y()))
        self.set_label(source.label)

    def set_image_bounds(self, bounds: QRectF):
        """Constrain move/resize to stay within these scene-space bounds."""
        self._image_bounds = bounds

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
        self._w = float(w)
        self._h = float(h)
        self._update_z_value()

    def set_label(self, label):
        """Set the display label for the bounding box.

        Args:
            label: Bounding box label.
        """
        self.label = label
        if self.editable:
            hue = utils.n_split_hash(label, 1)[0]
            self.color = QColor()
            self.color.setHsv(hue, 150, 230)
        else:
            self.color = QColor(PALETTE["fg_muted"])
            self.color.setAlpha(150)
        self.update()
        self._label_item.update()

    def set_highlighted(self, highlighted: bool):
        """Set whether the box is highlighted.

        Args:
            highlighted: Highlight on or off.
        """
        self.highlighted = bool(highlighted)
        self.update()

    def area(self):
        """Compute the area of the box.

        Returns:
            float: Box area.
        """
        return self._w * self._h

    def _update_z_value(self):
        # Prefer selecting/hit-testing smaller (e.g. nested) boxes over larger
        # enclosing ones when they overlap, by keeping them visually on top.
        base = 100.0 if self.editable else 0.0
        area = max(1.0, self.area())
        self.setZValue(base + max(0.0, 50.0 - (area**0.5) / 20.0))

    def rect(self) -> QRectF:
        return QRectF(0, 0, self._w, self._h)

    def boundingRect(self) -> QRectF:
        pad = 3
        return QRectF(-pad, -pad, self._w + 2 * pad, self._h + 2 * pad)

    def _edge_at(self, pos: QPointF) -> Optional[str]:
        if not self.editable:
            return None
        r = self.rect()
        m = self.EDGE_MARGIN
        if not r.adjusted(-m, -m, m, m).contains(pos):
            return None
        near_left = abs(pos.x() - r.left()) <= m
        near_right = abs(pos.x() - r.right()) <= m
        near_top = abs(pos.y() - r.top()) <= m
        near_bottom = abs(pos.y() - r.bottom()) <= m
        if near_top and near_left:
            return "tl"
        if near_top and near_right:
            return "tr"
        if near_bottom and near_left:
            return "bl"
        if near_bottom and near_right:
            return "br"
        if near_top:
            return "t"
        if near_bottom:
            return "b"
        if near_left:
            return "l"
        if near_right:
            return "r"
        return None

    def edge_at_scene_point(self, scene_pos: QPointF) -> Optional[str]:
        """Return which resize edge/corner (if any) a scene-space point falls on."""
        return self._edge_at(self.mapFromScene(scene_pos))

    def hoverMoveEvent(self, event):
        edge = self._edge_at(event.pos())
        if edge is not None:
            self.setCursor(_EDGE_CURSORS[edge])
        else:
            # Over the box body (not a handle): cede cursor control back to
            # the view, which shows the pan cursor there.
            self.unsetCursor()
        super().hoverMoveEvent(event)

    def hoverEnterEvent(self, event):
        self._hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hovered = False
        self.unsetCursor()
        self.update()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.editable:
            self._resize_edge = self._edge_at(event.pos())
        else:
            self._resize_edge = None

        if self._resize_edge is not None:
            self._press_scene_rect = QRectF(
                self.pos().x(), self.pos().y(), self._w, self._h
            )
            self._press_scene_pos = event.scenePos()
            self.resizeStarted.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resize_edge is not None:
            self._apply_resize(event.scenePos())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._resize_edge is not None:
            self._resize_edge = None
            if self._commit_geometry_to_source():
                self.geometryCommitted.emit(self)
            self.resizeFinished.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)
        if self._commit_geometry_to_source():
            self.geometryCommitted.emit(self)

    def contextMenuEvent(self, event):
        if not self.editable:
            event.ignore()
            return
        self.contextMenuRequested.emit(self, event.scenePos())
        event.accept()

    def _apply_resize(self, scene_pos: QPointF):
        delta = scene_pos - self._press_scene_pos
        rect = self._press_scene_rect
        edge = self._resize_edge

        left, top = rect.left(), rect.top()
        right, bottom = rect.right(), rect.bottom()
        if "l" in edge:
            left += delta.x()
        if "r" in edge:
            right += delta.x()
        if "t" in edge:
            top += delta.y()
        if "b" in edge:
            bottom += delta.y()

        bounds = self._image_bounds
        left = max(bounds.left(), left)
        top = max(bounds.top(), top)
        right = min(bounds.right(), right)
        bottom = min(bounds.bottom(), bottom)

        if right - left < self.MIN_SIZE:
            if "l" in edge:
                left = right - self.MIN_SIZE
            else:
                right = left + self.MIN_SIZE
        if bottom - top < self.MIN_SIZE:
            if "t" in edge:
                top = bottom - self.MIN_SIZE
            else:
                bottom = top + self.MIN_SIZE

        self.prepareGeometryChange()
        self.setPos(left, top)
        self._w = right - left
        self._h = bottom - top
        self._update_z_value()
        self.update()

    def _commit_geometry_to_source(self) -> bool:
        x, y = int(round(self.pos().x())), int(round(self.pos().y()))
        w, h = int(round(self._w)), int(round(self._h))
        changed = (
            x != self.source.x()
            or y != self.source.y()
            or w != self.source.width()
            or h != self.source.height()
        )
        if changed:
            self.source.setRect(x, y, w, h)
        return changed

    def itemChange(self, change, value):
        if (
            change == QGraphicsItem.GraphicsItemChange.ItemPositionChange
            and self.scene() is not None
        ):
            bounds = self._image_bounds
            max_x = max(bounds.left(), bounds.right() - self._w)
            max_y = max(bounds.top(), bounds.bottom() - self._h)
            x = min(max(value.x(), bounds.left()), max_x)
            y = min(max(value.y(), bounds.top()), max_y)
            return QPointF(x, y)
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.update()
        return super().itemChange(change, value)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: Optional[QWidget] = None,
    ) -> None:
        """Paint the item within the scene."""
        if not self.editable:
            pen = QPen(self.color, 1)
        else:
            pen = QPen(self.color.lighter(), 1)
            if self._hovered and not self.isSelected():
                pen.setWidth(2)
                pen.setStyle(Qt.PenStyle.DashLine)
            if self.highlighted:
                pen.setWidth(2)
            if self.isSelected():
                pen = QPen(QColor(PALETTE["accent"]), 2)

        # Cosmetic: line width stays constant in screen pixels regardless of zoom.
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self.rect())

        if self.isSelected():
            ring_pen = QPen(QColor(PALETTE["selection_ring"]), 1, Qt.PenStyle.DashLine)
            ring_pen.setCosmetic(True)
            painter.setPen(ring_pen)
            painter.drawRect(self.rect().adjusted(-4, -4, 4, 4))
