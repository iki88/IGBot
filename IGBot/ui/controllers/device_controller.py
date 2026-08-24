import logging

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from IGBot.core.phone_manager import DeviceDiscoveryResult, PhoneManager

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class _DiscoverySignals(QObject):
    completed = Signal(object)


class _DiscoveryTask(QRunnable):
    def __init__(self) -> None:
        super().__init__()
        self.signals = _DiscoverySignals()

    @Slot()
    def run(self) -> None:
        self.signals.completed.emit(PhoneManager.discover_devices())


class DeviceController(QObject):
    """Coordinates non-blocking device discovery for desktop views."""

    refresh_started = Signal()
    devices_changed = Signal(list)
    discovery_failed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread_pool = QThreadPool.globalInstance()
        self._refreshing = False
        self._active_task: _DiscoveryTask | None = None

    @Slot()
    def refresh(self) -> None:
        if self._refreshing:
            return

        self._refreshing = True
        self.refresh_started.emit()
        logger.info("Discovering connected Android devices")

        task = _DiscoveryTask()
        task.signals.completed.connect(self._on_discovery_completed)
        self._active_task = task
        self._thread_pool.start(task)

    @Slot(object)
    def _on_discovery_completed(self, result: DeviceDiscoveryResult) -> None:
        self._refreshing = False
        self._active_task = None

        if result.error:
            logger.error(result.error)
            self.discovery_failed.emit(result.error)
            return

        logger.info("Found %d connected Android device(s)", len(result.devices))
        self.devices_changed.emit(result.devices)
