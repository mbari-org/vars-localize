"""Qt helpers for running blocking tasks off the UI thread."""

import traceback
from typing import Callable, Optional

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal, pyqtSlot


class WorkerSignals(QObject):
    result = pyqtSignal(object)
    error = pyqtSignal(str)
    finished = pyqtSignal()


class Worker(QRunnable):
    def __init__(self, fn: Callable, *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs
        self.signals = WorkerSignals()

    @pyqtSlot()
    def run(self):
        try:
            result = self._fn(*self._args, **self._kwargs)
            self.signals.result.emit(result)
        except Exception:
            self.signals.error.emit(traceback.format_exc())
        finally:
            self.signals.finished.emit()


def run_async(
    owner,
    fn: Callable,
    *args,
    on_result: Optional[Callable] = None,
    on_error: Optional[Callable] = None,
    on_finished: Optional[Callable] = None,
    thread_pool: Optional[QThreadPool] = None,
    **kwargs,
):
    """Run a function in the global QThreadPool with optional callbacks."""
    worker = Worker(fn, *args, **kwargs)

    if on_result is not None:
        worker.signals.result.connect(on_result)
    if on_error is not None:
        worker.signals.error.connect(on_error)
    if on_finished is not None:
        worker.signals.finished.connect(on_finished)

    # Keep references on owner to prevent early GC while running.
    if not hasattr(owner, "_active_workers"):
        owner._active_workers = set()

    owner._active_workers.add(worker)

    def _cleanup():
        owner._active_workers.discard(worker)

    worker.signals.finished.connect(_cleanup)
    pool = thread_pool if thread_pool is not None else QThreadPool.globalInstance()
    if pool is None:
        worker.run()
        return

    pool.start(worker)
