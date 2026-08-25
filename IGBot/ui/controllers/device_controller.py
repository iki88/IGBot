import logging
from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from IGBot.core.device import AssignedAccount, DeviceFleetSnapshot, DeviceRecord
from IGBot.services.device_inventory_service import DeviceInventoryService

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class _WorkerSignals(QObject):
    completed = Signal(object)
    failed = Signal(str)


class _ServiceTask(QRunnable):
    def __init__(self, operation: Callable[[], object]) -> None:
        super().__init__()
        self._operation = operation
        self.signals = _WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self._operation()
        except Exception as error:
            logger.exception("Device operation failed")
            self.signals.failed.emit(str(error))
            return
        self.signals.completed.emit(result)


class DeviceController(QObject):
    """Coordinates device inventory operations outside the UI thread."""

    refresh_started = Signal()
    devices_changed = Signal(list)
    discovery_failed = Signal(str)
    phone_accounts_requested = Signal(object, list)
    deletion_started = Signal(str)
    device_deleted = Signal(str)
    operation_failed = Signal(str)
    unmanaged_devices_ready = Signal(list)
    archived_accounts_ready = Signal(list)
    device_folder_ready = Signal(str)

    def __init__(
        self,
        service: DeviceInventoryService,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._thread_pool = QThreadPool.globalInstance()
        self._refreshing = False
        self._records: dict[str, DeviceRecord] = {}
        self._tasks: set[_ServiceTask] = set()

    @Slot()
    def refresh(self) -> None:
        if self._refreshing:
            return

        self._refreshing = True
        self.refresh_started.emit()
        logger.info("Refreshing the device inventory")

        task = _ServiceTask(self._service.refresh)
        task.signals.completed.connect(self._on_refresh_completed)
        task.signals.failed.connect(self._on_refresh_failed)
        self._start_task(task)

    @Slot(str)
    def open_phone_accounts(self, serial: str) -> None:
        record = self._records.get(serial)
        if record is None:
            self.operation_failed.emit(f"Device {serial} is not in the inventory")
            return
        accounts: list[AssignedAccount] = list(record.accounts)
        self.phone_accounts_requested.emit(record, accounts)

    @Slot(str)
    def delete_device(self, serial: str) -> None:
        if serial not in self._records:
            self.operation_failed.emit(f"Device {serial} is not in the inventory")
            return

        self.deletion_started.emit(serial)
        task = _ServiceTask(lambda: self._service.delete(serial))
        task.signals.completed.connect(lambda _: self._on_delete_completed(serial))
        task.signals.failed.connect(self._on_operation_failed)
        self._start_task(task)

    @Slot()
    def load_unmanaged_devices(self) -> None:
        task = _ServiceTask(self._service.unmanaged_devices)
        task.signals.completed.connect(
            lambda devices: self.unmanaged_devices_ready.emit(list(devices))
        )
        task.signals.failed.connect(self._on_operation_failed)
        self._start_task(task)

    @Slot(str, str)
    def add_device(self, serial: str, phone_name: str) -> None:
        self._run_and_refresh(lambda: self._service.add_device(serial, phone_name))

    @Slot(str, str)
    def rename_device(self, serial: str, phone_name: str) -> None:
        self._run_and_refresh(lambda: self._service.rename_device(serial, phone_name))

    @Slot(str)
    def open_device_folder(self, serial: str) -> None:
        task = _ServiceTask(lambda: self._service.device_directory(serial))
        task.signals.completed.connect(
            lambda directory: self.device_folder_ready.emit(str(directory))
        )
        task.signals.failed.connect(self._on_operation_failed)
        self._start_task(task)

    @Slot()
    def load_archived_accounts(self) -> None:
        task = _ServiceTask(self._service.archived_accounts)
        task.signals.completed.connect(
            lambda accounts: self.archived_accounts_ready.emit(list(accounts))
        )
        task.signals.failed.connect(self._on_operation_failed)
        self._start_task(task)

    def _run_and_refresh(self, operation: Callable[[], object]) -> None:
        task = _ServiceTask(operation)
        task.signals.completed.connect(lambda _: self.refresh())
        task.signals.failed.connect(self._on_operation_failed)
        self._start_task(task)

    def _start_task(self, task: _ServiceTask) -> None:
        self._tasks.add(task)
        task.signals.completed.connect(lambda _: self._release_task(task))
        task.signals.failed.connect(lambda _: self._release_task(task))
        self._thread_pool.start(task)

    def _release_task(self, task: _ServiceTask) -> None:
        self._tasks.discard(task)

    @Slot(object)
    def _on_refresh_completed(self, snapshot: DeviceFleetSnapshot) -> None:
        self._refreshing = False
        if snapshot.error:
            logger.error(snapshot.error)
            self.discovery_failed.emit(snapshot.error)
            return

        self._records = {record.serial: record for record in snapshot.devices}
        records = list(snapshot.devices)
        logger.info("Device inventory contains %d phone(s)", len(records))
        self.devices_changed.emit(records)

    @Slot(str)
    def _on_refresh_failed(self, message: str) -> None:
        self._refreshing = False
        self.discovery_failed.emit(message)

    def _on_delete_completed(self, serial: str) -> None:
        self._records.pop(serial, None)
        logger.info("Removed device %s from IGBot", serial)
        self.device_deleted.emit(serial)
        self.devices_changed.emit(list(self._records.values()))

    @Slot(str)
    def _on_operation_failed(self, message: str) -> None:
        self.operation_failed.emit(message)
