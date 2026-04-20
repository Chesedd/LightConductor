"""QRunnable-based background UDP probe. Emits a signal with
(master_id, status) on completion."""
from __future__ import annotations

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal

from lightconductor.application.host_reachability import (
    PingStatus,
    ping_host,
)


class MasterPingSignals(QObject):
    """Separate QObject for signals because QRunnable itself is not a
    QObject. Instances of this class live on the main thread and emit
    from the worker thread via queued connection semantics."""
    completed = pyqtSignal(str, str)


class MasterPingWorker(QRunnable):
    """One-shot UDP reachability probe. Constructed with the info it
    needs; pushed onto QThreadPool by the caller. Does NOT own the
    QTimer - the caller schedules probes."""

    def __init__(
        self,
        master_id: str,
        host: str,
        port: int,
        timeout: float = 1.0,
    ):
        super().__init__()
        self.master_id = master_id
        self.host = host
        self.port = port
        self.timeout = timeout
        self.signals = MasterPingSignals()
        self.setAutoDelete(True)

    def run(self) -> None:
        status = ping_host(
            self.host, self.port, self.timeout,
        )
        self.signals.completed.emit(
            self.master_id, status.value,
        )
