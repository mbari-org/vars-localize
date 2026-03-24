"""Centralized UI state for Qt widgets."""

from typing import List

from PyQt6.QtCore import QObject, pyqtSignal


class AppStateStore(QObject):
    """Shared state store with Qt signals for reactive UI updates."""

    observerChanged = pyqtSignal(str)
    observerRoleChanged = pyqtSignal(str)
    adminModeChanged = pyqtSignal(bool)
    conceptChanged = pyqtSignal(str)
    conceptsChanged = pyqtSignal(list)
    uuidsChanged = pyqtSignal(list)
    loadingChanged = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._observer = ""
        self._observer_role = ""
        self._admin_mode = False
        self._concept = ""
        self._concepts: List[str] = []
        self._uuids: List[str] = []
        self._loading = False

    @property
    def observer(self) -> str:
        return self._observer

    @observer.setter
    def observer(self, value: str):
        if value != self._observer:
            self._observer = value
            self.observerChanged.emit(value)

    @property
    def observer_role(self) -> str:
        return self._observer_role

    @observer_role.setter
    def observer_role(self, value: str):
        if value != self._observer_role:
            self._observer_role = value
            self.observerRoleChanged.emit(value)

    @property
    def admin_mode(self) -> bool:
        return self._admin_mode

    @admin_mode.setter
    def admin_mode(self, value: bool):
        if value != self._admin_mode:
            self._admin_mode = value
            self.adminModeChanged.emit(value)

    @property
    def concept(self) -> str:
        return self._concept

    @concept.setter
    def concept(self, value: str):
        if value != self._concept:
            self._concept = value
            self.conceptChanged.emit(value)

    @property
    def concepts(self) -> List[str]:
        return list(self._concepts)

    @concepts.setter
    def concepts(self, values: List[str]):
        normalized = list(values) if values else []
        if normalized != self._concepts:
            self._concepts = normalized
            self.conceptsChanged.emit(list(normalized))

    @property
    def uuids(self) -> List[str]:
        return list(self._uuids)

    @uuids.setter
    def uuids(self, values: List[str]):
        normalized = list(values) if values else []
        if normalized != self._uuids:
            self._uuids = normalized
            self.uuidsChanged.emit(list(normalized))

    @property
    def loading(self) -> bool:
        return self._loading

    @loading.setter
    def loading(self, value: bool):
        if value != self._loading:
            self._loading = value
            self.loadingChanged.emit(value)
