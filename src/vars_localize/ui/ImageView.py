"""Custom QGraphicsView widget for controlling image/localization graphics and input."""

from __future__ import annotations

from typing import Callable, List, Optional, Any, cast

from PyQt6.QtCore import Qt, QPoint, QPointF, QRectF, QLineF, QSizeF
from PyQt6.QtGui import (
    QEnterEvent,
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
    QGraphicsLineItem,
    QDialog,
    QVBoxLayout,
    QPushButton,
    QMessageBox,
)

from vars_localize.ui.ConceptSearchbar import ConceptSearchbar
from vars_localize.ui.EntryTree import EntryTreeItem
from vars_localize.models import ImagedMomentEntry
from vars_localize.ui.BoundingBox import (
    BoundingBoxManager,
    GraphicsBoundingBox,
    SourceBoundingBox,
)
from vars_localize.ui.PropertiesDialog import PropertiesDialog
from vars_localize.ui.theme import PALETTE
from vars_localize.services import M3Service
from vars_localize.services.errors import ServiceError
from vars_localize.util.logging import get_logger
from vars_localize.util.qt_async import run_async
from vars_localize.util.utils import center_window

logger = get_logger("ImageView")


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
        self._observation_select_callback: Optional[Callable[[EntryTreeItem], None]] = (
            None
        )
        self.m3_service = None
        self.sam3_service = None

        # Graphical box selection
        self.pt_1 = None
        self.pt_2 = None
        self.selected_box = None
        self.hovered_box = None
        self.mouse_line_pen = QPen(QColor(PALETTE["crosshairs"]))
        self.mouse_hline = QLineF()
        self.mouse_vline = QLineF()
        self._crosshair_h_item: Optional[QGraphicsLineItem] = None
        self._crosshair_v_item: Optional[QGraphicsLineItem] = None

        self.hov_tl_rect = None
        self.hov_tr_rect = None
        self.hov_bl_rect = None
        self.hov_br_rect = None
        self.resize_type = None
        self.resize_offset = None
        self._hover_handle_type = 0

        self.hov_pt_1 = None
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

        # Cache scaled pixmap by (source cache key, view width, view height).
        self._scaled_pixmap_key: Optional[tuple[int, int, int]] = None
        self._scaled_pixmap: Optional[QPixmap] = None

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
            if not self._mouse_in_view:
                self._sam_hover_box = None
                self.redraw()
                return

            self._sam_hover_box = None
            boxes = self._filter_point_prompt_boxes(boxes)
            if not boxes:
                # log("[SAM] hover produced no boxes after filter", level=1)
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
                    "SAM ready: {}, {}".format(
                        self._semantic_capability_text(), self._point_capability_text()
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
                        if self._box_is_highlighted(box):
                            box_item.set_highlighted(True)
                        if self.hovered_box == box:
                            self.draw_drag_corners(box_item)
                    for video_box in video_boxes:
                        video_box_item = self.draw_bounding_box(
                            video_box,
                            box_manager,
                            editable=False,
                        )
                        if self._box_is_highlighted(video_box):
                            video_box_item.set_highlighted(True)

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

            if self._mouse_in_view and self._sam_hover_box is not None:
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

            if self._mouse_in_view:
                handle_type = self.resize_type or self._hover_handle_type
                if handle_type in (1, 4):
                    self.setCursor(Qt.CursorShape.SizeFDiagCursor)
                elif handle_type in (2, 3):
                    self.setCursor(Qt.CursorShape.SizeBDiagCursor)
                else:
                    self.setCursor(Qt.CursorShape.BlankCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)

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

        self._update_mouse_overlay()

    def clear(self):
        """Clear scene items and reset all bounding box managers."""
        self.scene().clear()
        self._crosshair_h_item = None
        self._crosshair_v_item = None
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
            uuid = observation.uuid
            observation.box_manager = BoundingBoxManager()
            observation.box_manager.set_box_click_callback(
                self.show_box_properties_dialog
            )

            def override_obs_selection(obs_entry):
                def wrapped(_):
                    if self._observation_select_callback is not None:
                        self._observation_select_callback(obs_entry)

                return wrapped

            observation.box_manager.set_box_right_click_callback(
                override_obs_selection(observation_entry)
            )
            self.enabled_observations[uuid] = True

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
        self._invalidate_scaled_pixmap_cache()
        self.pt_1 = None
        self.pt_2 = None

    def _invalidate_scaled_pixmap_cache(self):
        self._scaled_pixmap_key = None
        self._scaled_pixmap = None

    def _ensure_crosshair_items(self):
        if self._crosshair_h_item is None:
            self._crosshair_h_item = self.scene().addLine(
                self.mouse_hline, self.mouse_line_pen
            )
        if self._crosshair_v_item is None:
            self._crosshair_v_item = self.scene().addLine(
                self.mouse_vline, self.mouse_line_pen
            )

    def _update_mouse_overlay(self):
        """Update live crosshair overlay without rebuilding the full scene."""
        if self.pixmap_src is None:
            return

        self._ensure_crosshair_items()
        if self._crosshair_h_item is not None:
            self._crosshair_h_item.setLine(self.mouse_hline)
        if self._crosshair_v_item is not None:
            self._crosshair_v_item.setLine(self.mouse_vline)

        handle_type = self.resize_type or self._hover_handle_type
        show_crosshair = bool(self._mouse_in_view and handle_type == 0)
        if self._crosshair_h_item is not None:
            self._crosshair_h_item.setVisible(show_crosshair)
        if self._crosshair_v_item is not None:
            self._crosshair_v_item.setVisible(show_crosshair)

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
                self.hovered_box = None
                self.redraw()
                return

        raise LookupError("Could not find the selected association box.")

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

        cache_key = (int(pixmap.cacheKey()), int(self.width()), int(self.height()))
        if self._scaled_pixmap_key == cache_key and self._scaled_pixmap is not None:
            scaled_pixmap = self._scaled_pixmap
        else:
            scaled_pixmap = pixmap.scaled(
                self.width(),
                self.height(),
                Qt.AspectRatioMode.KeepAspectRatio,
            )
            self._scaled_pixmap_key = cache_key
            self._scaled_pixmap = scaled_pixmap

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
            try:
                self._m3_modify_box(
                    box_json_after,
                    box.source.observation_uuid,
                    box.source.association_uuid,
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
        self.redraw()

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

    def reset_mouse(self):
        self.pt_1 = None
        self.pt_2 = None
        self.hov_pt_1 = None
        self.resize_offset = None
        self.resize_type = None
        self._hover_handle_type = 0
        self._sam_hover_box = None
        self.redraw()

    def _drag_handle_hover_type(self, scene_pos: QPointF) -> int:
        if self.hovered_box is None or self.pixmap_scalar is None:
            return 0

        length = 10.0
        top_left = self.get_scene_rel_point(
            QPointF(self.hovered_box.x(), self.hovered_box.y())
        )
        x = float(top_left.x())
        y = float(top_left.y())
        w = float(self.hovered_box.width()) * float(self.pixmap_scalar)
        h = float(self.hovered_box.height()) * float(self.pixmap_scalar)

        if QRectF(x, y, length, length).contains(scene_pos):
            return 1
        if QRectF(x + w - length, y, length, length).contains(scene_pos):
            return 2
        if QRectF(x, y + h - length, length, length).contains(scene_pos):
            return 3
        if QRectF(x + w - length, y + h - length, length, length).contains(scene_pos):
            return 4
        return 0

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
                    try:
                        self.handle_new_box(new_src_box)
                    except Exception as exc:
                        QMessageBox.warning(self, "Box creation failed", str(exc))

            if self.resize_type:
                try:
                    self._m3_modify_box(
                        self.hovered_box.get_json(),
                        self.hovered_box.observation_uuid,
                        self.hovered_box.association_uuid,
                        to_concept=self.hovered_box.part or "self",
                    )
                except ServiceError as exc:
                    QMessageBox.warning(
                        self,
                        "Resize failed",
                        "Could not persist box resize.\n\n{}".format(exc),
                    )
                else:
                    self.reload_moment()

            self.reset_mouse()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if (
            event.button() == Qt.MouseButton.RightButton
            and self._sam_assist_enabled
            and self._sam_hover_box is not None
        ):
            try:
                self.handle_new_box(
                    self._sam_hover_box,
                    preserve_sam_state=True,
                )
                self._sam_hover_box = None
            except Exception as exc:
                QMessageBox.warning(self, "Box creation failed", str(exc))
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
        self._mouse_in_view = True
        previous_hovered_box = self.hovered_box
        previous_hover_handle_type = self._hover_handle_type

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
            hovered_item = None
            for uuid, enabled in self.enabled_observations.items():
                if enabled:
                    hov_box_item = self.observation_map[
                        uuid
                    ].observation.box_manager.get_box_hovered(event.pos())
                    if hov_box_item and (
                        hovered_item is None
                        or hov_box_item.area() < hovered_item.area()
                    ):
                        hovered_item = hov_box_item
            self.hovered_box = hovered_item.source if hovered_item else None

        self._hover_handle_type = self._drag_handle_hover_type(QPointF(event.pos()))

        self._maybe_update_hover_candidate(event)

        is_dragging = bool(
            self.resize_type
            or (event.buttons() & Qt.MouseButton.LeftButton and self.pt_1 is not None)
        )
        hover_changed = previous_hovered_box != self.hovered_box
        handle_changed = previous_hover_handle_type != self._hover_handle_type

        if is_dragging or hover_changed or handle_changed:
            self.redraw()
        else:
            self._update_mouse_overlay()

    def enterEvent(self, event: QEnterEvent) -> None:
        self._mouse_in_view = True
        self.redraw()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._mouse_in_view = False
        self._hover_handle_type = 0
        self._sam_hover_box = None
        self._sam_last_hover_point = None
        self.redraw()
        super().leaveEvent(event)

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
        self._invalidate_scaled_pixmap_cache()
        self.redraw()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Up:
            self.select_prev()
        elif event.key() == Qt.Key.Key_Down:
            self.select_next()
