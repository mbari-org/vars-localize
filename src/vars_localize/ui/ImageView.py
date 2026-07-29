"""Custom QGraphicsView widget for controlling image/localization graphics and input."""

from __future__ import annotations

from typing import Callable, List, Optional, Any, cast

from PyQt6.QtCore import Qt, QPoint, QPointF, QRectF, QLineF, QTimer
from PyQt6.QtGui import (
    QEnterEvent,
    QImage,
    QResizeEvent,
    QMouseEvent,
    QWheelEvent,
    QPixmap,
    QColor,
    QKeyEvent,
    QPen,
    QPainter,
)
from PyQt6.QtWidgets import (
    QGraphicsView,
    QGraphicsScene,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsLineItem,
    QDialog,
    QVBoxLayout,
    QPushButton,
    QMessageBox,
    QMenu,
    QLabel,
)

from vars_localize.ui.ConceptSearchbar import ConceptSearchbar
from vars_localize.ui.EntryTree import EntryTreeItem
from vars_localize.models import ImagedMomentEntry
from vars_localize.ui.BoundingBox import BoundingBoxItem, SourceBoundingBox
from vars_localize.ui.PropertiesDialog import PropertiesDialog
from vars_localize.ui.theme import PALETTE
from vars_localize.services import M3Service
from vars_localize.services.errors import ServiceError
from vars_localize.util.logging import get_logger
from vars_localize.util.qt_async import run_async
from vars_localize.util.utils import center_window

logger = get_logger("ImageView")


class _MinimapView(QGraphicsView):
    """Small always-visible overview of the full image with a viewport indicator.

    Uses its own private scene containing only the image pixmap -- box/label
    annotations and SAM overlays from the main view never appear here.
    """

    def __init__(self, main_view: "ImageView", parent=None):
        super().__init__(QGraphicsScene(), parent)
        self._main = main_view
        self._pixmap_item: Optional[QGraphicsPixmapItem] = None
        self.setInteractive(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setFixedSize(180, 140)
        self.setStyleSheet(
            "QGraphicsView {{ border: 1px solid {0}; background-color: {1}; }}".format(
                PALETTE["border"], PALETTE["bg_subtle"]
            )
        )
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.hide()

    def set_pixmap(self, pixmap: Optional[QPixmap]):
        if pixmap is None or pixmap.isNull():
            if self._pixmap_item is not None:
                self.scene().removeItem(self._pixmap_item)
                self._pixmap_item = None
            self.hide()
            return
        if self._pixmap_item is None:
            self._pixmap_item = self.scene().addPixmap(pixmap)
        else:
            self._pixmap_item.setPixmap(pixmap)
        self._pixmap_item.setPos(0, 0)
        self.scene().setSceneRect(0, 0, pixmap.width(), pixmap.height())
        self.fitInView(self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

    def reposition(self):
        margin = 10
        parent = self.parentWidget()
        if parent is None:
            return
        self.move(parent.width() - self.width() - margin, margin)

    def update_visibility(self):
        if self._pixmap_item is None:
            self.hide()
            return
        current_scale = self._main.transform().m11()
        self.setVisible(current_scale > self._main._fit_scale() * 1.02)

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawForeground(painter, rect)
        if self._pixmap_item is None:
            return
        visible_scene_rect = self._main.mapToScene(
            self._main.viewport().rect()
        ).boundingRect()
        pen = QPen(QColor(PALETTE["accent"]), 2)
        pen.setCosmetic(True)
        painter.setPen(pen)
        fill = QColor(PALETTE["accent"])
        fill.setAlpha(40)
        painter.setBrush(fill)
        painter.drawRect(visible_scene_rect)

    def wheelEvent(self, event) -> None:
        event.ignore()

    def mousePressEvent(self, event) -> None:
        self._navigate_to(event.pos())

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._navigate_to(event.pos())

    def _navigate_to(self, viewport_pos: QPoint):
        self._main.centerOn(self.mapToScene(viewport_pos))
        self._main._sync_minimap()


class ImageView(QGraphicsView):
    SAM_MIN_AREA = 100
    SAM_OVERLAP_IOU = 0.2

    MIN_SCALE = 0.1
    MAX_SCALE = 20.0
    ZOOM_STEP = 1.15
    CLICK_DRAG_THRESHOLD = 4

    def __init__(self, parent=None):
        super(ImageView, self).__init__(parent)

        self.setMinimumSize(1200, 675)
        self.setViewportMargins(-2, -2, -2, -2)
        self.setMouseTracking(True)

        self.image_scene = QGraphicsScene()
        self.setScene(self.image_scene)
        self.scene().setBackgroundBrush(QColor(PALETTE["bg_subtle"]))
        self.scene().selectionChanged.connect(self._on_scene_selection_changed)

        # Zoom anchoring is done manually in wheelEvent (using the event's own
        # position) rather than via AnchorUnderMouse, which re-queries the OS
        # cursor position and can desync from the wheel event's coordinates.
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        # Floating child widgets over the viewport (minimap, status/ancillary
        # labels) get corrupted by QGraphicsView's scroll-blit optimization
        # unless the viewport always fully repaints.
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)

        self.observation_uuid = None
        self.observer = None
        self.moment = None
        self.observation_map = None
        self.enabled_observations = None

        self.pixmap_src = None
        self.pixmap_item: Optional[QGraphicsPixmapItem] = None

        self.select_next = None
        self.select_prev = None
        self._observation_select_callback: Optional[Callable[[EntryTreeItem], None]] = (
            None
        )
        self.m3_service = None
        self.sam3_service = None

        # Graphical box selection / interaction state.
        self.pt_1 = None
        self.pt_2 = None
        self.selected_box = None
        self.resize_type = False
        self._suppress_selection_signal = False
        self._box_items: List[BoundingBoxItem] = []
        self._drag_rect_item: Optional[QGraphicsRectItem] = None
        self._sam_candidate_item: Optional[QGraphicsRectItem] = None
        self._sam_hover_item: Optional[QGraphicsRectItem] = None
        self._crosshair_h_item: Optional[QGraphicsLineItem] = None
        self._crosshair_v_item: Optional[QGraphicsLineItem] = None

        # Click+drag pans by default; Ctrl+click+drag draws a new box instead.
        self._panning = False
        self._pan_start_pos: Optional[QPoint] = None
        self._pan_start_scroll: Optional[tuple] = None
        self._current_cursor_shape: Optional[Qt.CursorShape] = None

        # Click-to-select state: a click (no drag) on overlapping boxes
        # cycles through them on repeated clicks at the same spot.
        self._last_select_click_pos: Optional[QPoint] = None
        self._last_select_candidates: List[BoundingBoxItem] = []
        self._last_select_cycle_index = 0

        # Saved view state while previewing a SAM candidate under the accept/reject buttons.
        self._focus_preview_saved: Optional[tuple] = None

        self._user_has_zoomed = False
        self._minimap: Optional[_MinimapView] = _MinimapView(
            self, parent=self.viewport()
        )

        self._status_label = QLabel(self.viewport())
        self._status_label.setStyleSheet(
            "color: {}; background: transparent; font-family: 'Courier New';".format(
                PALETTE["fg_primary"]
            )
        )
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.hide()

        self._ancillary_label = QLabel(self.viewport())
        self._ancillary_label.setStyleSheet(
            "color: {}; background: transparent; font-family: 'Courier New';".format(
                PALETTE["fg_primary"]
            )
        )
        self._ancillary_label.hide()

        self._image_loading = False
        self._image_loading_uuid = None
        self._image_loading_error = None

        self._sam_assist_enabled = False
        self._sam_semantic_enabled = True
        self._sam_point_enabled = True
        self._sam_ready_image_uuid = None
        self._sam_embedding_busy = False
        self._sam_embedding_request_uuid = None
        self._sam_failed_image_uuid = None
        self._sam_last_error_message: Optional[str] = None
        self._sam_candidate_boxes: List[SourceBoundingBox] = []
        self._sam_candidate_index = 0
        self._sam_candidate_observation_uuid = None
        self._sam_candidate_concept: Optional[str] = None
        self._sam_pending_concept: Optional[str] = None
        self._sam_pending_exemplar_concept: Optional[str] = None
        self._sam_hover_box: Optional[SourceBoundingBox] = None
        self._sam_hover_inflight = False
        self._sam_last_hover_point = None
        self._sam_candidate_ui_callback: Optional[Callable[[bool, int, int], None]] = (
            None
        )
        self._sam_status_ui_callback: Optional[Callable[[str], None]] = None
        self._mouse_in_view = False

        self._sam_min_area = self.SAM_MIN_AREA
        self._sam_overlap_iou = self.SAM_OVERLAP_IOU
        self._video_data_request_uuid = None
        self._active_annotation_concept: Optional[str] = None

    def configure_sam_params(self, min_area: int, overlap_iou: float):
        self._sam_min_area = max(1, int(min_area))
        self._sam_overlap_iou = max(0.0, min(1.0, float(overlap_iou)))

    def _m3_fetch_image(self, url: str):
        return self._require_m3_service().fetch_image_bytes(url)

    def _m3_get_all_parts(self):
        return self._require_m3_service().get_all_parts()

    def _m3_get_video_data(self, video_reference_uuid: str):
        return self._require_m3_service().get_video_data(video_reference_uuid)

    def _m3_create_observation(self, *args, **kwargs):
        return self._require_m3_service().create_observation(*args, **kwargs)

    def _m3_create_box(self, *args, **kwargs):
        return self._require_m3_service().create_box(*args, **kwargs)

    def _m3_modify_box(self, *args, **kwargs):
        return self._require_m3_service().modify_box(*args, **kwargs)

    def _m3_delete_box(self, *args, **kwargs):
        return self._require_m3_service().delete_box(*args, **kwargs)

    def _m3_delete_observation(self, *args, **kwargs):
        return self._require_m3_service().delete_observation(*args, **kwargs)

    def _require_m3_service(self) -> M3Service:
        if self.m3_service is None:
            raise RuntimeError("ImageView requires an injected M3Service instance")
        return self.m3_service

    def _count_bounding_box_associations(self, observation) -> int:
        associations = getattr(observation, "associations", []) or []
        assoc_boxes = sum(
            1
            for assoc in associations
            if getattr(assoc, "link_name", "") == "bounding box"
        )
        hydrated_boxes = len(getattr(observation, "boxes", []) or []) + len(
            getattr(observation, "video_boxes", []) or []
        )
        return max(assoc_boxes, hydrated_boxes)

    def _is_observation_owned(self, observation_uuid: str) -> bool:
        tree = self.moment.treeWidget() if self.moment is not None else None
        if tree is not None and observation_uuid in tree.editable_uuids:
            return True

        root = cast(Any, self.window())
        return bool(getattr(root, "admin_mode", False))

    def set_sam_candidate_ui_callback(self, callback: Callable[[bool, int, int], None]):
        self._sam_candidate_ui_callback = callback
        self._notify_sam_candidate_state()

    def set_observation_select_callback(
        self, callback: Callable[[EntryTreeItem], None]
    ):
        self._observation_select_callback = callback

    def _has_scene(self) -> bool:
        try:
            return self.scene() is not None
        except RuntimeError:
            return False

    def _clear_scene_selection(self):
        if not self._has_scene():
            return
        self._suppress_selection_signal = True
        try:
            self.scene().clearSelection()
        finally:
            self._suppress_selection_signal = False

    def _find_box_item(self, box: SourceBoundingBox) -> Optional[BoundingBoxItem]:
        for item in self._box_items:
            if item.source is box:
                return item
        return None

    def _refresh_highlighting(self):
        for item in self._box_items:
            item.set_highlighted(self._box_is_highlighted(item.source))

    def _on_scene_selection_changed(self):
        if self._suppress_selection_signal:
            return
        selected = [
            it for it in self.scene().selectedItems() if isinstance(it, BoundingBoxItem)
        ]
        if selected:
            box_item = selected[0]
            self.selected_box = box_item.source
            new_obs_uuid = box_item.source.observation_uuid
            if new_obs_uuid and new_obs_uuid != self.observation_uuid:
                self.observation_uuid = new_obs_uuid
                if (
                    self._observation_select_callback is not None
                    and self.observation_map
                ):
                    entry = self.observation_map.get(new_obs_uuid)
                    if entry is not None:
                        self._observation_select_callback(entry)
        else:
            self.selected_box = None
        self._refresh_highlighting()

    def set_annotation_focus(
        self,
        concept_filter: Optional[str] = None,
        observation_uuid: Optional[str] = None,
    ):
        previous_concept = self._active_annotation_concept
        self._active_annotation_concept = (
            str(concept_filter) if concept_filter else None
        )
        concept_changed = previous_concept != self._active_annotation_concept

        if not self.enabled_observations or not self.observation_map:
            return

        for uuid in self.enabled_observations.keys():
            if self._active_annotation_concept is None:
                self.enabled_observations[uuid] = True
            else:
                concept = self.observation_map[uuid].observation.concept
                self.enabled_observations[uuid] = (
                    concept == self._active_annotation_concept
                )

        if observation_uuid and observation_uuid in self.observation_map:
            self.observation_uuid = observation_uuid
            self.selected_box = None
        else:
            self.observation_uuid = None
            self.selected_box = None
        self._clear_scene_selection()
        self._sam_hover_box = None
        if concept_changed:
            self._sam_candidate_boxes = []
            self._sam_candidate_index = 0
            self._notify_sam_candidate_state()
            if self._active_annotation_concept and getattr(
                self, "_sam_semantic_enabled", True
            ):
                self._start_sam_candidates_for_concept(self._active_annotation_concept)
            else:
                self._sam_pending_concept = None
                self._notify_sam_status(self._build_sam_status())
        else:
            self._notify_sam_candidate_state()
        self.redraw()

    def _box_is_highlighted(self, box: SourceBoundingBox) -> bool:
        if self.selected_box is not None:
            return self.selected_box == box
        if self.observation_uuid is None:
            return False
        return box.observation_uuid == self.observation_uuid

    @staticmethod
    def _bytes_to_pixmap(image_bytes: bytes) -> Optional[QPixmap]:
        if not image_bytes:
            return None
        pixmap = QPixmap()
        if not pixmap.loadFromData(image_bytes):
            return None
        return pixmap

    @staticmethod
    def _as_source_box(raw_box: Any, concept: str) -> SourceBoundingBox:
        if isinstance(raw_box, SourceBoundingBox):
            return raw_box

        box_dict = dict(raw_box or {})
        box_json = {
            "x": int(box_dict.get("x", 0)),
            "y": int(box_dict.get("y", 0)),
            "width": int(box_dict.get("width", 0)),
            "height": int(box_dict.get("height", 0)),
            "image_reference_uuid": box_dict.get("image_reference_uuid"),
        }
        return SourceBoundingBox(
            box_json,
            concept,
            observer=box_dict.get("observer"),
            observation_uuid=box_dict.get("observation_uuid"),
            association_uuid=box_dict.get("association_uuid"),
            part=box_dict.get("part"),
        )

    def _hydrate_observation_boxes(self, observation):
        observation.boxes = [
            self._as_source_box(box, observation.concept)
            for box in list(observation.boxes or [])
        ]
        observation.video_boxes = [
            self._as_source_box(box, observation.concept)
            for box in list(observation.video_boxes or [])
        ]

    def _ensure_video_data_loaded(self, moment: ImagedMomentEntry):
        if moment.video_data is not None or not moment.video_reference_uuid:
            return

        request_uuid = moment.uuid
        self._video_data_request_uuid = request_uuid

        def _on_result(video_data):
            if self.moment is None or self._video_data_request_uuid != request_uuid:
                return
            if self.moment.imaged_moment.uuid != request_uuid:
                return
            self.moment.imaged_moment.video_data = (
                video_data if isinstance(video_data, dict) else None
            )
            self.redraw()

        def _on_error(err):
            logger.warning("Video metadata preload failed: {}", err)

        run_async(
            self,
            self._m3_get_video_data,
            moment.video_reference_uuid,
            on_result=_on_result,
            on_error=_on_error,
        )

    def set_sam_status_ui_callback(self, callback: Callable[[str], None]):
        self._sam_status_ui_callback = callback
        self._notify_sam_status(self._build_sam_status())

    def _notify_sam_status(self, status: str):
        if self._sam_status_ui_callback is None:
            return
        self._sam_status_ui_callback(status)

    def _point_capability_text(self) -> str:
        if not getattr(self, "_sam_point_enabled", True):
            return "point prompts disabled"
        if self.sam3_service is None or not self.sam3_service.available:
            return "point prompts unavailable"

        state = getattr(self.sam3_service, "point_prompt_state", "unavailable")
        if state == "ready":
            return "point prompts ready"
        if state == "loading":
            return "point prompts syncing"
        if state == "lazy":
            return "point prompts load on first hover"
        return "point prompts unavailable"

    def _semantic_capability_text(self) -> str:
        if not getattr(self, "_sam_semantic_enabled", True):
            return "text prompts disabled"
        return "text prompts ready"

    def _build_sam_status(self) -> str:
        if self.sam3_service is None or not self.sam3_service.available:
            return "SAM unavailable"
        if not self._sam_assist_enabled:
            return "SAM disabled"
        if self.moment is None or self.pixmap_src is None:
            return "SAM enabled, waiting for image"
        if self._sam_embedding_busy:
            return "SAM loading image embedding..."
        current_uuid = self.moment.imaged_moment.uuid
        if self._sam_failed_image_uuid == current_uuid:
            return self._sam_last_error_message or "SAM embedding failed"
        if self._sam_ready_image_uuid == self.moment.imaged_moment.uuid:
            return "SAM ready: {}, {}".format(
                self._semantic_capability_text(), self._point_capability_text()
            )
        return "SAM enabled, embedding not ready"

    @staticmethod
    def _is_cuda_oom_error(err: Exception) -> bool:
        text = str(err).lower()
        return "out of memory" in text and "cuda" in text

    def set_sam_assist_enabled(self, enabled: bool):
        is_available = bool(
            self.sam3_service is not None and self.sam3_service.available
        )
        self._sam_assist_enabled = bool(enabled and is_available)
        if not self._sam_assist_enabled:
            self._clear_sam_state(reset_embedding=False)
        else:
            self._maybe_start_sam_embedding()
        self._notify_sam_status(self._build_sam_status())
        self.redraw()

    def set_sam_prompt_modes(self, semantic_enabled: bool, point_enabled: bool):
        self._sam_semantic_enabled = bool(semantic_enabled)
        self._sam_point_enabled = bool(point_enabled)

        if not self._sam_semantic_enabled:
            self._sam_candidate_boxes = []
            self._sam_candidate_index = 0
            self._sam_pending_concept = None
            self._sam_pending_exemplar_concept = None

        if not self._sam_point_enabled:
            self._sam_hover_box = None
            self._sam_hover_inflight = False
            self._sam_last_hover_point = None

        self._notify_sam_candidate_state()
        self._notify_sam_status(self._build_sam_status())
        self.redraw()

    def _notify_sam_candidate_state(self):
        if self._sam_candidate_ui_callback is None:
            return
        has_candidates = bool(self._sam_candidate_boxes)
        self._sam_candidate_ui_callback(
            has_candidates,
            self._sam_candidate_index,
            len(self._sam_candidate_boxes),
        )

    def _clear_sam_state(self, reset_embedding: bool = True):
        self._sam_candidate_boxes = []
        self._sam_candidate_index = 0
        self._sam_candidate_observation_uuid = None
        self._sam_candidate_concept = None
        self._sam_pending_concept = None
        self._sam_pending_exemplar_concept = None
        self._sam_hover_box = None
        self._sam_hover_inflight = False
        self._sam_last_hover_point = None
        if reset_embedding:
            self._sam_ready_image_uuid = None
            self._sam_embedding_request_uuid = None
            self._sam_failed_image_uuid = None
            self._sam_last_error_message = None
        self._notify_sam_candidate_state()
        self._notify_sam_status(self._build_sam_status())

    @property
    def _current_sam_candidate(self) -> Optional[SourceBoundingBox]:
        if not self._sam_candidate_boxes:
            return None
        idx = max(0, min(self._sam_candidate_index, len(self._sam_candidate_boxes) - 1))
        return self._sam_candidate_boxes[idx]

    def accept_sam_candidate(self):
        candidate = self._current_sam_candidate
        if candidate is None:
            return
        try:
            had_selected_observation = bool(self.observation_uuid)
            self.handle_new_box(
                candidate,
                refresh=False,
                preserve_sam_state=True,
            )
            self._drop_current_candidate()
            if had_selected_observation:
                self.set_annotation_focus(
                    concept_filter=self._active_annotation_concept,
                    observation_uuid=None,
                )
            self.reload_moment(preserve_sam_state=True)
        except Exception as exc:
            QMessageBox.warning(self, "Box creation failed", str(exc))
        self.redraw()

    def reject_sam_candidate(self):
        if self._current_sam_candidate is None:
            return
        self._drop_current_candidate()
        self.redraw()

    def _drop_current_candidate(self):
        if not self._sam_candidate_boxes:
            return
        idx = max(0, min(self._sam_candidate_index, len(self._sam_candidate_boxes) - 1))
        self._sam_candidate_boxes.pop(idx)
        if self._sam_candidate_index >= len(self._sam_candidate_boxes):
            self._sam_candidate_index = max(0, len(self._sam_candidate_boxes) - 1)
        self._notify_sam_candidate_state()

    def _pixmap_to_rgb_ndarray(self, pixmap: QPixmap):
        import numpy as np

        image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGB888)
        width = image.width()
        height = image.height()
        ptr = image.bits()
        ptr.setsize(image.sizeInBytes())
        arr = np.frombuffer(ptr, np.uint8).reshape((height, image.bytesPerLine()))
        arr = arr[:, : width * 3].reshape((height, width, 3)).copy()
        return arr

    def _sam_query_text(self, concept: str):
        if self.sam3_service is None:
            return []
        return self.sam3_service.query_text(concept)

    def _sam_query_point(self, x: int, y: int):
        if self.sam3_service is None:
            return []
        return self.sam3_service.query_point(x, y)

    def _maybe_start_sam_embedding(self):
        if not self._sam_assist_enabled:
            self._notify_sam_status(self._build_sam_status())
            return
        if self.moment is None or self.pixmap_src is None:
            self._notify_sam_status(self._build_sam_status())
            return
        if self.sam3_service is None or not self.sam3_service.available:
            self._notify_sam_status(self._build_sam_status())
            return

        moment_uuid = self.moment.imaged_moment.uuid
        if (
            self._sam_ready_image_uuid == moment_uuid
            or self._sam_embedding_busy
            or self._sam_failed_image_uuid == moment_uuid
        ):
            self._notify_sam_status(self._build_sam_status())
            return

        self._sam_embedding_busy = True
        self._sam_embedding_request_uuid = moment_uuid
        self._notify_sam_status("SAM loading image embedding...")

        def _embed():
            if self._sam_embedding_request_uuid != moment_uuid:
                return None
            image_rgb = self._pixmap_to_rgb_ndarray(self.pixmap_src)
            self.sam3_service.set_image(image_rgb, image_key=moment_uuid)
            return moment_uuid

        def _on_result(embedded_uuid: Optional[str]):
            if embedded_uuid is None:
                return
            current_uuid = self.moment.imaged_moment.uuid if self.moment else None
            if current_uuid != embedded_uuid:
                return
            self._sam_ready_image_uuid = embedded_uuid
            self._sam_failed_image_uuid = None
            self._sam_last_error_message = None
            self._notify_sam_status(self._build_sam_status())
            pending_concept = self._sam_pending_concept
            if pending_concept:
                self._sam_pending_concept = None
                self._start_sam_candidates_for_concept(pending_concept)
            pending_exemplar_concept = self._sam_pending_exemplar_concept
            if pending_exemplar_concept:
                self._sam_pending_exemplar_concept = None
                self._start_sam_candidates_from_exemplars(pending_exemplar_concept)

        def _on_error(err):
            current_uuid = self.moment.imaged_moment.uuid if self.moment else None
            if current_uuid != moment_uuid:
                return

            if self._is_cuda_oom_error(err):
                self._sam_failed_image_uuid = moment_uuid
                self._sam_last_error_message = (
                    "SAM embedding failed (GPU out of memory)"
                )
                logger.error(
                    "Embedding failed for image {} due to CUDA OOM; further retries are paused until image changes",
                    moment_uuid,
                )
            else:
                self._sam_failed_image_uuid = moment_uuid
                self._sam_last_error_message = "SAM embedding failed"
                logger.error("Embedding failed for image {}: {}", moment_uuid, err)

            self._notify_sam_status(self._build_sam_status())

        def _on_finished():
            self._sam_embedding_busy = False
            self._notify_sam_status(self._build_sam_status())
            current_uuid = self.moment.imaged_moment.uuid if self.moment else None
            if (
                self._sam_assist_enabled
                and current_uuid is not None
                and self._sam_ready_image_uuid != current_uuid
                and self._sam_failed_image_uuid != current_uuid
            ):
                self._maybe_start_sam_embedding()

        run_async(
            self,
            _embed,
            on_result=_on_result,
            on_error=_on_error,
            on_finished=_on_finished,
        )

    def _start_sam_candidates_for_concept(self, concept: str):
        if not self._sam_assist_enabled:
            self._notify_sam_status(self._build_sam_status())
            return
        if not getattr(self, "_sam_semantic_enabled", True):
            self._notify_sam_status(self._build_sam_status())
            return
        if self.moment is None:
            self._notify_sam_status(self._build_sam_status())
            return
        if not concept:
            self._notify_sam_status(self._build_sam_status())
            return

        moment_uuid = self.moment.imaged_moment.uuid
        if self._sam_ready_image_uuid != moment_uuid:
            if self._sam_failed_image_uuid == moment_uuid:
                self._notify_sam_status(self._build_sam_status())
                return
            self._notify_sam_status("SAM waiting for embedding to query concept...")
            self._sam_pending_concept = concept
            self._sam_pending_exemplar_concept = None
            self._maybe_start_sam_embedding()
            return

        self._sam_candidate_observation_uuid = None
        self._sam_candidate_concept = concept
        self._notify_sam_status("SAM querying concept '{}'...".format(concept))

        def _on_result(boxes):
            if self.moment is None:
                return
            current_uuid = self.moment.imaged_moment.uuid
            if current_uuid != moment_uuid:
                return
            if self._active_annotation_concept != concept:
                return

            candidates = self._make_candidate_boxes(boxes, None, concept)
            self._sam_candidate_boxes = candidates
            self._sam_candidate_index = 0
            self._notify_sam_candidate_state()
            self._notify_sam_status(
                "SAM ready: {} candidate(s), {}".format(
                    len(candidates),
                    self._point_capability_text(),
                )
            )
            self.redraw()

        def _on_error(err):
            logger.error("Concept query failed: {}", err)
            self._notify_sam_status("SAM concept query failed")

        run_async(
            self,
            self._sam_query_text,
            concept,
            on_result=_on_result,
            on_error=_on_error,
        )

    def _sam_query_boxes(self, boxes_xyxy):
        if self.sam3_service is None:
            return []
        return self.sam3_service.query_boxes(boxes_xyxy)

    def _exemplar_boxes_for_active_concept(self) -> List[SourceBoundingBox]:
        concept = self._active_annotation_concept
        if not concept or not self.observation_map:
            return []
        boxes: List[SourceBoundingBox] = []
        for item in self.observation_map.values():
            obs = item.observation
            if obs.concept != concept:
                continue
            boxes.extend(list(obs.boxes))
        return boxes

    def can_find_similar(self) -> bool:
        if not self._sam_assist_enabled or not getattr(
            self, "_sam_semantic_enabled", True
        ):
            return False
        if self.sam3_service is None or not self.sam3_service.available:
            return False
        if not self._active_annotation_concept:
            return False
        return bool(self._exemplar_boxes_for_active_concept())

    def find_similar_from_exemplars(self):
        self._start_sam_candidates_from_exemplars(self._active_annotation_concept)

    def _start_sam_candidates_from_exemplars(self, concept: Optional[str]):
        if not self._sam_assist_enabled:
            self._notify_sam_status(self._build_sam_status())
            return
        if not getattr(self, "_sam_semantic_enabled", True):
            self._notify_sam_status(self._build_sam_status())
            return
        if self.moment is None:
            self._notify_sam_status(self._build_sam_status())
            return
        if not concept:
            self._notify_sam_status(
                "SAM: no active annotation concept for Find Similar"
            )
            return

        exemplars = self._exemplar_boxes_for_active_concept()
        if not exemplars:
            self._notify_sam_status(
                "SAM: no existing boxes for '{}' to use as exemplars".format(concept)
            )
            return

        moment_uuid = self.moment.imaged_moment.uuid
        if self._sam_ready_image_uuid != moment_uuid:
            if self._sam_failed_image_uuid == moment_uuid:
                self._notify_sam_status(self._build_sam_status())
                return
            self._notify_sam_status(
                "SAM waiting for embedding to find similar to '{}'...".format(concept)
            )
            self._sam_pending_exemplar_concept = concept
            self._sam_pending_concept = None
            self._maybe_start_sam_embedding()
            return

        boxes_xyxy = [
            (box.x(), box.y(), box.x() + box.width(), box.y() + box.height())
            for box in exemplars
        ]

        self._sam_candidate_observation_uuid = None
        self._sam_candidate_concept = concept
        self._notify_sam_status(
            "SAM querying {} exemplar(s) for concept '{}'...".format(
                len(boxes_xyxy), concept
            )
        )

        def _on_result(boxes):
            if self.moment is None:
                return
            current_uuid = self.moment.imaged_moment.uuid
            if current_uuid != moment_uuid:
                return
            if self._active_annotation_concept != concept:
                return

            candidates = self._make_candidate_boxes(boxes, None, concept)
            self._sam_candidate_boxes = candidates
            self._sam_candidate_index = 0
            self._notify_sam_candidate_state()
            self._notify_sam_status(
                "SAM ready: {} candidate(s) from {} exemplar(s), {}".format(
                    len(candidates), len(boxes_xyxy), self._point_capability_text()
                )
            )
            self.redraw()

        def _on_error(err):
            logger.error("Exemplar query failed: {}", err)
            self._notify_sam_status("SAM exemplar query failed")

        run_async(
            self,
            self._sam_query_boxes,
            boxes_xyxy,
            on_result=_on_result,
            on_error=_on_error,
        )

    def _make_candidate_boxes(
        self,
        boxes,
        observation_uuid: Optional[str],
        concept: str,
        apply_overlap_filter: bool = True,
    ):
        candidates: List[SourceBoundingBox] = []
        for box in boxes or []:
            x, y, w, h = box
            box_json = {
                "x": int(x),
                "y": int(y),
                "width": int(w),
                "height": int(h),
                "image_reference_uuid": self.moment.imaged_moment.image_reference_uuid,
            }
            candidate = SourceBoundingBox(
                box_json,
                concept,
                observer=self.observer,
                observation_uuid=observation_uuid or "",
                part="self",
            )
            if candidate.width() * candidate.height() <= self._sam_min_area:
                continue
            if apply_overlap_filter and self._overlaps_existing(candidate):
                continue
            candidates.append(candidate)
        return candidates

    def _filter_point_prompt_boxes(self, boxes):
        if not boxes or self.pixmap_src is None:
            return boxes

        image_area = float(self.pixmap_src.width() * self.pixmap_src.height())
        if image_area <= 0:
            return boxes

        filtered = []
        for box in boxes:
            x, y, w, h = box
            if float(w * h) / image_area > 0.95:
                continue
            filtered.append(box)
        return filtered

    def _all_existing_boxes(self) -> List[SourceBoundingBox]:
        if not self.observation_map:
            return []
        boxes: List[SourceBoundingBox] = []
        for item in self.observation_map.values():
            obs = item.observation
            boxes.extend(list(obs.boxes))
            boxes.extend(list(obs.video_boxes))
        return boxes

    def _iou(self, a: SourceBoundingBox, b: SourceBoundingBox) -> float:
        ax1 = a.x()
        ay1 = a.y()
        ax2 = ax1 + a.width()
        ay2 = ay1 + a.height()

        bx1 = b.x()
        by1 = b.y()
        bx2 = bx1 + b.width()
        by2 = by1 + b.height()

        ix1 = max(ax1, bx1)
        iy1 = max(ay1, by1)
        ix2 = min(ax2, bx2)
        iy2 = min(ay2, by2)

        iw = max(0, ix2 - ix1)
        ih = max(0, iy2 - iy1)
        inter = iw * ih
        if inter <= 0:
            return 0.0

        union = a.width() * a.height() + b.width() * b.height() - inter
        if union <= 0:
            return 0.0
        return float(inter) / float(union)

    def _overlaps_existing(self, candidate: SourceBoundingBox) -> bool:
        for existing in self._all_existing_boxes():
            if self._iou(candidate, existing) >= self._sam_overlap_iou:
                return True
        return False

    def _maybe_update_hover_candidate(self, event: QMouseEvent):
        if not self._sam_assist_enabled:
            return
        if not getattr(self, "_sam_point_enabled", True):
            return
        if self.pixmap_src is None or self.moment is None:
            return
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Ctrl is reserved for drawing a new box; hide any SAM suggestion while held.
            if self._sam_hover_box is not None:
                self._sam_hover_box = None
                self._update_mouse_overlay()
            return
        if event.buttons() & Qt.MouseButton.LeftButton:
            return
        if self.resize_type:
            return

        moment_uuid = self.moment.imaged_moment.uuid
        if self._sam_ready_image_uuid != moment_uuid:
            return

        pt = self.get_im_rel_point(event.pos()).toPoint()
        if pt.x() < 0 or pt.y() < 0:
            return
        if self.pixmap_src and (
            pt.x() > self.pixmap_src.width() or pt.y() > self.pixmap_src.height()
        ):
            return

        if self._sam_last_hover_point is not None:
            dx = abs(pt.x() - self._sam_last_hover_point.x())
            dy = abs(pt.y() - self._sam_last_hover_point.y())
            if dx < 6 and dy < 6:
                return

        if self._sam_hover_inflight:
            return

        self._sam_last_hover_point = pt
        self._sam_hover_inflight = True
        self._notify_sam_status("SAM point prompt query...")

        def _on_result(boxes):
            if not self._sam_assist_enabled:
                return
            if not self._mouse_in_view:
                self._sam_hover_box = None
                self.redraw()
                return

            self._sam_hover_box = None
            boxes = self._filter_point_prompt_boxes(boxes)
            if not boxes:
                self.redraw()
                return

            observation_uuid = self.observation_uuid
            concept = self._active_annotation_concept or ""
            if (
                observation_uuid is not None
                and self.observation_map
                and observation_uuid in self.observation_map
            ):
                concept = self.observation_map[observation_uuid].observation.concept

            candidates = self._make_candidate_boxes(
                boxes,
                observation_uuid,
                concept,
                apply_overlap_filter=False,
            )
            if candidates:
                self._sam_hover_box = candidates[0]
            if self.sam3_service is not None and self.sam3_service.available:
                self._notify_sam_status(
                    "SAM ready: {}, {}".format(
                        self._semantic_capability_text(), self._point_capability_text()
                    )
                )
            self.redraw()

        def _on_error(err):
            self._notify_sam_status("SAM point prompt query failed")

        def _on_finished():
            self._sam_hover_inflight = False
            if self.sam3_service is not None and self.sam3_service.available:
                self._notify_sam_status(
                    "SAM ready: {}, {}".format(
                        self._semantic_capability_text(), self._point_capability_text()
                    )
                )

        run_async(
            self,
            self._sam_query_point,
            int(pt.x()),
            int(pt.y()),
            on_result=_on_result,
            on_error=_on_error,
            on_finished=_on_finished,
        )

    # --- Rendering ---------------------------------------------------------

    def set_entry(self, entry: EntryTreeItem):
        """Set the selected tree entry and load associated data.

        Args:
            entry: Entry tree item to load from.
        """
        if entry.is_imaged_moment:
            entry.setExpanded(True)
            if entry != self.moment:
                self.load_moment(entry)
            self.set_annotation_focus(
                concept_filter=self._active_annotation_concept,
                observation_uuid=None,
            )
        elif entry.is_observation:
            if entry.parent() != self.moment:
                self.load_moment(entry.parent())
            self.set_annotation_focus(
                concept_filter=self._active_annotation_concept,
                observation_uuid=entry.observation.uuid,
            )

    def load_moment(self, entry: EntryTreeItem, preserve_sam_state: bool = False):
        """Load data for an imaged moment entry.

        Args:
            entry: Entry tree item of an imaged moment.
            preserve_sam_state: Preserve SAM embedding/candidates for same-image refreshes.
        """
        current_uuid = (
            self.moment.imaged_moment.uuid if self.moment is not None else None
        )
        next_uuid = entry.imaged_moment.uuid
        preserve_same_image = bool(preserve_sam_state and current_uuid == next_uuid)

        self.moment = entry
        if not preserve_same_image:
            self._clear_sam_state(reset_embedding=True)
        else:
            self._sam_hover_box = None
            self._sam_hover_inflight = False
            self._sam_last_hover_point = None

        moment: ImagedMomentEntry = entry.imaged_moment
        if moment.cached_image is not None:
            self._image_loading = False
            self._image_loading_uuid = None
            self._image_loading_error = None
            self.set_pixmap(moment.cached_image)
            self._maybe_start_sam_embedding()
            self._notify_sam_status(self._build_sam_status())
        elif moment.image_url:
            self._image_loading = True
            self._image_loading_uuid = moment.uuid
            self._image_loading_error = None
            self.set_pixmap(None)

            request_uuid = moment.uuid

            def _on_result(pixmap):
                current_moment = self.moment.imaged_moment if self.moment else None
                if current_moment is None or current_moment.uuid != request_uuid:
                    return

                current_moment.cached_image = pixmap
                self._image_loading = False
                self._image_loading_uuid = None
                if pixmap is None:
                    self._image_loading_error = "Could not load image."
                else:
                    self._image_loading_error = None
                self.set_pixmap(pixmap)
                self._maybe_start_sam_embedding()
                self._notify_sam_status(self._build_sam_status())
                self.redraw()

            def _on_error(_):
                current_moment = self.moment.imaged_moment if self.moment else None
                if current_moment is None or current_moment.uuid != request_uuid:
                    return

                self._image_loading = False
                self._image_loading_uuid = None
                self._image_loading_error = "Could not load image."
                self.set_pixmap(None)
                self._notify_sam_status("SAM waiting: image load failed")
                self.redraw()

            run_async(
                self,
                self._m3_fetch_image,
                moment.image_url,
                on_result=lambda image_bytes: _on_result(
                    self._bytes_to_pixmap(image_bytes)
                ),
                on_error=_on_error,
            )
        else:
            self._image_loading = False
            self._image_loading_uuid = None
            self._image_loading_error = "No image URL."
            self.set_pixmap(None)
            self._notify_sam_status("SAM waiting: no image URL")
        observation_entries = [entry.child(idx) for idx in range(entry.childCount())]
        self.observation_map = dict(
            [
                (
                    cast(EntryTreeItem, child).observation.uuid,
                    cast(EntryTreeItem, child),
                )
                for child in observation_entries
                if isinstance(child, EntryTreeItem) and child.is_observation
            ]
        )  # observation uuid -> entry tree item
        self.enabled_observations = dict()
        for observation_entry in self.observation_map.values():
            observation = observation_entry.observation
            self._hydrate_observation_boxes(observation)
            self.enabled_observations[observation.uuid] = True

        selected_observation_uuid = None
        if self.observation_uuid and self.observation_uuid in self.observation_map:
            selected_observation_uuid = self.observation_uuid
        self.set_annotation_focus(
            concept_filter=self._active_annotation_concept,
            observation_uuid=selected_observation_uuid,
        )

        if (
            self._sam_assist_enabled
            and getattr(self, "_sam_semantic_enabled", True)
            and self._active_annotation_concept
            and not preserve_same_image
        ):
            self._start_sam_candidates_for_concept(self._active_annotation_concept)

        self._ensure_video_data_loaded(moment)

    def set_pixmap(self, pixmap: Optional[QPixmap]):
        """Set the source pixmap, resize the scene to it, and fit the view.

        Reloading the *same* image (e.g. after a box edit triggers a data
        refresh) intentionally does not reset the user's current zoom/pan --
        only a genuinely different image does.

        Args:
            pixmap: Source pixmap to display, in full resolution.
        """
        previous_key = (
            self.pixmap_src.cacheKey()
            if self.pixmap_src is not None and not self.pixmap_src.isNull()
            else None
        )
        new_key = (
            pixmap.cacheKey() if pixmap is not None and not pixmap.isNull() else None
        )
        same_image = (
            previous_key is not None and new_key is not None and previous_key == new_key
        )

        self.pixmap_src = pixmap
        self.pt_1 = None
        self.pt_2 = None

        if pixmap is None or pixmap.isNull():
            if self.pixmap_item is not None:
                self.scene().removeItem(self.pixmap_item)
                self.pixmap_item = None
            self.scene().setSceneRect(0, 0, max(1, self.width()), max(1, self.height()))
            if self._minimap is not None:
                self._minimap.set_pixmap(None)
            return

        if self.pixmap_item is None:
            self.pixmap_item = self.scene().addPixmap(pixmap)
            self.pixmap_item.setZValue(-100)
        else:
            self.pixmap_item.setPixmap(pixmap)
        self.pixmap_item.setPos(0, 0)
        self.scene().setSceneRect(0, 0, pixmap.width(), pixmap.height())

        if not same_image:
            self._user_has_zoomed = False
            self._fit_to_view()
        if self._minimap is not None:
            self._minimap.set_pixmap(pixmap)
            self._minimap.reposition()
        self._sync_minimap()

    def _fit_to_view(self):
        if self.pixmap_item is None:
            return
        self.fitInView(self.pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

    def _fit_scale(self) -> float:
        """Scale at which the image exactly fills the viewport (KeepAspectRatio)."""
        if self.pixmap_item is None:
            return 1.0
        img_rect = self.pixmap_item.boundingRect()
        viewport_size = self.viewport().size()
        if img_rect.width() <= 0 or img_rect.height() <= 0:
            return 1.0
        return min(
            viewport_size.width() / img_rect.width(),
            viewport_size.height() / img_rect.height(),
        )

    def _sync_minimap(self):
        """Refresh the minimap indicator and force-repaint viewport-corner overlays.

        Qt's internal scroll optimization blits the viewport's existing pixels
        during a pan/zoom for performance, which can leave child widgets
        layered on top of the viewport (the minimap, status/ancillary labels)
        showing stale pixels until something explicitly repaints them.
        """
        if self._minimap is not None:
            self._minimap.update_visibility()
            self._minimap.viewport().update()
            self._minimap.update()
        if self._status_label is not None:
            self._status_label.update()
        if self._ancillary_label is not None:
            self._ancillary_label.update()

    def preview_focus_on_sam_candidate(self):
        """Temporarily center/zoom on the current SAM candidate for context.

        Meant to be called while the mouse hovers the accept/reject buttons
        (and again after accepting/rejecting, to snap to the next candidate
        while still hovering); pair with `clear_focus_preview()` to restore
        the prior view once the mouse actually leaves the buttons.
        """
        candidate = self._current_sam_candidate
        if candidate is None or self.pixmap_item is None:
            return
        if self._focus_preview_saved is None:
            # Only remember the true pre-preview state once, so repeated calls
            # while still hovering (e.g. after accept/reject) don't clobber it
            # with an already-zoomed-in state.
            self._focus_preview_saved = (
                QPointF(self.transform().m11(), self.transform().m22()),
                self.horizontalScrollBar().value(),
                self.verticalScrollBar().value(),
                self._user_has_zoomed,
            )
        rect = QRectF(
            candidate.x(), candidate.y(), candidate.width(), candidate.height()
        )
        self._focus_on_rect(rect, fraction=0.30)

    def clear_focus_preview(self):
        """Restore the view state saved by `preview_focus_on_sam_candidate()`."""
        if self._focus_preview_saved is None:
            return
        scale_point, h_value, v_value, had_zoomed = self._focus_preview_saved
        self._focus_preview_saved = None
        self.resetTransform()
        self.scale(scale_point.x(), scale_point.y())
        self.horizontalScrollBar().setValue(h_value)
        self.verticalScrollBar().setValue(v_value)
        self._user_has_zoomed = had_zoomed
        self._sync_minimap()

    def _focus_on_rect(self, rect: QRectF, fraction: float):
        if rect.width() <= 0 or rect.height() <= 0:
            return
        viewport_size = self.viewport().size()
        if rect.width() >= rect.height():
            scale = (fraction * viewport_size.width()) / rect.width()
        else:
            scale = (fraction * viewport_size.height()) / rect.height()
        # Never zoom out past "image fills the view", same floor as wheelEvent.
        min_scale = max(self.MIN_SCALE, self._fit_scale())
        scale = max(min_scale, min(self.MAX_SCALE, scale))
        self.resetTransform()
        self.scale(scale, scale)
        self.centerOn(rect.center())
        self._user_has_zoomed = True
        self._sync_minimap()

    def _position_overlays(self):
        margin = 10
        viewport_size = self.viewport().size()
        if self._ancillary_label is not None:
            self._ancillary_label.move(
                margin, viewport_size.height() - self._ancillary_label.height() - margin
            )
        if self._status_label is not None:
            self._status_label.adjustSize()
            self._status_label.move(
                (viewport_size.width() - self._status_label.width()) // 2,
                (viewport_size.height() - self._status_label.height()) // 2,
            )
        if self._minimap is not None:
            self._minimap.reposition()

    def _show_status_message(self):
        if self._image_loading:
            msg = "Loading image..."
        elif self._image_loading_error:
            msg = self._image_loading_error
        else:
            msg = "No image loaded."
        self._status_label.setText(msg)
        self._position_overlays()
        self._status_label.show()
        self._ancillary_label.hide()
        self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        self._current_cursor_shape = Qt.CursorShape.ArrowCursor

    def _hide_status_message(self):
        self._status_label.hide()

    def draw_ancillary_data(self):
        """Update the ancillary metadata overlay text for the current image."""
        if self.moment is None:
            self._ancillary_label.hide()
            return

        moment = self.moment.imaged_moment
        text_dict = {}

        if moment.ancillary_data:
            ancillary_data = moment.ancillary_data

            if "depth_meters" in ancillary_data:
                text_dict["Depth (m): {:<10.2f}"] = ancillary_data["depth_meters"]

            if "latitude" in ancillary_data:
                text_dict["Latitude: {:<10.3f}"] = ancillary_data["latitude"]

            if "longitude" in ancillary_data:
                text_dict["Longitude: {:<10.3f}"] = ancillary_data["longitude"]

        if moment.recorded_timestamp:
            text_dict["Recorded: {:<20}"] = moment.recorded_timestamp.replace(
                "T", " "
            ).replace("Z", "")

        if moment.video_data and "uri" in moment.video_data:
            uri = moment.video_data["uri"]
            if uri.startswith("urn:"):
                video_sequence_name = uri.split(":")[-1]
                text_dict["Video: {:<10}"] = video_sequence_name

        text_str = " ".join(k.format(v) for k, v in text_dict.items())
        if not text_str:
            self._ancillary_label.hide()
            return
        self._ancillary_label.setText(text_str)
        self._ancillary_label.adjustSize()
        self._position_overlays()
        self._ancillary_label.show()

    @staticmethod
    def _cosmetic_pen(color: str, width: int, style=Qt.PenStyle.SolidLine) -> QPen:
        pen = QPen(QColor(PALETTE[color]), width, style)
        pen.setCosmetic(True)
        return pen

    def _ensure_overlay_items(self):
        if self._drag_rect_item is None:
            self._drag_rect_item = self.scene().addRect(
                QRectF(), self._cosmetic_pen("accent_alt", 1)
            )
            self._drag_rect_item.setZValue(150)
            self._drag_rect_item.setVisible(False)
        if self._sam_candidate_item is None:
            self._sam_candidate_item = self.scene().addRect(
                QRectF(), self._cosmetic_pen("success", 2, Qt.PenStyle.DashLine)
            )
            self._sam_candidate_item.setZValue(200)
            self._sam_candidate_item.setVisible(False)
        if self._sam_hover_item is None:
            self._sam_hover_item = self.scene().addRect(
                QRectF(), self._cosmetic_pen("warning", 2, Qt.PenStyle.DashLine)
            )
            self._sam_hover_item.setZValue(200)
            self._sam_hover_item.setVisible(False)
        if self._crosshair_h_item is None:
            self._crosshair_h_item = self.scene().addLine(
                QLineF(), self._cosmetic_pen("crosshairs", 1)
            )
            self._crosshair_h_item.setZValue(250)
            self._crosshair_h_item.setVisible(False)
        if self._crosshair_v_item is None:
            self._crosshair_v_item = self.scene().addLine(
                QLineF(), self._cosmetic_pen("crosshairs", 1)
            )
            self._crosshair_v_item.setZValue(250)
            self._crosshair_v_item.setVisible(False)

    def _update_crosshair(self, scene_pos: Optional[QPointF]):
        """Show red crosshairs through the cursor while Ctrl (draw-box mode) is held."""
        if not self._has_scene() or self.pixmap_src is None:
            return
        self._ensure_overlay_items()
        if scene_pos is None:
            self._crosshair_h_item.setVisible(False)
            self._crosshair_v_item.setVisible(False)
            return
        scene_rect = self.scene().sceneRect()
        self._crosshair_h_item.setLine(
            QLineF(scene_rect.left(), scene_pos.y(), scene_rect.right(), scene_pos.y())
        )
        self._crosshair_v_item.setLine(
            QLineF(scene_pos.x(), scene_rect.top(), scene_pos.x(), scene_rect.bottom())
        )
        self._crosshair_h_item.setVisible(True)
        self._crosshair_v_item.setVisible(True)

    def _update_drag_rect_overlay(self):
        if not self._has_scene():
            return
        self._ensure_overlay_items()
        rect = self.calc_drag_rect()
        if rect is None:
            self._drag_rect_item.setVisible(False)
            return
        self._drag_rect_item.setRect(rect)
        self._drag_rect_item.setVisible(True)

    def _clear_drag_rect_overlay(self):
        if self._drag_rect_item is not None:
            self._drag_rect_item.setVisible(False)

    def _update_mouse_overlay(self):
        """Reposition SAM candidate/hover overlay rects without a full rebuild."""
        if self.pixmap_src is None or self.pixmap_item is None:
            return
        self._ensure_overlay_items()

        candidate = self._current_sam_candidate
        if candidate is not None:
            self._sam_candidate_item.setRect(
                QRectF(
                    candidate.x(), candidate.y(), candidate.width(), candidate.height()
                )
            )
            self._sam_candidate_item.setVisible(True)
        else:
            self._sam_candidate_item.setVisible(False)

        if self._mouse_in_view and self._sam_hover_box is not None:
            box = self._sam_hover_box
            self._sam_hover_item.setRect(
                QRectF(box.x(), box.y(), box.width(), box.height())
            )
            self._sam_hover_item.setVisible(True)
        else:
            self._sam_hover_item.setVisible(False)

    def _clear_box_items(self):
        for item in self._box_items:
            if item.scene() is not None:
                self.scene().removeItem(item)
        self._box_items = []

    def _add_box_item(
        self, box: SourceBoundingBox, bounds: QRectF, editable: bool
    ) -> BoundingBoxItem:
        box_item = BoundingBoxItem(box, editable=editable)
        box_item.set_image_bounds(bounds)
        box_item.set_highlighted(self._box_is_highlighted(box))
        if editable:
            box_item.geometryCommitted.connect(self._on_box_geometry_committed)
            box_item.contextMenuRequested.connect(self._on_box_context_menu_requested)
            box_item.resizeStarted.connect(self._on_box_resize_started)
            box_item.resizeFinished.connect(self._on_box_resize_finished)
        self.scene().addItem(box_item)
        self._box_items.append(box_item)
        return box_item

    def _rebuild_box_items(self):
        self._clear_box_items()
        if (
            not self.enabled_observations
            or not self.observation_map
            or self.pixmap_src is None
        ):
            return
        bounds = QRectF(0, 0, self.pixmap_src.width(), self.pixmap_src.height())
        for uuid, enabled in self.enabled_observations.items():
            if not enabled:
                continue
            observation = self.observation_map[uuid].observation
            for box in observation.boxes:
                self._add_box_item(box, bounds, editable=True)
            for video_box in observation.video_boxes:
                self._add_box_item(video_box, bounds, editable=False)

    def redraw(self):
        """Sync scene items and overlays with the current state."""
        if self.pixmap_src is None or self.pixmap_item is None:
            self._clear_box_items()
            self._show_status_message()
            self._update_mouse_overlay()
            return

        self._hide_status_message()
        self.draw_ancillary_data()
        self._rebuild_box_items()
        self._update_mouse_overlay()
        self._update_drag_rect_overlay()
        self._sync_minimap()

    def select_observation(self, observation_uuid: str):
        """Set the active observation used for highlight/edit focus.

        Args:
            observation_uuid: Observation UUID to focus, or "all"/None to clear focus.
        """
        if observation_uuid and observation_uuid != "all":
            self.observation_uuid = observation_uuid
            self.selected_box = None
        else:
            self.observation_uuid = None
            self.selected_box = None
        self._clear_scene_selection()
        self._refresh_highlighting()
        if self.observation_uuid is None:
            self._sam_candidate_boxes = []
            self._sam_hover_box = None
            self._notify_sam_candidate_state()

    def focus_association_box(
        self, observation_uuid: str, association_uuid: str
    ) -> None:
        if not self.observation_map:
            raise LookupError("No observations are loaded for the current image.")

        observation_entry = self.observation_map.get(observation_uuid)
        if observation_entry is None:
            raise LookupError(
                "Could not find the selected observation in the current image."
            )

        self.select_observation(observation_uuid)
        observation = observation_entry.observation
        all_boxes = list(observation.boxes) + list(observation.video_boxes)

        for box in all_boxes:
            if box.association_uuid == association_uuid:
                self.selected_box = box
                box_item = self._find_box_item(box)
                if box_item is not None:
                    self._suppress_selection_signal = True
                    try:
                        self._clear_scene_selection()
                        box_item.setSelected(True)
                    finally:
                        self._suppress_selection_signal = False
                self._refresh_highlighting()
                self.redraw()
                return

        raise LookupError("Could not find the selected association box.")

    def get_im_rel_point(self, pt) -> QPointF:
        """Convert a viewport-relative point to full-resolution image coordinates.

        Args:
            pt: Viewport-relative point (QPoint or QPointF).

        Returns:
            QPointF: Point in image-pixel space.
        """
        point = pt.toPoint() if hasattr(pt, "toPoint") else pt
        return self.mapToScene(point)

    def get_scene_rel_point(self, pt: QPointF) -> QPoint:
        """Convert an image-relative point to viewport coordinates.

        Args:
            pt: Image-relative point.

        Returns:
            QPoint: Point relative to the viewport.
        """
        return self.mapFromScene(pt)

    def show_box_properties_dialog(self, box_item: BoundingBoxItem):
        """Open the properties dialog for a selected box.

        Args:
            box_item: Graphical bounding box item to edit.
        """
        box = box_item.source
        self.selected_box = box
        self._suppress_selection_signal = True
        try:
            self._clear_scene_selection()
            box_item.setSelected(True)
        finally:
            self._suppress_selection_signal = False
        self._refresh_highlighting()

        box_json_before = box.get_json()
        part_before = box.part or "self"

        dialog = PropertiesDialog(box, parent=self)
        dialog.setup_form(
            self.pixmap_src,
            self.redraw,
            part_options=self._m3_get_all_parts(),
        )
        dialog.set_delete_callback(self.delete_box)

        dialog.setModal(True)
        dialog.adjustSize()
        center_window(dialog, self.window())
        dialog.exec()

        box_json_after = box.get_json()
        part_after = box.part or "self"
        if box_json_after != box_json_before or part_after != part_before:
            box.observer = self.observer  # Update observer field
            try:
                self._m3_modify_box(
                    box_json_after,
                    box.observation_uuid,
                    box.association_uuid,
                    to_concept=part_after,
                )
            except ServiceError as exc:
                QMessageBox.warning(
                    self,
                    "Update failed",
                    "Could not update bounding box.\n\n{}".format(exc),
                )
            else:
                self.reload_moment()

        self.pt_1 = None
        self.pt_2 = None

        self.selected_box = None
        self._clear_scene_selection()
        self.redraw()

    def _on_box_geometry_committed(self, box_item: BoundingBoxItem):
        box = box_item.source
        try:
            self._m3_modify_box(
                box.get_json(),
                box.observation_uuid,
                box.association_uuid,
                to_concept=box.part or "self",
            )
        except ServiceError as exc:
            QMessageBox.warning(
                self,
                "Update failed",
                "Could not persist box change.\n\n{}".format(exc),
            )
        else:
            self.reload_moment()

    def _on_box_resize_started(self):
        self.resize_type = True

    def _on_box_resize_finished(self):
        self.resize_type = False

    def _on_box_context_menu_requested(
        self, box_item: BoundingBoxItem, scene_pos: QPointF
    ):
        menu = QMenu(self)
        edit_action = menu.addAction("Edit Properties...")
        select_action = menu.addAction("Select Observation")
        menu.addSeparator()
        delete_action = menu.addAction("Delete Box")

        global_pos = self.mapToGlobal(self.mapFromScene(scene_pos))
        chosen = menu.exec(global_pos)
        if chosen is edit_action:
            self.show_box_properties_dialog(box_item)
        elif chosen is select_action:
            entry = (
                self.observation_map.get(box_item.source.observation_uuid)
                if self.observation_map
                else None
            )
            if entry is not None and self._observation_select_callback is not None:
                self._observation_select_callback(entry)
        elif chosen is delete_action:
            choice = QMessageBox.question(
                self,
                "Delete Box?",
                "Delete this bounding box?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if choice == QMessageBox.StandardButton.Yes:
                try:
                    self.delete_box(box_item.source)
                except Exception as exc:
                    QMessageBox.warning(self, "Delete failed", str(exc))

    def delete_box(self, box: SourceBoundingBox):
        """Delete a box from the observation and persist deletion.

        Args:
            box: Source bounding box to delete.
        """
        if not self.observation_map or box.observation_uuid not in self.observation_map:
            raise RuntimeError("Could not resolve the target observation for this box.")

        observation = self.observation_map[box.observation_uuid].observation
        is_last_box = self._count_bounding_box_associations(observation) <= 1

        try:
            self._m3_delete_box(box.association_uuid)  # Call deletion request
        except ServiceError as exc:
            QMessageBox.warning(
                self,
                "Delete failed",
                "Could not delete bounding box.\n\n{}".format(exc),
            )
            return

        if box in observation.boxes:
            observation.boxes.remove(box)
        if box in observation.video_boxes:
            observation.video_boxes.remove(box)
        if getattr(observation, "associations", None):
            observation.associations = [
                assoc
                for assoc in observation.associations
                if getattr(assoc, "uuid", "") != box.association_uuid
            ]

        if is_last_box and self._is_observation_owned(observation.uuid):
            choice = QMessageBox.question(
                self,
                "Delete Observation?",
                "This was the last bounding box for this observation. Delete the observation as well?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if choice == QMessageBox.StandardButton.Yes:
                try:
                    self._m3_delete_observation(observation.uuid)
                except ServiceError as exc:
                    QMessageBox.warning(
                        self,
                        "Delete failed",
                        "The bounding box was deleted, but deleting the observation failed.\n\n{}".format(
                            exc
                        ),
                    )

        self.reload_moment()

    def calc_drag_rect(self):
        """Compute the drag-selection rectangle.

        Returns:
            QRectF | None: Rectangle when both drag points exist, else None.
        """
        if self.pt_1 and self.pt_2:
            x = self.pt_1.x()
            y = self.pt_1.y()
            w = self.pt_2.x() - x
            h = self.pt_2.y() - y

            if w < 0:
                w = -w
                x = self.pt_2.x()
            if h < 0:
                h = -h
                y = self.pt_2.y()

            return QRectF(x, y, w, h)
        return None

    def calc_crop_rect(self, drag_rect: QRectF):
        """Clamp a drag rectangle to image bounds.

        Args:
            drag_rect: Drag rectangle.

        Returns:
            QRectF: Cropped rectangle.
        """
        x = drag_rect.x()
        y = drag_rect.y()
        w = drag_rect.width()
        h = drag_rect.height()
        if x < 0:
            w += x
            x = 0
        if y < 0:
            h += y
            y = 0
        if x + w > self.pixmap_src.width():
            w = self.pixmap_src.width() - x
        if y + h > self.pixmap_src.height():
            h = self.pixmap_src.height() - y

        return QRectF(x, y, w, h)

    def prompt_concept(self):
        """Prompt for concept selection.

        Returns:
            str: Selected concept, or an empty string when canceled.
        """
        dialog = QDialog(self)
        dialog.setLayout(QVBoxLayout())
        dialog.setWindowTitle("Specify a concept")
        dialog.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        search = ConceptSearchbar()

        # Reuse loaded concept names from shared app state.
        search.set_concepts(self._get_prompt_concepts())

        submit_button = QPushButton("Submit")
        submit_button.setEnabled(False)
        submit_button.pressed.connect(dialog.accept)

        concepts = search.get_concepts()
        concept_selected = ""

        def _find_match(text: str) -> str:
            """Return the correctly-cased concept for *text*, or empty string."""
            t = text.strip().lower()
            return next((c for c in concepts if c.lower() == t), "")

        def on_activated(concept: str):
            nonlocal concept_selected
            concept_selected = str(concept or "").strip()
            submit_button.setEnabled(bool(concept_selected))

        def on_return_pressed():
            nonlocal concept_selected
            matched = _find_match(search.text())
            if matched:
                concept_selected = matched
                dialog.accept()

        search.textChanged.connect(lambda _: submit_button.setEnabled(False))
        search.set_callback(on_activated)
        search.returnPressed.connect(on_return_pressed)
        search.setFocus()

        dialog.layout().addWidget(search)
        dialog.layout().addWidget(submit_button)

        dialog.setModal(True)
        dialog.adjustSize()
        center_window(dialog, self.window())
        accepted = dialog.exec()
        # Restore mouse-in-view state: the enter event from the dialog closing
        # may not be delivered until the next event loop iteration, so the
        # crosshair redraw that follows would otherwise run with a stale False.
        self._mouse_in_view = True
        if accepted != QDialog.DialogCode.Accepted or not concept_selected:
            return ""

        # Resolve synonym / common name → primary concept name.
        try:
            concept_selected = self._require_m3_service().get_concept_name(
                concept_selected
            )
        except Exception:
            pass
        return concept_selected

    def _get_prompt_concepts(self):
        """Return concept suggestions for prompt_concept."""
        try:
            root_any = cast(Any, self.window())
            search_panel = root_any.search_panel
            concepts = list(search_panel._state.concepts or [])
            if concepts:
                return concepts
            if search_panel.search_mode == "concept":
                return search_panel.search_bar.get_concepts()
        except Exception:
            pass
        return []

    def make_new_observation(self, concept):
        """Create a new observation for the current imaged moment.

        Args:
            concept: Concept to observe.

        Returns:
            dict | None: Observation response JSON, if creation succeeds.
        """
        kwargs = dict()
        moment = self.moment.imaged_moment
        if moment.timecode:
            kwargs["timecode"] = moment.timecode
        if moment.elapsed_time_millis is not None:
            kwargs["elapsed_time_millis"] = moment.elapsed_time_millis
        if moment.recorded_timestamp:
            kwargs["recorded_timestamp"] = moment.recorded_timestamp

        try:
            observation = (
                self._m3_create_observation(  # Call observation creation request
                    moment.video_reference_uuid,
                    concept,
                    self.observer,
                    **kwargs,
                )
            )
        except ServiceError as exc:
            raise RuntimeError(
                "Could not create observation.\n\n{}".format(exc)
            ) from exc

        if not observation:
            raise RuntimeError("Observation creation returned an empty payload.")

        observation_uuid = observation.get("observation_uuid") or observation.get(
            "uuid"
        )
        if not observation_uuid:
            raise RuntimeError("Observation creation response missing UUID field.")

        observation["observation_uuid"] = str(observation_uuid)
        self.moment.treeWidget().editable_uuids.add(observation["observation_uuid"])
        return observation

    def reload_moment(self, preserve_sam_state: bool = False):
        """Fully reload the current imaged moment entry."""
        target_entry = self.moment
        image = target_entry.imaged_moment.cached_image

        def _on_done():
            # Guard: ignore if the user navigated away before the reload finished.
            if self.moment is not target_entry:
                return
            if image is not None:
                target_entry.imaged_moment.cached_image = image
            self.load_moment(
                target_entry,
                preserve_sam_state=preserve_sam_state,
            )

        target_entry.treeWidget().load_imaged_moment_entry_async(
            target_entry,
            on_error=lambda err: QMessageBox.warning(
                self,
                "Refresh failed",
                "Could not reload imaged moment.\n\n{}".format(err),
            ),
            on_finished=_on_done,
        )

    def handle_new_box(
        self,
        box: SourceBoundingBox,
        refresh: bool = True,
        preserve_sam_state: bool = False,
    ) -> None:
        """Create a new box, creating an observation if needed.

        Args:
            box: Source bounding box.
        """
        uuid = self.observation_uuid
        created_new_observation = False
        if not uuid:  # Imaged moment selected
            new_concept = self._active_annotation_concept or self.prompt_concept()
            if not new_concept:  # No concept was specified
                raise ValueError("Concept is required to create a new observation.")
            observation = self.make_new_observation(new_concept)
            if not observation or "observation_uuid" not in observation:
                raise RuntimeError(
                    "Could not create an observation for the selected concept."
                )
            box.set_label(new_concept)
            uuid = observation["observation_uuid"]
            created_new_observation = True

        box.observation_uuid = uuid

        observation = None
        if self.observation_map and uuid in self.observation_map:
            observation = self.observation_map[uuid].observation
        elif not created_new_observation:
            raise RuntimeError("Could not resolve the target observation for this box.")

        if (
            observation is not None
            and self._count_bounding_box_associations(observation) > 0
        ):
            raise ValueError(
                "This observation already has a bounding box association. "
                "Delete or update the existing box instead of creating another."
            )

        response_json = self._m3_create_box(box.get_json(), uuid, to_concept=box.part)
        if not response_json or "uuid" not in response_json:
            raise RuntimeError(
                "Server rejected this box. Please try again or adjust box bounds."
            )

        box.association_uuid = response_json["uuid"]
        if refresh:
            self.reload_moment(preserve_sam_state=preserve_sam_state)

    # --- Mouse / keyboard / view events -------------------------------------

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self.pixmap_src is None or self.pixmap_item is None:
            super().wheelEvent(event)
            return
        delta = event.angleDelta().y()
        if delta == 0:
            super().wheelEvent(event)
            return
        factor = self.ZOOM_STEP if delta > 0 else 1.0 / self.ZOOM_STEP
        current_scale = self.transform().m11()
        # Never allow zooming out past "image fills the view".
        min_scale = max(self.MIN_SCALE, self._fit_scale())
        target_scale = max(min_scale, min(self.MAX_SCALE, current_scale * factor))
        applied_factor = target_scale / current_scale if current_scale else 1.0
        if abs(applied_factor - 1.0) > 1e-6:
            # Anchor manually on the wheel event's own position so the point
            # under the cursor stays fixed, instead of relying on Qt's
            # AnchorUnderMouse (which re-queries the OS cursor position and
            # can end up zooming around the wrong spot).
            anchor_viewport_pos = event.position().toPoint()
            anchor_scene_pos = self.mapToScene(anchor_viewport_pos)
            self.scale(applied_factor, applied_factor)
            shifted_viewport_pos = self.mapFromScene(anchor_scene_pos)
            drift = shifted_viewport_pos - anchor_viewport_pos
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() + drift.x()
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() + drift.y()
            )
        self._user_has_zoomed = target_scale > min_scale * 1.001
        self._sync_minimap()
        event.accept()

    def _resolve_box_item(self, item) -> Optional[BoundingBoxItem]:
        if isinstance(item, BoundingBoxItem):
            return item
        if item is not None and isinstance(item.parentItem(), BoundingBoxItem):
            return item.parentItem()
        return None

    def _is_resize_handle_at(self, viewport_pos: QPoint) -> bool:
        box_item = self._resolve_box_item(self.itemAt(viewport_pos))
        if box_item is None:
            return False
        return box_item.edge_at_scene_point(self.mapToScene(viewport_pos)) is not None

    def _accept_sam_hover_box(self, candidate: SourceBoundingBox):
        try:
            self.handle_new_box(candidate, preserve_sam_state=True)
        except Exception as exc:
            QMessageBox.warning(self, "Box creation failed", str(exc))
        self.redraw()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if (
            event.button() == Qt.MouseButton.RightButton
            and self._sam_assist_enabled
            and self._sam_hover_box is not None
        ):
            candidate = self._sam_hover_box
            self._sam_hover_box = None
            event.accept()
            # Defer: handle_new_box() may open a modal "Specify a concept"
            # dialog (prompt_concept()) when no concept/observation is active
            # (e.g. "All concepts" selected). Opening a modal dialog
            # synchronously from inside mousePressEvent -- while this mouse
            # button is still logically down -- can leave the view's mouse
            # grab in a broken state on some platforms (observed on macOS,
            # not reproducible on Linux), so the canvas stops receiving any
            # further mouse events afterward. Running it on the next
            # event-loop iteration lets Qt finish this press/release cycle
            # cleanly first.
            QTimer.singleShot(0, lambda: self._accept_sam_hover_box(candidate))
            return

        ctrl_held = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        if (
            ctrl_held
            and event.button() == Qt.MouseButton.LeftButton
            and self.pixmap_src
        ):
            # Ctrl always starts drawing a new box, regardless of what's under
            # the cursor -- do NOT forward to the scene, so an existing box's
            # own move/resize handling never engages while Ctrl is held.
            self.pt_1 = self.get_im_rel_point(event.pos())
            self.pt_2 = None
            event.accept()
            return

        if (
            not self._is_resize_handle_at(event.pos())
            and event.button() == Qt.MouseButton.LeftButton
            and self.pixmap_src
        ):
            # Plain click+drag pans the view -- over empty canvas, a SAM
            # suggestion overlay, or the body of an existing box (only its
            # edge/corner handles resize; dragging a box body no longer
            # moves it, so panning stays available even over nested boxes).
            self._panning = True
            self._pan_start_pos = event.pos()
            self._pan_start_scroll = (
                self.horizontalScrollBar().value(),
                self.verticalScrollBar().value(),
            )
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            self._current_cursor_shape = Qt.CursorShape.ClosedHandCursor

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        self._mouse_in_view = True
        ctrl_held = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)

        if ctrl_held and self.pixmap_src:
            self._update_crosshair(self.get_im_rel_point(event.pos()))
            if self._current_cursor_shape != Qt.CursorShape.BlankCursor:
                self.viewport().setCursor(Qt.CursorShape.BlankCursor)
                self._current_cursor_shape = Qt.CursorShape.BlankCursor
            if self._sam_hover_box is not None:
                # Ctrl is reserved for drawing; hide any SAM suggestion while held.
                self._sam_hover_box = None
                self._update_mouse_overlay()
            if self.pt_1 is not None and (event.buttons() & Qt.MouseButton.LeftButton):
                self.pt_2 = self.get_im_rel_point(event.pos())
                self._update_drag_rect_overlay()
            # Do not forward to the scene -- box hover/resize/move must not
            # engage while Ctrl (draw-new-box mode) is held.
            return

        self._update_crosshair(None)

        if self._panning and self._pan_start_pos is not None:
            delta = event.pos() - self._pan_start_pos
            self.horizontalScrollBar().setValue(self._pan_start_scroll[0] - delta.x())
            self.verticalScrollBar().setValue(self._pan_start_scroll[1] - delta.y())
            super().mouseMoveEvent(event)
            self._sync_minimap()
            return

        if self.pixmap_src is not None and not self._is_resize_handle_at(event.pos()):
            desired_cursor = Qt.CursorShape.OpenHandCursor
            if self._current_cursor_shape != desired_cursor:
                self.viewport().setCursor(desired_cursor)
                self._current_cursor_shape = desired_cursor

        self._maybe_update_hover_candidate(event)

        if (
            self.pixmap_src
            and self.pt_1 is not None
            and (event.buttons() & Qt.MouseButton.LeftButton)
        ):
            self.pt_2 = self.get_im_rel_point(event.pos())
            self._update_drag_rect_overlay()

        super().mouseMoveEvent(event)
        self._update_mouse_overlay()

    def _handle_box_click_selection(self, viewport_pos: QPoint):
        """Select the box under a click, cycling through overlapping boxes
        on repeated clicks at (roughly) the same spot."""
        if not self._has_scene():
            return
        scene_pos = self.mapToScene(viewport_pos)
        candidates = [
            it
            for it in self.scene().items(scene_pos)
            if isinstance(it, BoundingBoxItem) and it.editable
        ]
        if not candidates:
            self._last_select_click_pos = None
            self._last_select_candidates = []
            self._last_select_cycle_index = 0
            self.scene().clearSelection()
            return

        same_spot = (
            self._last_select_click_pos is not None
            and (viewport_pos - self._last_select_click_pos).manhattanLength()
            <= self.CLICK_DRAG_THRESHOLD
            and candidates == self._last_select_candidates
        )
        self._last_select_cycle_index = (
            (self._last_select_cycle_index + 1) % len(candidates) if same_spot else 0
        )
        self._last_select_click_pos = viewport_pos
        self._last_select_candidates = candidates

        target = candidates[self._last_select_cycle_index]
        self.scene().clearSelection()
        target.setSelected(True)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._panning:
            press_pos = self._pan_start_pos
            self._panning = False
            self._pan_start_pos = None
            self._pan_start_scroll = None
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
            self._current_cursor_shape = Qt.CursorShape.OpenHandCursor
            if (
                press_pos is not None
                and (event.pos() - press_pos).manhattanLength()
                <= self.CLICK_DRAG_THRESHOLD
            ):
                self._handle_box_click_selection(event.pos())
            super().mouseReleaseEvent(event)
            return

        if self.pixmap_src and self.pt_1 is not None and self.pt_2 is not None:
            new_rect = self.calc_crop_rect(self.calc_drag_rect())
            box_json = {
                "x": int(new_rect.x()),
                "y": int(new_rect.y()),
                "width": int(new_rect.width()),
                "height": int(new_rect.height()),
                "image_reference_uuid": self.moment.imaged_moment.image_reference_uuid,
            }

            concept = (
                self.observation_map[self.observation_uuid].observation.concept
                if self.observation_uuid
                else ""
            )
            observer = self.observer

            new_src_box = SourceBoundingBox(box_json, concept, observer, part="self")
            if new_src_box.width() * new_src_box.height() > 100:
                try:
                    self.handle_new_box(new_src_box)
                except Exception as exc:
                    QMessageBox.warning(self, "Box creation failed", str(exc))

        self.pt_1 = None
        self.pt_2 = None
        self._clear_drag_rect_overlay()
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        self.pt_1 = None
        self.pt_2 = None
        item = self.itemAt(event.pos())
        box_item = item if isinstance(item, BoundingBoxItem) else None
        if box_item is None and item is not None:
            parent = item.parentItem()
            if isinstance(parent, BoundingBoxItem):
                box_item = parent
        if box_item is not None and box_item.editable:
            self.show_box_properties_dialog(box_item)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def enterEvent(self, event: QEnterEvent) -> None:
        self._mouse_in_view = True
        if self.pixmap_src is not None and not self._panning:
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
            self._current_cursor_shape = Qt.CursorShape.OpenHandCursor
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._mouse_in_view = False
        self._sam_hover_box = None
        self._sam_last_hover_point = None
        self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        self._current_cursor_shape = Qt.CursorShape.ArrowCursor
        self._update_crosshair(None)
        self._update_mouse_overlay()
        super().leaveEvent(event)

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        super().scrollContentsBy(dx, dy)
        self._sync_minimap()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if not self._user_has_zoomed:
            self._fit_to_view()
        self._position_overlays()
        self._sync_minimap()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Up:
            self.select_prev()
        elif event.key() == Qt.Key.Key_Down:
            self.select_next()
        elif event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            if self.selected_box is not None:
                choice = QMessageBox.question(
                    self,
                    "Delete Box?",
                    "Delete the selected bounding box?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if choice == QMessageBox.StandardButton.Yes:
                    try:
                        self.delete_box(self.selected_box)
                    except Exception as exc:
                        QMessageBox.warning(self, "Delete failed", str(exc))
            else:
                super().keyPressEvent(event)
        else:
            super().keyPressEvent(event)
