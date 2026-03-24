"""Custom QGraphicsView widget for controlling image/localization graphics and input."""

from typing import Callable, List, Optional, Any, cast

from PyQt6.QtCore import Qt, QPoint, QPointF, QRectF, QLineF, QSizeF
from PyQt6.QtGui import (
    QImage,
    QResizeEvent,
    QMouseEvent,
    QPixmap,
    QColor,
    QKeyEvent,
    QPen,
    QFont,
)
from PyQt6.QtWidgets import (
    QGraphicsView,
    QGraphicsScene,
    QDialog,
    QVBoxLayout,
    QPushButton,
    QMessageBox,
)

from vars_localize.ui.ConceptSearchbar import ConceptSearchbar
from vars_localize.ui.EntryTree import EntryTreeItem, update_imaged_moment_entry
from vars_localize.models import ImagedMomentEntry
from vars_localize.ui.BoundingBox import (
    BoundingBoxManager,
    GraphicsBoundingBox,
    SourceBoundingBox,
)
from vars_localize.ui.PropertiesDialog import PropertiesDialog
from vars_localize.ui.theme import PALETTE
from vars_localize.services import M3Service
from vars_localize.util.qt_async import run_async
from vars_localize.util.utils import center_window, log


class ImageView(QGraphicsView):
    SAM_MIN_AREA = 100
    SAM_OVERLAP_IOU = 0.2

    def __init__(self, parent=None):
        super(ImageView, self).__init__(parent)

        self.setMinimumSize(1200, 675)
        self.setViewportMargins(-2, -2, -2, -2)
        self.setMouseTracking(True)

        self.image_scene = QGraphicsScene()
        self.setScene(self.image_scene)
        self.refit()

        self.observation_uuid = None
        self.observer = None
        self.moment = None
        self.observation_map = None
        self.enabled_observations = None

        self.pixmap_src = None
        self.pixmap_scalar = None
        self.pixmap_pos = None

        self.select_next = None
        self.select_prev = None
        self.m3_service = None
        self.sam3_service = None

        # Graphical box selection
        self.pt_1 = None
        self.pt_2 = None
        self.selected_box = None
        self.hovered_box = None
        self.mouse_line_pen = QPen(QColor(PALETTE["accent"]))
        self.mouse_hline = QLineF()
        self.mouse_vline = QLineF()

        self.hov_tl_rect = None
        self.hov_tr_rect = None
        self.hov_bl_rect = None
        self.hov_br_rect = None
        self.resize_type = None
        self.resize_offset = None

        self.hov_pt_1 = None
        self._image_loading = False
        self._image_loading_uuid = None
        self._image_loading_error = None

        self._sam_assist_enabled = False
        self._sam_ready_image_uuid = None
        self._sam_embedding_busy = False
        self._sam_embedding_request_uuid = None
        self._sam_candidate_boxes: List[SourceBoundingBox] = []
        self._sam_candidate_index = 0
        self._sam_candidate_observation_uuid = None
        self._sam_pending_observation_uuid = None
        self._sam_hover_box: Optional[SourceBoundingBox] = None
        self._sam_hover_inflight = False
        self._sam_last_hover_point = None
        self._sam_candidate_ui_callback: Optional[Callable[[bool, int, int], None]] = (
            None
        )
        self._sam_status_ui_callback: Optional[Callable[[str], None]] = None

        self._sam_min_area = self.SAM_MIN_AREA
        self._sam_overlap_iou = self.SAM_OVERLAP_IOU

    def configure_sam_params(self, min_area: int, overlap_iou: float):
        self._sam_min_area = max(1, int(min_area))
        self._sam_overlap_iou = max(0.0, min(1.0, float(overlap_iou)))

    def _m3_fetch_image(self, url: str):
        return self._require_m3_service().fetch_image(url)

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

    def _require_m3_service(self) -> M3Service:
        if self.m3_service is None:
            raise RuntimeError("ImageView requires an injected M3Service instance")
        return self.m3_service

    def set_sam_candidate_ui_callback(self, callback: Callable[[bool, int, int], None]):
        self._sam_candidate_ui_callback = callback
        self._notify_sam_candidate_state()

    def set_sam_status_ui_callback(self, callback: Callable[[str], None]):
        self._sam_status_ui_callback = callback
        self._notify_sam_status(self._build_sam_status())

    def _notify_sam_status(self, status: str):
        if self._sam_status_ui_callback is None:
            return
        self._sam_status_ui_callback(status)

    def _point_capability_text(self) -> str:
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

    def _build_sam_status(self) -> str:
        if self.sam3_service is None or not self.sam3_service.available:
            return "SAM unavailable"
        if not self._sam_assist_enabled:
            return "SAM disabled"
        if self.moment is None or self.pixmap_src is None:
            return "SAM enabled, waiting for image"
        if self._sam_embedding_busy:
            return "SAM loading image embedding..."
        if self._sam_ready_image_uuid == self.moment.imaged_moment.uuid:
            return "SAM ready: text prompts ready, {}".format(
                self._point_capability_text()
            )
        return "SAM enabled, embedding not ready"

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
        self._sam_pending_observation_uuid = None
        self._sam_hover_box = None
        self._sam_hover_inflight = False
        self._sam_last_hover_point = None
        if reset_embedding:
            self._sam_ready_image_uuid = None
            self._sam_embedding_request_uuid = None
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
        if self.handle_new_box(candidate):
            self._drop_current_candidate()
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
        if self._sam_ready_image_uuid == moment_uuid or self._sam_embedding_busy:
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
            self._notify_sam_status(self._build_sam_status())
            pending_uuid = self._sam_pending_observation_uuid
            if pending_uuid:
                self._sam_pending_observation_uuid = None
                self._start_sam_candidates_for_observation(pending_uuid)

        def _on_error(err):
            log("[SAM] embedding failed:\n{}".format(err), level=2)
            self._notify_sam_status("SAM embedding failed")

        def _on_finished():
            self._sam_embedding_busy = False
            self._notify_sam_status(self._build_sam_status())
            current_uuid = self.moment.imaged_moment.uuid if self.moment else None
            if (
                self._sam_assist_enabled
                and current_uuid is not None
                and self._sam_ready_image_uuid != current_uuid
            ):
                self._maybe_start_sam_embedding()

        run_async(
            self,
            _embed,
            on_result=_on_result,
            on_error=_on_error,
            on_finished=_on_finished,
        )

    def _start_sam_candidates_for_observation(self, observation_uuid: str):
        if not self._sam_assist_enabled:
            self._notify_sam_status(self._build_sam_status())
            return
        if not self.observation_map or observation_uuid not in self.observation_map:
            self._notify_sam_status(self._build_sam_status())
            return
        if self.moment is None:
            self._notify_sam_status(self._build_sam_status())
            return

        moment_uuid = self.moment.imaged_moment.uuid
        if self._sam_ready_image_uuid != moment_uuid:
            self._notify_sam_status("SAM waiting for embedding to query concept...")
            self._sam_pending_observation_uuid = observation_uuid
            self._maybe_start_sam_embedding()
            return

        observation = self.observation_map[observation_uuid].observation
        concept = observation.concept
        self._sam_candidate_observation_uuid = observation_uuid
        self._notify_sam_status("SAM querying concept '{}'...".format(concept))

        def _on_result(boxes):
            if self.moment is None:
                return
            current_uuid = self.moment.imaged_moment.uuid
            if current_uuid != moment_uuid:
                return
            if self.observation_uuid != observation_uuid:
                return

            candidates = self._make_candidate_boxes(boxes, observation_uuid, concept)
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
            log("[SAM] concept query failed:\n{}".format(err), level=2)
            self._notify_sam_status("SAM concept query failed")

        run_async(
            self,
            self._sam_query_text,
            concept,
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
        if self.pixmap_src is None or self.moment is None:
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
                # log("[SAM] hover result ignored: SAM assist disabled", level=1)
                return

            self._sam_hover_box = None
            boxes = self._filter_point_prompt_boxes(boxes)
            if not boxes:
                # log("[SAM] hover produced no boxes after filter", level=1)
                self.redraw()
                return

            observation_uuid = self.observation_uuid
            concept = ""
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
            # log("[SAM] hover candidate boxes after overlap filter: {}".format(len(candidates)), level=1)
            if candidates:
                self._sam_hover_box = candidates[0]
                # log(
                #     "[SAM] hover selected candidate: x={}, y={}, w={}, h={}".format(
                #         self._sam_hover_box.x(),
                #         self._sam_hover_box.y(),
                #         self._sam_hover_box.width(),
                #         self._sam_hover_box.height(),
                #     ),
                #     level=1,
                # )
            if self.sam3_service is not None and self.sam3_service.available:
                self._notify_sam_status(
                    "SAM ready: text prompts ready, {}".format(
                        self._point_capability_text()
                    )
                )
            self.redraw()

        def _on_error(err):
            # log("[SAM] hover query failed:\n{}".format(err), level=2)
            self._notify_sam_status("SAM point prompt query failed")

        def _on_finished():
            self._sam_hover_inflight = False
            if self.sam3_service is not None and self.sam3_service.available:
                self._notify_sam_status(
                    "SAM ready: text prompts ready, {}".format(
                        self._point_capability_text()
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

    def redraw(self):
        """Redraw the scene with image, overlays, and interaction guides."""
        self.clear()
        self.refit()
        self.scene().setBackgroundBrush(QColor(PALETTE["bg_subtle"]))
        if self.pixmap_src:  # Image loaded, draw image + relevant components
            self.draw_pixmap(self.pixmap_src)

            self.draw_ancillary_data()

            if self.enabled_observations:
                for uuid, enabled in self.enabled_observations.items():
                    if not enabled:
                        continue

                    item = self.observation_map[uuid]
                    observation = item.observation
                    box_manager = observation.box_manager
                    boxes = observation.boxes
                    video_boxes = observation.video_boxes
                    for box in boxes:
                        box_item = self.draw_bounding_box(box, box_manager)
                        if self.selected_box == box:
                            box_item.set_highlighted(True)
                        if self.hovered_box == box:
                            self.draw_drag_corners(box_item)
                    for video_box in video_boxes:
                        self.draw_bounding_box(video_box, box_manager, editable=False)

            sam_candidate = self._current_sam_candidate
            if sam_candidate is not None:
                top_left = self.get_scene_rel_point(
                    QPointF(sam_candidate.x(), sam_candidate.y())
                )
                self.scene().addRect(
                    QRectF(
                        QPointF(top_left),
                        QSizeF(
                            sam_candidate.width() * self.pixmap_scalar,
                            sam_candidate.height() * self.pixmap_scalar,
                        ),
                    ),
                    QPen(QColor(PALETTE["success"]), 2, Qt.PenStyle.DashLine),
                )

            if self._sam_hover_box is not None:
                hover_top_left = self.get_scene_rel_point(
                    QPointF(self._sam_hover_box.x(), self._sam_hover_box.y())
                )
                self.scene().addRect(
                    QRectF(
                        QPointF(hover_top_left),
                        QSizeF(
                            self._sam_hover_box.width() * self.pixmap_scalar,
                            self._sam_hover_box.height() * self.pixmap_scalar,
                        ),
                    ),
                    QPen(QColor(PALETTE["warning"]), 2, Qt.PenStyle.DashLine),
                )

            # Draw crosshairs
            self.scene().addLine(self.mouse_hline, self.mouse_line_pen)
            self.scene().addLine(self.mouse_vline, self.mouse_line_pen)
            self.setCursor(Qt.CursorShape.BlankCursor)

            drag_rect = self.calc_drag_rect()
            if drag_rect:  # Drag rectangle should be drawn
                top_left = self.get_scene_rel_point(
                    QPointF(drag_rect.x(), drag_rect.y())
                )
                scaled_size = drag_rect.size() * self.pixmap_scalar
                self.scene().addRect(
                    QRectF(QPointF(top_left), scaled_size),
                    QColor(PALETTE["accent_alt"]),
                )
        else:  # No image loaded
            if self._image_loading:
                msg = "Loading image..."
            elif self._image_loading_error:
                msg = self._image_loading_error
            else:
                msg = "No image loaded."
            text_item = self.scene().addText(msg, QFont("Courier New"))
            text_item.setDefaultTextColor(QColor(PALETTE["fg_primary"]))
            text_item.setPos(
                self.width() / 2 - text_item.boundingRect().width() / 2,
                self.height() / 2 - text_item.boundingRect().height() / 2,
            )
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def clear(self):
        """Clear scene items and reset all bounding box managers."""
        self.scene().clear()
        if self.observation_map:
            for box_manager in [
                entry.observation.box_manager for entry in self.observation_map.values()
            ]:
                if box_manager is not None:
                    box_manager.clear()

    def set_entry(self, entry: EntryTreeItem):
        """Set the selected tree entry and load associated data.

        Args:
            entry: Entry tree item to load from.
        """
        if entry.is_imaged_moment:
            entry.setExpanded(True)
            if entry != self.moment:
                self.load_moment(entry)
            self.select_observation("all")
        elif entry.is_observation:
            if entry.parent() != self.moment:
                self.load_moment(entry.parent())
            self.select_observation(entry.observation.uuid)
            if self._sam_assist_enabled:
                self._start_sam_candidates_for_observation(entry.observation.uuid)

    def load_moment(self, entry: EntryTreeItem):
        """Load data for an imaged moment entry.

        Args:
            entry: Entry tree item of an imaged moment.
        """
        self.moment = entry
        self._clear_sam_state(reset_embedding=True)
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
                on_result=_on_result,
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
            uuid = observation.uuid
            observation.box_manager = BoundingBoxManager()
            observation.box_manager.set_box_click_callback(
                self.show_box_properties_dialog
            )

            def override_obs_selection(obs_entry):
                def wrapped(_):
                    self.parent().parent().parent().load_entry(obs_entry, None)
                    self.parent().parent().parent().search_panel.select_entry(obs_entry)

                return wrapped

            observation.box_manager.set_box_right_click_callback(
                override_obs_selection(observation_entry)
            )
            self.enabled_observations[uuid] = True

    def draw_drag_corners(self, box: GraphicsBoundingBox):
        length = 10
        tl_rect = self.scene().addRect(
            box.x(), box.y(), length, length, pen=box.color.lighter()
        )
        tr_rect = self.scene().addRect(
            box.x() + box.width - length,
            box.y(),
            length,
            length,
            pen=box.color.lighter(),
        )
        bl_rect = self.scene().addRect(
            box.x(),
            box.y() + box.height - length,
            length,
            length,
            pen=box.color.lighter(),
        )
        br_rect = self.scene().addRect(
            box.x() + box.width - length,
            box.y() + box.height - length,
            length,
            length,
            pen=box.color.lighter(),
        )

        self.hov_tl_rect = tl_rect.rect()
        self.hov_tr_rect = tr_rect.rect()
        self.hov_bl_rect = bl_rect.rect()
        self.hov_br_rect = br_rect.rect()

    def set_pixmap(self, pixmap):
        """Set the source pixmap and clear drag anchors.

        Args:
            pixmap: Source pixmap to display.
        """
        self.pixmap_src = pixmap
        self.pt_1 = None
        self.pt_2 = None

    def select_observation(self, observation_uuid: str):
        """Select and display boxes for a specific observation.

        Args:
            observation_uuid: Observation UUID to display, or "all".
        """
        for uuid in self.enabled_observations.keys():
            self.enabled_observations[uuid] = (
                True
                if (observation_uuid == uuid or observation_uuid == "all")
                else False
            )
        self.observation_uuid = observation_uuid if observation_uuid != "all" else None
        if self.observation_uuid is None:
            self._sam_candidate_boxes = []
            self._sam_hover_box = None
            self._notify_sam_candidate_state()

    def focus_association_box(
        self, observation_uuid: str, association_uuid: str
    ) -> bool:
        if not self.observation_map:
            return False

        observation_entry = self.observation_map.get(observation_uuid)
        if observation_entry is None:
            return False

        self.select_observation(observation_uuid)
        observation = observation_entry.observation
        all_boxes = list(observation.boxes) + list(observation.video_boxes)

        for box in all_boxes:
            if box.association_uuid == association_uuid:
                self.selected_box = box
                self.hovered_box = None
                self.redraw()
                return True

        return False

    def refit(self):
        """Refit the scene rectangle to match the current view size."""
        self.setSceneRect(0, 0, self.width(), self.height())

    def draw_pixmap(self, pixmap: QPixmap):
        """Scale and draw a pixmap into the scene.

        Args:
            pixmap: Pixmap object to draw.

        Returns:
            QGraphicsPixmapItem | None: Created scene item, if drawn.
        """
        if not pixmap or pixmap.isNull():
            return
        scaled_pixmap = pixmap.scaled(
            self.width(), self.height(), Qt.AspectRatioMode.KeepAspectRatio
        )
        self.pixmap_scalar = scaled_pixmap.width() / pixmap.width()
        self.pixmap_pos = QPointF(
            self.width() / 2 - scaled_pixmap.width() / 2,
            self.height() / 2 - scaled_pixmap.height() / 2,
        )

        pixmap_item = self.scene().addPixmap(scaled_pixmap)
        pixmap_item.setPos(self.pixmap_pos)
        return pixmap_item

    def draw_ancillary_data(self):
        """Draw ancillary metadata text over the current image."""
        text_dict = {}

        moment = self.moment.imaged_moment

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

        if moment.video_data is None and moment.video_reference_uuid:
            moment.video_data = self._m3_get_video_data(moment.video_reference_uuid)

        if moment.video_data and "uri" in moment.video_data:
            uri = moment.video_data["uri"]
            if uri.startswith("urn:"):
                video_sequence_name = moment.video_data["uri"].split(":")[-1]
                text_dict["Video: {:<10}"] = video_sequence_name

        text_str = " ".join(k.format(v) for k, v in text_dict.items())
        text_item = self.scene().addText(text_str, QFont("Courier New"))
        text_item.setDefaultTextColor(QColor(PALETTE["fg_primary"]))
        text_item.setPos(10, self.height() - text_item.boundingRect().height() - 10)

    def draw_bounding_box(
        self,
        box_src: SourceBoundingBox,
        manager: BoundingBoxManager,
        editable: bool = True,
    ):
        """Draw a bounding box and register it in a manager.

        Args:
            box_src: Source bounding box to add.
            manager: Bounding box manager.
            editable: Whether the box should be editable.

        Returns:
            GraphicsBoundingBox: Drawn graphics item.
        """
        box_pos = self.get_scene_rel_point(QPointF(box_src.x(), box_src.y()))
        box_item = manager.make_box(
            box_pos.x(),
            box_pos.y(),
            self.pixmap_scalar * box_src.width(),
            self.pixmap_scalar * box_src.height(),
            box_src.label,
            box_src,
            editable=editable,
        )
        self.scene().addItem(box_item)
        return box_item

    def get_im_rel_point(self, pt: QPoint):
        """Convert a scene-relative point to image coordinates.

        Args:
            pt: Scene-relative point.

        Returns:
            QPointF: Point relative to the image.
        """
        return QPointF(
            (pt.x() - self.pixmap_pos.x()) / self.pixmap_scalar,
            (pt.y() - self.pixmap_pos.y()) / self.pixmap_scalar,
        )

    def get_scene_rel_point(self, pt: QPointF):
        """Convert an image-relative point to scene coordinates.

        Args:
            pt: Image-relative point.

        Returns:
            QPoint: Point relative to the scene.
        """
        return QPoint(
            int(self.pixmap_scalar * pt.x() + self.pixmap_pos.x()),
            int(self.pixmap_scalar * pt.y() + self.pixmap_pos.y()),
        )

    def show_box_properties_dialog(self, box: GraphicsBoundingBox):
        """Open the properties dialog for a selected box.

        Args:
            box: Graphical bounding box object to edit.
        """
        self.selected_box = box.source
        self.redraw()

        box_json_before = box.source.get_json()
        part_before = box.source.part or "self"

        dialog = PropertiesDialog(box.source, parent=self)
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

        box_json_after = box.source.get_json()
        part_after = box.source.part or "self"
        if box_json_after != box_json_before or part_after != part_before:
            box.source.observer = self.observer  # Update observer field
            self._m3_modify_box(
                box_json_after,
                box.source.observation_uuid,
                box.source.association_uuid,
                to_concept=part_after,
            )
            update_imaged_moment_entry(self.moment)  # Update tree

        self.pt_1 = None
        self.pt_2 = None

        self.selected_box = None
        self.redraw()

    def delete_box(self, box: SourceBoundingBox):
        """Delete a box from the observation and persist deletion.

        Args:
            box: Source bounding box to delete.
        """
        observation = self.observation_map[box.observation_uuid].observation
        source_boxes = observation.boxes
        if box in source_boxes:
            source_boxes.remove(box)
            self._m3_delete_box(box.association_uuid)  # Call deletion request
            update_imaged_moment_entry(self.moment)  # Update tree

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

        # Reuse concepts from the main search bar so the prompt behaves consistently.
        try:
            root_any = cast(Any, self.window())
            search.set_concepts(root_any.search_panel.search_bar.get_concepts())
        except Exception:
            search.set_concepts([])

        submit_button = QPushButton("Submit")
        submit_button.setEnabled(False)
        submit_button.pressed.connect(dialog.accept)

        concept_selected = ""

        def update_concept_selected(concept):
            nonlocal concept_selected
            text = str(concept or "").strip()
            concept_selected = text
            submit_button.setEnabled(bool(text))

        search.textChanged.connect(update_concept_selected)
        search.set_callback(update_concept_selected)
        search.returnPressed.connect(dialog.accept)
        search.setFocus()

        dialog.layout().addWidget(search)
        dialog.layout().addWidget(submit_button)

        dialog.setModal(True)
        dialog.adjustSize()
        center_window(dialog, self.window())
        accepted = dialog.exec()
        if accepted != QDialog.DialogCode.Accepted:
            return ""
        return concept_selected.strip()

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

        observation = self._m3_create_observation(  # Call observation creation request
            moment.video_reference_uuid,
            concept,
            self.observer,
            **kwargs,
        )

        if not observation or "observation_uuid" not in observation:
            return None

        self.moment.treeWidget().editable_uuids.add(observation["observation_uuid"])

        self.reload_moment()

        return observation

    def reload_moment(self):
        """Fully reload the current imaged moment entry."""
        image = self.moment.imaged_moment.cached_image
        self.moment.treeWidget().load_imaged_moment_entry(
            self.moment
        )  # Reload the tree
        if image is not None:
            self.moment.imaged_moment.cached_image = image
        self.load_moment(self.moment)  # Reload imaged moment

    def handle_new_box(self, box: SourceBoundingBox) -> bool:
        """Create a new box, creating an observation if needed.

        Args:
            box: Source bounding box.

        Returns:
            bool: True on success, False on failure.
        """
        uuid = self.observation_uuid
        if not uuid:  # Imaged moment selected
            new_concept = self.prompt_concept()
            if not new_concept:  # No concept was specified
                return False
            observation = self.make_new_observation(new_concept)
            if not observation or "observation_uuid" not in observation:
                QMessageBox.warning(
                    self,
                    "Observation creation failed",
                    "Could not create an observation for the selected concept.",
                )
                return False
            box.set_label(new_concept)
            uuid = observation["observation_uuid"]

        if not self.observation_map or uuid not in self.observation_map:
            QMessageBox.warning(
                self,
                "Box creation failed",
                "Could not resolve the target observation for this box.",
            )
            return False

        box.observation_uuid = uuid
        observation = self.observation_map[uuid].observation

        response_json = self._m3_create_box(box.get_json(), uuid, to_concept=box.part)
        if not response_json or "uuid" not in response_json:
            QMessageBox.warning(
                self,
                "Box creation failed",
                "Server rejected this box. Please try again or adjust box bounds.",
            )
            return False

        box.association_uuid = response_json["uuid"]
        self.draw_bounding_box(box, observation.box_manager)
        observation.boxes.append(box)
        update_imaged_moment_entry(self.moment)  # Update tree
        return True

    def reset_mouse(self):
        self.pt_1 = None
        self.pt_2 = None
        self.hov_pt_1 = None
        self.resize_offset = None
        self.resize_type = None
        self._sam_hover_box = None
        self.redraw()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self.pixmap_src:
            new_rect = self.calc_drag_rect()
            if new_rect:
                new_rect = self.calc_crop_rect(new_rect)
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

                # Default fast-path: create boxes as "self" and allow editing in properties.
                new_src_box = SourceBoundingBox(
                    box_json, concept, observer, part="self"
                )
                if new_src_box.width() * new_src_box.height() > 100:
                    self.handle_new_box(new_src_box)

            if self.resize_type:
                self._m3_modify_box(
                    self.hovered_box.get_json(),
                    self.hovered_box.observation_uuid,
                    self.hovered_box.association_uuid,
                    to_concept=self.hovered_box.part or "self",
                )

            self.reset_mouse()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if (
            event.button() == Qt.MouseButton.RightButton
            and self._sam_assist_enabled
            and self._sam_hover_box is not None
        ):
            if self.handle_new_box(self._sam_hover_box):
                self._sam_hover_box = None
            self.redraw()
            event.accept()
            return

        pos_f = QPointF(event.pos())
        if self.pixmap_src:
            self.pt_1 = self.get_im_rel_point(pos_f)
        if self.hovered_box:
            corner_box = None
            self.hov_pt_1 = self.get_im_rel_point(pos_f)
            if self.hov_tl_rect is not None and self.hov_tl_rect.contains(pos_f):
                self.resize_type = 1
                corner_box = self.hov_tl_rect
            elif self.hov_tr_rect is not None and self.hov_tr_rect.contains(pos_f):
                self.resize_type = 2
                corner_box = self.hov_tr_rect
            elif self.hov_bl_rect is not None and self.hov_bl_rect.contains(pos_f):
                self.resize_type = 3
                corner_box = self.hov_bl_rect
            elif self.hov_br_rect is not None and self.hov_br_rect.contains(pos_f):
                self.resize_type = 4
                corner_box = self.hov_br_rect
            else:
                self.hov_pt_1 = None

            if corner_box:
                self.pt_1 = None
                x, y, _, _ = corner_box.getRect()
                corner = self.get_im_rel_point(QPoint(int(x), int(y)))
                self.resize_offset = self.hov_pt_1 - corner

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self.pixmap_src:
            self.pt_2 = self.get_im_rel_point(event.pos())
            if self.hovered_box:
                if self.resize_type == 1:
                    new_tl_corner = (self.pt_2 - self.resize_offset).toPoint()
                    if new_tl_corner.x() < 0:
                        new_tl_corner.setX(0)
                    if new_tl_corner.y() < 0:
                        new_tl_corner.setY(0)
                    self.hovered_box.setTopLeft(new_tl_corner)
                elif self.resize_type == 2:
                    new_tr_corner = (self.pt_2 - self.resize_offset).toPoint()
                    new_tr_corner.setX(
                        int(new_tr_corner.x() + 2 * self.resize_offset.x())
                    )
                    if new_tr_corner.x() > self.pixmap_src.width():
                        new_tr_corner.setX(int(self.pixmap_src.width()))
                    if new_tr_corner.y() < 0:
                        new_tr_corner.setY(0)
                    self.hovered_box.setTopRight(new_tr_corner)
                elif self.resize_type == 3:
                    new_bl_corner = (self.pt_2 - self.resize_offset).toPoint()
                    new_bl_corner.setY(
                        int(new_bl_corner.y() + 2 * self.resize_offset.y())
                    )
                    if new_bl_corner.x() < 0:
                        new_bl_corner.setX(0)
                    if new_bl_corner.y() > self.pixmap_src.height():
                        new_bl_corner.setY(int(self.pixmap_src.height()))
                    self.hovered_box.setBottomLeft(new_bl_corner)
                elif self.resize_type == 4:
                    new_br_corner = (self.pt_2 - self.resize_offset).toPoint()
                    new_br_corner.setX(
                        int(new_br_corner.x() + 2 * self.resize_offset.x())
                    )
                    new_br_corner.setY(
                        int(new_br_corner.y() + 2 * self.resize_offset.y())
                    )
                    if new_br_corner.x() > self.pixmap_src.width():
                        new_br_corner.setX(int(self.pixmap_src.width()))
                    if new_br_corner.y() > self.pixmap_src.height():
                        new_br_corner.setY(int(self.pixmap_src.height()))
                    self.hovered_box.setBottomRight(new_br_corner)

        self.mouse_hline.setLine(
            0, event.pos().y(), self.scene().width(), event.pos().y()
        )
        self.mouse_vline.setLine(
            event.pos().x(), 0, event.pos().x(), self.scene().height()
        )

        if self.enabled_observations and not self.resize_type:
            for uuid, enabled in self.enabled_observations.items():
                if enabled:
                    hov_box_item = self.observation_map[
                        uuid
                    ].observation.box_manager.get_box_hovered(event.pos())
                    if hov_box_item:
                        self.hovered_box = hov_box_item.source
                    else:
                        self.hovered_box = None

        self._maybe_update_hover_candidate(event)

        self.redraw()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if self.pixmap_src:
            self.pt_1 = None
            self.pt_2 = None
            for uuid, enabled in self.enabled_observations.items():
                if enabled:
                    self.observation_map[uuid].observation.box_manager.check_box_click(
                        event.pos(), event.button() == Qt.MouseButton.RightButton
                    )

    def resizeEvent(self, event: QResizeEvent) -> None:
        self.redraw()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Up:
            self.select_prev()
        elif event.key() == Qt.Key.Key_Down:
            self.select_next()
