from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMainWindow, QSplitter, QStackedWidget

from IGBot.core.device import AssignedAccount, DeviceRecord
from IGBot.services.archive_service import ARCHIVED_ACCOUNTS
from IGBot.services.device_inventory_service import DeviceInventoryService
from IGBot.ui.controllers.device_controller import DeviceController
from IGBot.ui.pages.devices_page import DevicesPage
from IGBot.ui.pages.phone_accounts_page import PhoneAccountsPage
from IGBot.ui.widgets.confirmation_dialog import ConfirmationDialog
from IGBot.ui.widgets.error_dialog import ErrorDialog
from IGBot.ui.widgets.live_log_panel import LiveLogPanel
from IGBot.ui.widgets.navigation_sidebar import NavigationSidebar
from IGBot.ui.widgets.top_toolbar import TopToolbar
from IGBot.ui.widgets.transfer_account_dialog import TransferAccountDialog


class MainWindow(QMainWindow):
    """Top-level application shell for IGBot desktop."""

    def __init__(self, device_service: DeviceInventoryService | None = None) -> None:
        super().__init__()
        self.setObjectName("mainWindow")
        self.setWindowTitle("IGBot")
        self.resize(1440, 900)
        self.setMinimumSize(960, 640)
        self._managed_phone_serial: str | None = None

        service = device_service or DeviceInventoryService.for_workspace(Path.cwd())
        self.device_controller = DeviceController(service, self)
        self.sidebar = NavigationSidebar(self)
        self.toolbar = TopToolbar(self)
        self.pages = QStackedWidget(self)
        self.devices_page = DevicesPage(self.device_controller, self)
        self.phone_accounts_page = PhoneAccountsPage(self)
        self.live_log = LiveLogPanel(self)

        self._build_shell()
        self._connect_signals()
        self.device_controller.refresh()

    def _build_shell(self) -> None:
        self.addToolBar(Qt.TopToolBarArea, self.toolbar)

        self.pages.addWidget(self.devices_page)
        self.pages.addWidget(self.phone_accounts_page)

        content_splitter = QSplitter(Qt.Vertical, self)
        content_splitter.setObjectName("contentSplitter")
        content_splitter.addWidget(self.pages)
        content_splitter.addWidget(self.live_log)
        content_splitter.setSizes([710, 170])
        content_splitter.setStretchFactor(0, 4)
        content_splitter.setStretchFactor(1, 1)
        content_splitter.setChildrenCollapsible(False)

        shell = QSplitter(Qt.Horizontal, self)
        shell.setObjectName("shellSplitter")
        shell.addWidget(self.sidebar)
        shell.addWidget(content_splitter)
        shell.setSizes([190, 1250])
        shell.setStretchFactor(0, 0)
        shell.setStretchFactor(1, 1)
        shell.setCollapsible(0, False)
        shell.setChildrenCollapsible(False)
        self.setCentralWidget(shell)

        self.statusBar().showMessage("Ready")

    def _connect_signals(self) -> None:
        self.sidebar.page_selected.connect(self._navigate_to_page)
        self.toolbar.refresh_requested.connect(self.device_controller.refresh)
        self.device_controller.refresh_started.connect(
            lambda: self.statusBar().showMessage("Discovering Android devices…")
        )
        self.device_controller.refresh_started.connect(
            lambda: self.toolbar.set_refreshing(True)
        )
        self.device_controller.devices_changed.connect(self._show_device_count)
        self.device_controller.devices_changed.connect(
            lambda _: self.toolbar.set_refreshing(False)
        )
        self.device_controller.devices_changed.connect(self._sync_phone_accounts)
        self.device_controller.discovery_failed.connect(
            lambda message: self.statusBar().showMessage(message)
        )
        self.device_controller.discovery_failed.connect(
            lambda _: self.toolbar.set_refreshing(False)
        )
        self.device_controller.operation_failed.connect(
            lambda message: self.statusBar().showMessage(message)
        )
        self.device_controller.phone_accounts_requested.connect(
            self._open_phone_accounts
        )
        self.phone_accounts_page.back_requested.connect(self._open_devices)
        self.phone_accounts_page.rename_requested.connect(
            self.device_controller.rename_device
        )
        self.phone_accounts_page.folder_requested.connect(
            self.device_controller.open_device_folder
        )
        self.phone_accounts_page.delete_requested.connect(self._delete_managed_device)
        self.phone_accounts_page.transfer_requested.connect(self._show_transfer_dialog)
        self.phone_accounts_page.archive_requested.connect(self._show_archive_dialog)
        self.phone_accounts_page.restore_requested.connect(self._show_restore_dialog)
        self.phone_accounts_page.account_delete_requested.connect(
            self._show_delete_account_dialog
        )
        self.phone_accounts_page.account_folder_requested.connect(
            lambda directory: QDesktopServices.openUrl(QUrl.fromLocalFile(directory))
        )
        self.device_controller.device_folder_ready.connect(
            lambda directory: QDesktopServices.openUrl(QUrl.fromLocalFile(directory))
        )
        self.device_controller.archived_accounts_ready.connect(self._open_archived)
        self.device_controller.transfer_failed.connect(self._show_transfer_error)
        self.device_controller.archive_failed.connect(self._show_archive_error)
        self.device_controller.restore_failed.connect(self._show_restore_error)
        self.device_controller.account_deletion_failed.connect(
            self._show_delete_account_error
        )
        self.devices_page.notification_requested.connect(self.statusBar().showMessage)

    def _show_device_count(self, devices: list[DeviceRecord]) -> None:
        total = len(devices)
        connected = sum(device.connected for device in devices)
        self.statusBar().showMessage(f"{total} phones · {connected} connected")

    def _open_phone_accounts(
        self, device: DeviceRecord, accounts: list[AssignedAccount]
    ) -> None:
        self.phone_accounts_page.set_phone(device, accounts)
        self._managed_phone_serial = device.serial
        self.pages.setCurrentWidget(self.phone_accounts_page)
        self.toolbar.set_context_title("Phone accounts")
        self.statusBar().showMessage(f"Managing accounts for {device.serial}")

    def _open_devices(self) -> None:
        self._managed_phone_serial = None
        self.pages.setCurrentWidget(self.devices_page)
        self.toolbar.set_context_title("Device management")

    def _navigate_to_page(self, page_index: int) -> None:
        if page_index == 0:
            self._open_devices()
        elif page_index == 1:
            self.device_controller.load_archived_accounts()

    def _open_archived(self, accounts: list[AssignedAccount]) -> None:
        self._managed_phone_serial = None
        self.phone_accounts_page.set_archived(accounts)
        self.pages.setCurrentWidget(self.phone_accounts_page)
        self.toolbar.set_context_title("Archived accounts")

    def _delete_managed_device(self, serial: str) -> None:
        if self.devices_page._confirm_delete(serial):
            self.device_controller.delete_device(serial)

    def _show_transfer_dialog(self, username: str, source_serial: str) -> None:
        dialog = TransferAccountDialog(
            username,
            self.device_controller.managed_devices,
            source_serial,
            self,
        )
        if dialog.exec():
            self.device_controller.request_account_transfer(
                username, source_serial, dialog.destination_serial
            )

    def _show_transfer_error(self, message: str) -> None:
        ErrorDialog("Account Transfer Failed", message, self).exec()

    def _show_archive_dialog(self, username: str, source_serial: str) -> None:
        source = next(
            (
                device
                for device in self.device_controller.managed_devices
                if device.serial == source_serial
            ),
            None,
        )
        phone_name = source.phone_name or source.serial if source else source_serial
        confirmed = ConfirmationDialog.confirm(
            "Archive Account",
            username,
            f"This account will be removed from phone {phone_name} and moved to Archived.",
            self,
            confirm_text="Archive",
        )
        if confirmed:
            self.device_controller.request_account_archive(username, source_serial)

    def _show_archive_error(self, result) -> None:
        message = result.error if hasattr(result, "error") else str(result)
        ErrorDialog("Account Archive Failed", message, self).exec()

    def _show_restore_dialog(self, username: str) -> None:
        dialog = TransferAccountDialog(
            username,
            self.device_controller.managed_devices,
            ARCHIVED_ACCOUNTS,
            self,
            action_text="Restore",
        )
        if not dialog.exec():
            return

        destination_serial = dialog.destination_serial
        destination = next(
            (
                device
                for device in self.device_controller.managed_devices
                if device.serial == destination_serial
            ),
            None,
        )
        phone_name = (
            destination.phone_name or destination.serial
            if destination
            else destination_serial
        )
        confirmed = ConfirmationDialog.confirm(
            "Restore Account",
            username,
            f"This account will be restored from Archived to phone {phone_name}.",
            self,
            confirm_text="Restore",
        )
        if confirmed:
            self.device_controller.request_account_restore(username, destination_serial)

    def _show_restore_error(self, message: str) -> None:
        ErrorDialog("Account Restore Failed", message, self).exec()

    def _show_delete_account_dialog(self, username: str) -> None:
        confirmed = ConfirmationDialog.confirm(
            "Delete Account",
            username,
            "This account will be permanently deleted. This action cannot be undone.",
            self,
            confirm_text="Delete",
        )
        if confirmed:
            self.device_controller.delete_archived_account(username)

    def _show_delete_account_error(self, message: str) -> None:
        ErrorDialog("Account Deletion Failed", message, self).exec()

    def _sync_phone_accounts(self, devices: list[DeviceRecord]) -> None:
        if self._managed_phone_serial is None:
            return
        device = next(
            (item for item in devices if item.serial == self._managed_phone_serial),
            None,
        )
        if device is None:
            self._open_devices()
            return
        self.phone_accounts_page.set_phone(device, list(device.accounts))

    def closeEvent(self, event) -> None:
        self.live_log.detach_logging()
        super().closeEvent(event)
