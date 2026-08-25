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
    account_transfer_requested = Signal(str, str, str)
    transfer_failed = Signal(str)
    archive_completed = Signal(object)
    archive_failed = Signal(object)
    restore_failed = Signal(str)
    restore_completed = Signal(object)
    account_deletion_failed = Signal(str)
    archived_account_deleted = Signal(object)
    account_created = Signal(object)
    account_creation_failed = Signal(str)
    account_configuration_ready = Signal(object, object)
    account_configuration_saved = Signal(object)
    account_configuration_failed = Signal(str)

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

    @Slot(str, str, str)
    def add_account(self, username: str, password: str, serial: str) -> None:
        task = _ServiceTask(
            lambda: self._service.add_account(username, password, serial)
        )
        task.signals.completed.connect(self._on_account_created)
        task.signals.failed.connect(self.account_creation_failed)
        self._start_task(task)

    @Slot(object)
    def _on_account_created(self, account: AssignedAccount) -> None:
        destination = self._records.get(account.device_id)
        phone_name = (
            destination.phone_name or destination.serial
            if destination
            else account.device_id
        )
        logger.info("Added account %s to %s", account.username, phone_name)
        self.account_created.emit(account)
        self.refresh()

    def load_account_configuration(self, account: AssignedAccount) -> None:
        task = _ServiceTask(lambda: self._service.account_configuration(account))
        task.signals.completed.connect(
            lambda configuration: self.account_configuration_ready.emit(
                account, configuration
            )
        )
        task.signals.failed.connect(self.account_configuration_failed)
        self._start_task(task)

    def save_account_configuration(
        self, account: AssignedAccount, username: str, password: str, app_id: str
    ) -> None:
        task = _ServiceTask(
            lambda: self._service.update_account_configuration(
                account, username, password, app_id
            )
        )
        task.signals.completed.connect(self._on_account_configuration_saved)
        task.signals.failed.connect(self.account_configuration_failed)
        self._start_task(task)

    def _on_account_configuration_saved(self, account: AssignedAccount) -> None:
        logger.info("Saved account configuration for %s", account.username)
        self.account_configuration_saved.emit(account)
        self.refresh()

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

    @property
    def managed_devices(self) -> list[DeviceRecord]:
        return list(self._records.values())

    @Slot(str, str, str)
    def request_account_transfer(
        self, username: str, source_serial: str, destination_serial: str
    ) -> None:
        self.account_transfer_requested.emit(
            username, source_serial, destination_serial
        )
        managed_serials = set(self._records)
        source = self._records.get(source_serial)
        destination = self._records.get(destination_serial)
        task = _ServiceTask(
            lambda: self._service.transfer_service.transfer(
                username, source_serial, destination_serial, managed_serials
            )
        )
        task.signals.completed.connect(
            lambda _: self._on_transfer_completed(username, source, destination)
        )
        task.signals.failed.connect(self.transfer_failed)
        self._start_task(task)

    def _on_transfer_completed(self, username: str, source, destination) -> None:
        source_name = source.phone_name or source.serial if source else "Unknown"
        destination_name = (
            destination.phone_name or destination.serial if destination else "Unknown"
        )
        logger.info(
            "Transferred account %s: %s → %s", username, source_name, destination_name
        )
        self.refresh()

    @Slot(str, str)
    def request_account_archive(self, username: str, source_serial: str) -> None:
        task = _ServiceTask(
            lambda: self._service.archive_service.archive(username, source_serial)
        )
        task.signals.completed.connect(self._on_archive_completed)
        task.signals.failed.connect(self._on_archive_task_failed)
        self._start_task(task)

    @Slot(object)
    def _on_archive_completed(self, result) -> None:
        if result.valid:
            source = self._records.get(result.source_serial)
            source_name = (
                source.phone_name or source.serial if source else result.source_serial
            )
            logger.info(
                "Archived account %s: %s → Archived", result.username, source_name
            )
            self.archive_completed.emit(result)
            self.refresh()
        else:
            self.archive_failed.emit(result)

    @Slot(str)
    def _on_archive_task_failed(self, message: str) -> None:
        self.archive_failed.emit(message)

    @Slot(str, str)
    def request_account_restore(self, username: str, destination_serial: str) -> None:
        managed_serials = set(self._records)
        task = _ServiceTask(
            lambda: self._service.archive_service.restore(
                username, destination_serial, managed_serials
            )
        )
        task.signals.completed.connect(self._on_restore_completed)
        task.signals.failed.connect(self.restore_failed)
        self._start_task(task)

    @Slot(object)
    def _on_restore_completed(self, result) -> None:
        if not result.valid:
            self.restore_failed.emit(result.error or "Account restoration failed.")
            return

        destination = self._records.get(result.destination_serial)
        destination_name = (
            destination.phone_name or destination.serial
            if destination
            else result.destination_serial
        )
        logger.info(
            "Restored account %s: Archived → %s", result.username, destination_name
        )
        self.restore_completed.emit(result)
        self.refresh()
        self.load_archived_accounts()

    @Slot(str)
    def delete_archived_account(self, username: str) -> None:
        task = _ServiceTask(
            lambda: self._service.archive_service.delete_archived(username)
        )
        task.signals.completed.connect(self._on_archived_account_deleted)
        task.signals.failed.connect(self.account_deletion_failed)
        self._start_task(task)

    @Slot(object)
    def _on_archived_account_deleted(self, result) -> None:
        if not result.valid:
            self.account_deletion_failed.emit(
                result.error or "Archived account deletion failed."
            )
            return

        logger.info("Deleted archived account %s: Archived → Deleted", result.username)
        self.archived_account_deleted.emit(result)
        self.refresh()
        self.load_archived_accounts()

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
