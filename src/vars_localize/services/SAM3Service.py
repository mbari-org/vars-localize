"""Local SAM3 integration helper with optional ultralytics dependency."""

from __future__ import annotations

import gc
import os
import threading
from typing import Any, Iterable, List, Optional, Sequence, Tuple, cast

from vars_localize.util.logging import get_logger

logger = get_logger("SAM3Service")


class SAM3Service:
    """Thin wrapper around ultralytics SAM3 semantic predictor.

    The class is import-safe when the optional sam extra is not installed.
    """

    def __init__(self, model_path: str, conf: float = 0.35, imgsz: int = 644):
        self._model = (model_path or "").strip()
        self._conf = conf
        self._imgsz = max(64, int(imgsz))
        self._device = "cpu"
        self._base_overrides = dict(
            conf=self._conf,
            task="segment",
            mode="predict",
            model=self._model,
            imgsz=self._imgsz,
            compile=False,
            save=False,
            verbose=False,
        )
        self._semantic_predictor = None
        self._point_predictor = None
        self._predictor_lock = threading.RLock()
        self._predictor_ready = False
        self._image_rgb = None
        self._semantic_features = None
        self._point_features = None
        self._src_shape = None
        self._import_error = None
        self._missing_dependency_reported = False
        self._semantic_mode_enabled = True
        self._point_mode_enabled = True

    def _validate_model_path(self) -> Optional[Exception]:
        if not self._model:
            return ValueError(
                "No SAM3 model path configured. Set the model path in Settings."
            )
        if not os.path.isfile(self._model):
            return FileNotFoundError(
                "SAM3 model file not found: {}".format(self._model)
            )
        return None

    def configure_runtime(
        self,
        model_path: Optional[str] = None,
        conf: Optional[float] = None,
        imgsz: Optional[int] = None,
    ):
        if model_path is not None:
            self._model = (model_path or "").strip()
        if conf is not None:
            self._conf = max(0.0, min(1.0, float(conf)))
        if imgsz is not None:
            self._imgsz = max(64, int(imgsz))

        self._base_overrides["model"] = self._model
        self._base_overrides["conf"] = self._conf
        self._base_overrides["imgsz"] = self._imgsz

        predictor = self._semantic_predictor
        point_predictor = self._point_predictor
        for predictor in (predictor, point_predictor):
            if predictor is None:
                continue
            try:
                args = getattr(predictor, "args", None)
                if args is not None:
                    setattr(args, "conf", self._conf)
                    setattr(args, "imgsz", self._imgsz)
                overrides = getattr(predictor, "overrides", None)
                if isinstance(overrides, dict):
                    overrides["conf"] = self._conf
                    overrides["imgsz"] = self._imgsz
            except Exception:
                # Best-effort update; predictor internals can vary by ultralytics version.
                pass

        if self.available:
            self._import_error = None
        else:
            self._import_error = self._validate_model_path()

    def ensure_loaded(
        self,
        semantic_enabled: bool = True,
        point_enabled: bool = True,
    ) -> None:
        with self._predictor_lock:
            semantic_enabled = bool(semantic_enabled)
            point_enabled = bool(point_enabled)
            if not semantic_enabled and not point_enabled:
                self._cleanup_predictors()
                self._semantic_mode_enabled = False
                self._point_mode_enabled = False
                self._import_error = None
                return

            if (
                self.available
                and self._semantic_mode_enabled == semantic_enabled
                and self._point_mode_enabled == point_enabled
            ):
                return

            validation_error = self._validate_model_path()
            if validation_error is not None:
                self._import_error = validation_error
                raise RuntimeError(str(validation_error)) from validation_error

            try:
                self._device = self._select_device()
                self._build_predictors(
                    self._device,
                    semantic_enabled=semantic_enabled,
                    point_enabled=point_enabled,
                )
                self._semantic_mode_enabled = semantic_enabled
                self._point_mode_enabled = point_enabled
                self._import_error = None
                return
            except ModuleNotFoundError as exc:
                self._import_error = exc
                # Optional dependency: app should continue with SAM disabled.
                if not self._missing_dependency_reported:
                    logger.info(
                        "Ultralytics SAM dependency is not installed; SAM assist is disabled."
                    )
                    self._missing_dependency_reported = True
                raise RuntimeError(
                    "Ultralytics SAM dependency is not installed; SAM assist is disabled."
                ) from exc
            except (
                Exception
            ) as exc:  # pragma: no cover - depends on optional install/runtime
                self._import_error = exc
                logger.exception("SAM3 predictor initialization failed: {}", exc)
                raise RuntimeError("SAM3 predictor initialization failed.") from exc

    def _build_predictors(
        self,
        device: str,
        semantic_enabled: bool = True,
        point_enabled: bool = True,
    ):
        from ultralytics.models.sam import SAM3Predictor, SAM3SemanticPredictor

        self._cleanup_predictors()
        overrides = self._make_overrides(device)

        if semantic_enabled:
            # Semantic predictor handles text grounding.
            self._semantic_predictor = SAM3SemanticPredictor(overrides=dict(overrides))
        if point_enabled:
            # Interactive predictor handles point prompts.
            self._point_predictor = SAM3Predictor(overrides=dict(overrides))
        self._predictor_ready = False
        self._device = device

    def _make_overrides(self, device: str) -> dict:
        overrides = dict(self._base_overrides)
        overrides["device"] = device
        return overrides

    def _cleanup_predictors(self):
        self._semantic_predictor = None
        self._point_predictor = None
        self._predictor_ready = False
        self._semantic_features = None
        self._point_features = None
        self._src_shape = None
        self._image_rgb = None
        gc.collect()
        try:
            import torch

            if bool(torch.cuda.is_available()):
                torch.cuda.empty_cache()
        except Exception:
            pass

    @staticmethod
    def _select_device() -> str:
        try:
            import torch

            if bool(torch.cuda.is_available()):
                return "0"
            if bool(torch.backends.mps.is_available()):
                return "mps"
        except ModuleNotFoundError:
            # Torch is optional in this app unless SAM extras are installed.
            return "cpu"
        except Exception as exc:
            logger.warning("Torch device probe failed, defaulting to CPU: {}", exc)

        return "cpu"

    def _recreate_predictor(
        self,
        device: str,
        semantic_enabled: Optional[bool] = None,
        point_enabled: Optional[bool] = None,
    ):
        self._cleanup_predictors()
        self._build_predictors(
            device,
            semantic_enabled=self._semantic_mode_enabled
            if semantic_enabled is None
            else bool(semantic_enabled),
            point_enabled=self._point_mode_enabled
            if point_enabled is None
            else bool(point_enabled),
        )

    @property
    def available(self) -> bool:
        return self.semantic_available or self.point_available

    @property
    def semantic_available(self) -> bool:
        return self._semantic_predictor is not None

    @property
    def point_available(self) -> bool:
        return self._point_predictor is not None

    @property
    def availability_error(self) -> Optional[str]:
        if self._import_error is None:
            return None
        return str(self._import_error)

    @property
    def point_predictor_loaded(self) -> bool:
        return self.point_available

    @property
    def point_predictor_ready(self) -> bool:
        return bool(self._predictor_ready)

    @property
    def point_predictor_init_failed(self) -> bool:
        return not self.point_available and self._import_error is not None

    @property
    def point_prompt_state(self) -> str:
        if not self.point_available:
            return "unavailable"
        if self._predictor_ready:
            return "ready"
        return "loading"

    def set_image(self, image_rgb, image_key: Optional[str] = None):
        with self._predictor_lock:
            if not self.available:
                raise RuntimeError("SAM3 service is unavailable")
            _ = image_key

            semantic_predictor = cast(Any, self._semantic_predictor)
            point_predictor = cast(Any, self._point_predictor)
            try:
                if semantic_predictor is not None:
                    semantic_predictor.set_image(image_rgb)
                if point_predictor is not None:
                    point_predictor.set_image(image_rgb)
            except Exception as exc:
                message = str(exc)
                if self._device != "cpu" and (
                    "Invalid CUDA" in message or "device=" in message
                ):
                    logger.warning(
                        "Device {} failed during set_image; retrying on CPU".format(
                            self._device
                        )
                    )
                    self._recreate_predictor("cpu")
                    semantic_predictor = cast(Any, self._semantic_predictor)
                    point_predictor = cast(Any, self._point_predictor)
                    if semantic_predictor is not None:
                        semantic_predictor.set_image(image_rgb)
                    if point_predictor is not None:
                        point_predictor.set_image(image_rgb)
                else:
                    raise

            self._predictor_ready = True
            self._image_rgb = image_rgb

            self._semantic_features = (
                semantic_predictor.features if semantic_predictor is not None else None
            )
            self._point_features = (
                point_predictor.features if point_predictor is not None else None
            )
            self._src_shape = image_rgb.shape[:2]
            if semantic_predictor is not None:
                self._reset_semantic_prompt_state(semantic_predictor)
                try:
                    self._prime_point_prompt_context(semantic_predictor)
                except Exception as exc:
                    logger.warning("Neutral point context init failed: {}", exc)

            # log(
            #     "[SAM3] set_image complete: src_shape={} feature_ready={}".format(
            #         self._src_shape,
            #         self._semantic_features is not None and self._point_features is not None,
            #     ),
            #     level=1,
            # )

    def _reset_semantic_prompt_state(self, predictor: Optional[Any] = None) -> bool:
        """Clear semantic/text state so point prompting stays prompt-independent."""
        changed = False

        active = predictor
        if active is None:
            active = self._semantic_predictor
        if active is None:
            return changed

        reset_prompts = getattr(active, "reset_prompts", None)
        if callable(reset_prompts):
            try:
                reset_prompts()
                changed = True
            except Exception as exc:
                logger.warning("reset_prompts failed: {}", exc)

        prompts = getattr(active, "prompts", None)
        if isinstance(prompts, dict):
            prompts.clear()
            changed = True

        return changed

    def query_text(self, text: str) -> List[Tuple[int, int, int, int]]:
        with self._predictor_lock:
            if not self.semantic_available:
                raise RuntimeError("SAM3 semantic mode is unavailable")
            if self._semantic_features is None or self._src_shape is None:
                return []
            if not text.strip():
                return []

            predictor = cast(Any, self._semantic_predictor)
            self._reset_semantic_prompt_state(predictor)
            try:
                masks, boxes = predictor.inference_features(
                    self._semantic_features,
                    src_shape=self._src_shape,
                    text=[text],
                )
            finally:
                self._reset_semantic_prompt_state(predictor)
                try:
                    self._prime_point_prompt_context(predictor)
                except Exception as exc:
                    logger.warning("Neutral point context reset failed: {}", exc)

            normalized = self._normalize_mask_boxes(masks)
            if normalized:
                return normalized
            return self._normalize_boxes(boxes)

    def query_point(self, x: int, y: int) -> List[Tuple[int, int, int, int]]:
        with self._predictor_lock:
            if not self.point_available:
                raise RuntimeError("SAM3 point mode is unavailable")
            if self._src_shape is None:
                logger.warning("query_point skipped: src_shape not ready")
                return []
            if self._image_rgb is None:
                logger.warning("query_point skipped: image not loaded")
                return []
            if self._point_features is None:
                logger.warning("query_point skipped: point features not ready")
                return []

            predictor = cast(Any, self._point_predictor)
            # log("[SAM3] query_point at ({}, {})".format(x, y), level=1)
            try:
                masks, boxes = predictor.inference_features(
                    self._point_features,
                    src_shape=self._src_shape,
                    points=[[x, y]],
                    labels=[1],
                    multimask_output=False,
                )
            except Exception as exc:
                logger.exception("Point query failed: {}", exc)
                return []

            normalized = self._normalize_mask_boxes(masks)
            if normalized:
                # log("[SAM3] query_point mask boxes: {}".format(len(normalized)), level=1)
                return normalized
            normalized_boxes = self._normalize_boxes(boxes)
            # log("[SAM3] query_point bbox boxes: {}".format(len(normalized_boxes)), level=1)
            return normalized_boxes

    @staticmethod
    def _normalize_mask_boxes(masks: object) -> List[Tuple[int, int, int, int]]:
        if masks is None:
            return []

        arr = cast(Any, masks)
        cpu_attr = getattr(arr, "cpu", None)
        if callable(cpu_attr):
            arr = cpu_attr()
        numpy_attr = getattr(arr, "numpy", None)
        if callable(numpy_attr):
            arr = numpy_attr()

        try:
            import numpy as np
        except Exception:
            return []

        np_arr = np.asarray(arr)
        if np_arr.ndim == 2:
            np_arr = np_arr[None, ...]
        elif np_arr.ndim != 3:
            return []

        normalized: List[Tuple[int, int, int, int]] = []
        for mask in np_arr:
            ys, xs = np.where(mask > 0)
            if xs.size == 0 or ys.size == 0:
                continue

            x1 = int(xs.min())
            y1 = int(ys.min())
            x2 = int(xs.max())
            y2 = int(ys.max())

            w = x2 - x1 + 1
            h = y2 - y1 + 1
            if w <= 1 or h <= 1:
                continue
            normalized.append((x1, y1, w, h))

        return normalized

    @staticmethod
    def _normalize_boxes(boxes: object) -> List[Tuple[int, int, int, int]]:
        if boxes is None:
            return []

        arr = cast(Any, boxes)
        cpu_attr = getattr(arr, "cpu", None)
        if callable(cpu_attr):
            arr = cpu_attr()
        numpy_attr = getattr(arr, "numpy", None)
        if callable(numpy_attr):
            arr = numpy_attr()

        tolist_attr = getattr(arr, "tolist", None)
        if callable(tolist_attr):
            rows = tolist_attr()
        else:
            rows = arr

        if not isinstance(rows, Iterable):
            return []

        normalized: List[Tuple[int, int, int, int]] = []
        for row in rows:
            if not isinstance(row, Sequence) or len(row) < 4:
                continue
            x1 = int(round(float(row[0])))
            y1 = int(round(float(row[1])))
            x2 = int(round(float(row[2])))
            y2 = int(round(float(row[3])))

            x = min(x1, x2)
            y = min(y1, y2)
            w = abs(x2 - x1)
            h = abs(y2 - y1)
            if w <= 1 or h <= 1:
                continue
            normalized.append((x, y, w, h))
        return normalized

    @staticmethod
    def _prime_point_prompt_context(predictor: Any):
        """Ensure point prompting has a neutral language context in SAM3."""
        model = getattr(predictor, "model", None)
        if model is None:
            return

        set_classes = getattr(model, "set_classes", None)
        if callable(set_classes):
            # SAM3 grounding can require language features even for point prompts.
            set_classes(text=["visual"])
