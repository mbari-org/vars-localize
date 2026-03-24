"""Persistent application settings with typed accessors."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QSettings

from vars_localize.util.endpoints import DEFAULT_M3_URL


@dataclass(frozen=True)
class AppSettingsSnapshot:
    m3_url: str
    connection_timeout_secs: int
    search_page_size: int
    focus_search_shortcut: str
    clear_results_shortcut: str
    open_settings_shortcut: str
    sam3_enabled: bool
    sam3_model_path: str
    sam3_confidence: float
    sam3_image_size: int
    sam3_min_area: int
    sam3_overlap_iou: float


class AppSettings:
    ORG = "MBARI"
    APP = "VARSLocalize"

    KEY_M3_URL = "connection/m3_url"
    KEY_CONNECTION_TIMEOUT = "connection/check_timeout_secs"

    KEY_SEARCH_PAGE_SIZE = "search/page_size"

    KEY_SHORTCUT_FOCUS_SEARCH = "shortcuts/focus_search"
    KEY_SHORTCUT_CLEAR_RESULTS = "shortcuts/clear_results"
    KEY_SHORTCUT_OPEN_SETTINGS = "shortcuts/open_settings"

    KEY_SAM3_ENABLED = "ai/sam3_enabled"
    KEY_SAM3_MODEL_PATH = "ai/sam3_model_path"
    KEY_SAM3_CONFIDENCE = "ai/sam3_confidence"
    KEY_SAM3_IMAGE_SIZE = "ai/sam3_image_size"
    KEY_SAM3_MIN_AREA = "ai/sam3_min_area"
    KEY_SAM3_OVERLAP_IOU = "ai/sam3_overlap_iou"

    DEFAULT_CONNECTION_TIMEOUT = 3
    DEFAULT_SEARCH_PAGE_SIZE = 25

    DEFAULT_SHORTCUT_FOCUS_SEARCH = "Ctrl+F"
    DEFAULT_SHORTCUT_CLEAR_RESULTS = "Ctrl+L"
    DEFAULT_SHORTCUT_OPEN_SETTINGS = "Ctrl+,"

    DEFAULT_SAM3_ENABLED = False
    DEFAULT_SAM3_MODEL_PATH = ""
    DEFAULT_SAM3_CONFIDENCE = 0.35
    DEFAULT_SAM3_IMAGE_SIZE = 644
    DEFAULT_SAM3_MIN_AREA = 100
    DEFAULT_SAM3_OVERLAP_IOU = 0.2

    def __init__(self):
        self._settings = QSettings(self.ORG, self.APP)

    def snapshot(self) -> AppSettingsSnapshot:
        return AppSettingsSnapshot(
            m3_url=self.m3_url,
            connection_timeout_secs=self.connection_timeout_secs,
            search_page_size=self.search_page_size,
            focus_search_shortcut=self.focus_search_shortcut,
            clear_results_shortcut=self.clear_results_shortcut,
            open_settings_shortcut=self.open_settings_shortcut,
            sam3_enabled=self.sam3_enabled,
            sam3_model_path=self.sam3_model_path,
            sam3_confidence=self.sam3_confidence,
            sam3_image_size=self.sam3_image_size,
            sam3_min_area=self.sam3_min_area,
            sam3_overlap_iou=self.sam3_overlap_iou,
        )

    @property
    def m3_url(self) -> str:
        return str(
            self._settings.value(self.KEY_M3_URL, DEFAULT_M3_URL, type=str)
        ).strip()

    @m3_url.setter
    def m3_url(self, value: str):
        normalized = (value or "").strip().rstrip("/")
        self._settings.setValue(self.KEY_M3_URL, normalized or DEFAULT_M3_URL)

    @property
    def connection_timeout_secs(self) -> int:
        return max(
            1,
            int(
                self._settings.value(
                    self.KEY_CONNECTION_TIMEOUT,
                    self.DEFAULT_CONNECTION_TIMEOUT,
                    type=int,
                )
            ),
        )

    @connection_timeout_secs.setter
    def connection_timeout_secs(self, value: int):
        self._settings.setValue(self.KEY_CONNECTION_TIMEOUT, max(1, int(value)))

    @property
    def search_page_size(self) -> int:
        return max(
            1,
            int(
                self._settings.value(
                    self.KEY_SEARCH_PAGE_SIZE,
                    self.DEFAULT_SEARCH_PAGE_SIZE,
                    type=int,
                )
            ),
        )

    @search_page_size.setter
    def search_page_size(self, value: int):
        self._settings.setValue(self.KEY_SEARCH_PAGE_SIZE, max(1, int(value)))

    @property
    def focus_search_shortcut(self) -> str:
        return str(
            self._settings.value(
                self.KEY_SHORTCUT_FOCUS_SEARCH,
                self.DEFAULT_SHORTCUT_FOCUS_SEARCH,
                type=str,
            )
        ).strip()

    @focus_search_shortcut.setter
    def focus_search_shortcut(self, value: str):
        self._settings.setValue(
            self.KEY_SHORTCUT_FOCUS_SEARCH,
            (value or "").strip() or self.DEFAULT_SHORTCUT_FOCUS_SEARCH,
        )

    @property
    def clear_results_shortcut(self) -> str:
        return str(
            self._settings.value(
                self.KEY_SHORTCUT_CLEAR_RESULTS,
                self.DEFAULT_SHORTCUT_CLEAR_RESULTS,
                type=str,
            )
        ).strip()

    @clear_results_shortcut.setter
    def clear_results_shortcut(self, value: str):
        self._settings.setValue(
            self.KEY_SHORTCUT_CLEAR_RESULTS,
            (value or "").strip() or self.DEFAULT_SHORTCUT_CLEAR_RESULTS,
        )

    @property
    def open_settings_shortcut(self) -> str:
        return str(
            self._settings.value(
                self.KEY_SHORTCUT_OPEN_SETTINGS,
                self.DEFAULT_SHORTCUT_OPEN_SETTINGS,
                type=str,
            )
        ).strip()

    @open_settings_shortcut.setter
    def open_settings_shortcut(self, value: str):
        self._settings.setValue(
            self.KEY_SHORTCUT_OPEN_SETTINGS,
            (value or "").strip() or self.DEFAULT_SHORTCUT_OPEN_SETTINGS,
        )

    @property
    def sam3_enabled(self) -> bool:
        return bool(
            self._settings.value(
                self.KEY_SAM3_ENABLED,
                self.DEFAULT_SAM3_ENABLED,
                type=bool,
            )
        )

    @sam3_enabled.setter
    def sam3_enabled(self, value: bool):
        self._settings.setValue(self.KEY_SAM3_ENABLED, bool(value))

    @property
    def sam3_model_path(self) -> str:
        return str(
            self._settings.value(
                self.KEY_SAM3_MODEL_PATH,
                self.DEFAULT_SAM3_MODEL_PATH,
                type=str,
            )
        ).strip()

    @sam3_model_path.setter
    def sam3_model_path(self, value: str):
        self._settings.setValue(self.KEY_SAM3_MODEL_PATH, (value or "").strip())

    @property
    def sam3_confidence(self) -> float:
        return float(
            self._settings.value(
                self.KEY_SAM3_CONFIDENCE,
                self.DEFAULT_SAM3_CONFIDENCE,
                type=float,
            )
        )

    @sam3_confidence.setter
    def sam3_confidence(self, value: float):
        bounded = max(0.0, min(1.0, float(value)))
        self._settings.setValue(self.KEY_SAM3_CONFIDENCE, bounded)

    @property
    def sam3_image_size(self) -> int:
        return max(
            64,
            int(
                self._settings.value(
                    self.KEY_SAM3_IMAGE_SIZE,
                    self.DEFAULT_SAM3_IMAGE_SIZE,
                    type=int,
                )
            ),
        )

    @sam3_image_size.setter
    def sam3_image_size(self, value: int):
        self._settings.setValue(self.KEY_SAM3_IMAGE_SIZE, max(64, int(value)))

    @property
    def sam3_min_area(self) -> int:
        return max(
            1,
            int(
                self._settings.value(
                    self.KEY_SAM3_MIN_AREA,
                    self.DEFAULT_SAM3_MIN_AREA,
                    type=int,
                )
            ),
        )

    @sam3_min_area.setter
    def sam3_min_area(self, value: int):
        self._settings.setValue(self.KEY_SAM3_MIN_AREA, max(1, int(value)))

    @property
    def sam3_overlap_iou(self) -> float:
        value = float(
            self._settings.value(
                self.KEY_SAM3_OVERLAP_IOU,
                self.DEFAULT_SAM3_OVERLAP_IOU,
                type=float,
            )
        )
        return max(0.0, min(1.0, value))

    @sam3_overlap_iou.setter
    def sam3_overlap_iou(self, value: float):
        bounded = max(0.0, min(1.0, float(value)))
        self._settings.setValue(self.KEY_SAM3_OVERLAP_IOU, bounded)
