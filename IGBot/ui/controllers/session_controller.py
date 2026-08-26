import logging
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from IGBot.core.device import DeviceRecord
from IGBot.core.phone_scheduler import PhoneScheduler
from IGBot.core.session_engine import SessionState

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class _SchedulerWorker(QRunnable):
    def __init__(self, scheduler, state_callback, account_callback, completed, failed):
        super().__init__()
        self.scheduler = scheduler
        self._state_callback = state_callback
        self._account_callback = account_callback
        self._completed = completed
        self._failed = failed

    def run(self) -> None:
        try:
            self.scheduler.start(self._state_callback, self._account_callback)
        except Exception as error:  # noqa: BLE001 - worker boundary
            self._failed(str(error))
        finally:
            self._completed()


class SessionController(QObject):
    """Coordinate one persistent scheduler worker per managed phone."""

    state_changed = Signal(str, str)
    account_state_changed = Signal(str, str)
    operation_failed = Signal(str)

    def __init__(self, workspace_root: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._workspace_root = workspace_root
        self._pool = QThreadPool.globalInstance()
        self._schedulers: dict[str, PhoneScheduler] = {}
        self._workers: set[_SchedulerWorker] = set()

    def state_for(self, serial: str) -> SessionState:
        scheduler = self._schedulers.get(serial)
        return scheduler.state if scheduler else SessionState.IDLE

    def start(self, device: DeviceRecord) -> None:
        serial = device.serial
        logger.info("Phone Scheduler start requested for %s", serial)
        existing = self._schedulers.get(serial)
        if existing and existing.state in {
            SessionState.STARTING,
            SessionState.RUNNING,
            SessionState.WAITING,
            SessionState.STOPPING,
        }:
            self.operation_failed.emit("This phone scheduler is already active.")
            return
        scheduler = PhoneScheduler(device, self._workspace_root)
        self._schedulers[serial] = scheduler
        holder = {}
        worker = _SchedulerWorker(
            scheduler,
            lambda state: self.state_changed.emit(serial, state.value),
            lambda username, state: self.account_state_changed.emit(
                username, state.value
            ),
            lambda: self._worker_finished(serial, holder["worker"]),
            self.operation_failed.emit,
        )
        holder["worker"] = worker
        self._workers.add(worker)
        self._pool.start(worker)

    def stop(self, serial: str) -> None:
        logger.info("Phone Scheduler stop requested for %s", serial)
        scheduler = self._schedulers.get(serial)
        if scheduler is None:
            self.operation_failed.emit("This phone scheduler is not running.")
            return
        try:
            scheduler.stop(lambda state: self.state_changed.emit(serial, state.value))
        except Exception as error:  # noqa: BLE001 - controller boundary
            self.operation_failed.emit(str(error))

    def stop_all(self) -> None:
        for serial, scheduler in tuple(self._schedulers.items()):
            if scheduler.state in {
                SessionState.STARTING,
                SessionState.RUNNING,
                SessionState.WAITING,
            }:
                try:
                    scheduler.stop(
                        lambda state, device_id=serial: self.state_changed.emit(
                            device_id, state.value
                        )
                    )
                except Exception:
                    logger.exception("Could not stop Phone Scheduler for %s", serial)

    def _worker_finished(self, serial: str, worker: _SchedulerWorker) -> None:
        self._workers.discard(worker)
        scheduler = self._schedulers.get(serial)
        if scheduler is not None and scheduler.state in {
            SessionState.STOPPED,
            SessionState.ERROR,
        }:
            self._schedulers.pop(serial, None)
