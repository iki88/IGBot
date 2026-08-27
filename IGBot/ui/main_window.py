import logging
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QMainWindow, QSplitter, QStackedWidget

from IGBot.core.device import AssignedAccount, DeviceRecord
from IGBot.core.session_engine import SessionState
from IGBot.services.archive_service import ARCHIVED_ACCOUNTS
from IGBot.services.device_inventory_service import DeviceInventoryService
from IGBot.ui.controllers.device_controller import DeviceController
from IGBot.ui.controllers.session_controller import SessionController
from IGBot.ui.pages.account_page import AccountPage
from IGBot.ui.pages.activity_log_page import ActivityLogPage
from IGBot.ui.pages.devices_page import DevicesPage
from IGBot.ui.pages.global_settings_page import GlobalSettingsPage
from IGBot.ui.pages.phone_accounts_page import PhoneAccountsPage
from IGBot.ui.pages.templates_page import TemplatesPage
from IGBot.ui.widgets.add_account_dialog import AddAccountDialog
from IGBot.ui.widgets.confirmation_dialog import ConfirmationDialog
from IGBot.ui.widgets.error_dialog import ErrorDialog
from IGBot.ui.widgets.live_log_panel import LiveLogPanel
from IGBot.ui.widgets.navigation_sidebar import NavigationSidebar
from IGBot.ui.widgets.package_selection_dialog import PackageSelectionDialog
from IGBot.ui.widgets.template_editor_dialog import TemplateEditorDialog
from IGBot.ui.widgets.template_selection_dialog import TemplateSelectionDialog
from IGBot.ui.widgets.text_input_dialog import TextInputDialog
from IGBot.ui.widgets.top_toolbar import TopToolbar
from IGBot.ui.widgets.transfer_account_dialog import TransferAccountDialog

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class MainWindow(QMainWindow):
    """Top-level application shell for IGBot desktop."""

    def __init__(self, device_service: DeviceInventoryService | None = None) -> None:
        super().__init__()
        self.setObjectName("mainWindow")
        self.setWindowTitle("IGBot")
        self.resize(1440, 900)
        self.setMinimumSize(960, 640)
        self._managed_phone_serial: str | None = None
        self._workspace_context = "devices"
        self._account_return_context = "devices"
        self._templates = ()

        service = device_service or DeviceInventoryService.for_workspace(Path.cwd())
        self.device_controller = DeviceController(service, self)
        self.session_controller = SessionController(
            getattr(service, "workspace_root", Path.cwd()), self
        )
        self.sidebar = NavigationSidebar(self)
        self.toolbar = TopToolbar(self)
        self.pages = QStackedWidget(self)
        self.devices_page = DevicesPage(self.device_controller, self)
        self.phone_accounts_page = PhoneAccountsPage(self)
        self.live_log = LiveLogPanel(self)
        self.account_page = AccountPage(self)
        self.activity_log_page = ActivityLogPage(self.live_log, self)
        self.global_settings_page = GlobalSettingsPage(Path.cwd(), self)
        self.templates_page = TemplatesPage(self)
        self.devices_page.add_device_button.hide()

        self._build_shell()
        self._connect_signals()
        self.device_controller.refresh()
        self.device_controller.load_templates()

    def _build_shell(self) -> None:
        self.addToolBar(Qt.TopToolBarArea, self.toolbar)

        self.pages.addWidget(self.devices_page)
        self.pages.addWidget(self.phone_accounts_page)
        self.pages.addWidget(self.account_page)
        self.pages.addWidget(self.activity_log_page)
        self.pages.addWidget(self.global_settings_page)
        self.pages.addWidget(self.templates_page)

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
        self.toolbar.add_device_requested.connect(self.devices_page._show_add_device)
        self.toolbar.add_account_requested.connect(self._show_add_account_dialog)
        self.toolbar.save_requested.connect(self._save_account_configuration)
        self.toolbar.view_phone_requested.connect(self._view_phone)
        self.toolbar.start_requested.connect(self._start_phone_scheduler)
        self.toolbar.stop_requested.connect(self._stop_phone_scheduler)
        self.devices_page.runtime_start_requested.connect(self._start_device_accounts)
        self.phone_accounts_page.active_account_changed.connect(
            self._update_runtime_toolbar
        )
        self.session_controller.state_changed.connect(self._runtime_state_changed)
        self.session_controller.account_state_changed.connect(
            self._account_runtime_state_changed
        )
        self.session_controller.operation_failed.connect(self._show_runtime_error)
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
        self.device_controller.devices_changed.connect(self._sync_global_accounts)
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
        self.phone_accounts_page.account_open_requested.connect(self._open_account)
        self.account_page.back_requested.connect(self._return_from_account)
        self.account_page.dirty_changed.connect(self._set_account_dirty)
        self.account_page.package_detection_requested.connect(
            self._detect_foreground_package
        )
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
        self.phone_accounts_page.apply_template_requested.connect(
            self._show_apply_template_dialog
        )
        self.device_controller.device_folder_ready.connect(
            lambda directory: QDesktopServices.openUrl(QUrl.fromLocalFile(directory))
        )
        self.device_controller.archived_accounts_ready.connect(self._open_archived)
        self.device_controller.transfer_failed.connect(self._show_transfer_error)
        self.device_controller.archive_failed.connect(self._show_archive_error)
        self.device_controller.archive_completed.connect(
            self._return_after_account_action
        )
        self.device_controller.restore_failed.connect(self._show_restore_error)
        self.device_controller.restore_completed.connect(
            self._return_after_account_action
        )
        self.device_controller.account_deletion_failed.connect(
            self._show_delete_account_error
        )
        self.device_controller.archived_account_deleted.connect(
            self._return_after_account_action
        )
        self.device_controller.account_creation_failed.connect(
            self._show_add_account_error
        )
        self.device_controller.account_configuration_ready.connect(
            self._show_account_configuration
        )
        self.device_controller.account_configuration_saved.connect(
            self._on_account_configuration_saved
        )
        self.device_controller.account_configuration_failed.connect(
            self._show_account_configuration_error
        )
        self.device_controller.installed_packages_ready.connect(
            self._show_package_selection
        )
        self.device_controller.installed_packages_failed.connect(
            self._show_account_configuration_error
        )
        self.device_controller.foreground_package_ready.connect(
            self.account_page.set_application_id
        )
        self.device_controller.foreground_package_failed.connect(
            self._show_account_configuration_error
        )
        self.device_controller.phone_view_failed.connect(self._show_phone_view_error)
        self.device_controller.phone_view_ready.connect(
            lambda result: self.statusBar().showMessage(
                ("Phone view already open." if result.reused else "Phone view opened."),
                3000,
            )
        )
        self.devices_page.notification_requested.connect(self.statusBar().showMessage)
        self.device_controller.templates_changed.connect(self._templates_changed)
        self.device_controller.template_configuration_ready.connect(
            self._edit_template_configuration
        )
        self.device_controller.template_operation_failed.connect(
            self._show_template_error
        )
        self.device_controller.template_applied.connect(self._on_template_applied)
        self.templates_page.create_requested.connect(self._create_template)
        self.templates_page.edit_requested.connect(
            self.device_controller.load_template_configuration
        )
        self.templates_page.rename_requested.connect(self._rename_template)
        self.templates_page.delete_requested.connect(self._delete_template)

    def _show_device_count(self, devices: list[DeviceRecord]) -> None:
        total = len(devices)
        connected = sum(device.connected for device in devices)
        self.statusBar().showMessage(f"{total} phones · {connected} connected")

    def _view_phone(self) -> None:
        if self._workspace_context == "phone" and self._managed_phone_serial:
            serials = (self._managed_phone_serial,)
        elif self._workspace_context == "devices":
            serials = self.devices_page.selected_device_serials()
        else:
            serials = ()
        if len(serials) != 1:
            self._show_phone_view_error(
                "Select exactly one managed phone before viewing it."
            )
            return
        self.device_controller.view_phone(serials[0])

    def _show_phone_view_error(self, message: str) -> None:
        ErrorDialog("View Phone", message, self).exec()

    def _start_phone_scheduler(self) -> None:
        logger.info("Start clicked in Phone workspace")
        if not self._managed_phone_serial:
            self._report_runtime_error("No managed phone is open.")
            return
        device = next(
            (
                item
                for item in self.device_controller.managed_devices
                if item.serial == self._managed_phone_serial
            ),
            None,
        )
        if device is None:
            self._report_runtime_error(
                "The open phone is not in the managed inventory."
            )
            return
        self.session_controller.start(device)

    def _start_device_accounts(self, serial: str) -> None:
        logger.info("Start clicked for phone %s", serial)
        device = next(
            (
                item
                for item in self.device_controller.managed_devices
                if item.serial == serial
            ),
            None,
        )
        if device is None:
            self._report_runtime_error(
                "The selected phone is not in the managed inventory."
            )
            return
        self.session_controller.start(device)

    def _stop_phone_scheduler(self) -> None:
        logger.info("Stop clicked in Phone workspace")
        if not self._managed_phone_serial:
            self._report_runtime_error("No managed phone is open.")
            return
        self.session_controller.stop(self._managed_phone_serial)

    def _update_runtime_toolbar(self, account) -> None:
        if self._workspace_context != "phone" or not self._managed_phone_serial:
            self.toolbar.set_runtime_controls(False, False)
            return
        state = self.session_controller.state_for(self._managed_phone_serial)
        self.toolbar.set_runtime_controls(
            state in {SessionState.IDLE, SessionState.STOPPED, SessionState.ERROR},
            state
            in {SessionState.STARTING, SessionState.RUNNING, SessionState.WAITING},
        )

    def _runtime_state_changed(self, serial: str, status: str) -> None:
        self._update_runtime_toolbar(None)
        self.statusBar().showMessage(f"{serial}: {status}", 3000)

    def _account_runtime_state_changed(self, username: str, status: str) -> None:
        self.phone_accounts_page.set_runtime_status(username, status)
        self.statusBar().showMessage(f"{username}: {status}", 3000)

    def _show_runtime_error(self, message: str) -> None:
        ErrorDialog("Account Runtime", message, self).exec()

    def _report_runtime_error(self, message: str) -> None:
        logger.error("Account runtime validation failed: %s", message)
        self._show_runtime_error(message)

    def _open_phone_accounts(
        self, device: DeviceRecord, accounts: list[AssignedAccount]
    ) -> None:
        self.phone_accounts_page.set_phone(device, accounts)
        self.phone_accounts_page.options_button.hide()
        self._managed_phone_serial = device.serial
        self._workspace_context = "phone"
        self.pages.setCurrentWidget(self.phone_accounts_page)
        self.toolbar.set_context_title("Phone accounts")
        self.toolbar.set_context("phone", self.phone_accounts_page.options_menu)
        self._update_runtime_toolbar(None)
        self.live_log.show()
        self.statusBar().showMessage(f"Managing accounts for {device.serial}")

    def _open_devices(self) -> None:
        self._managed_phone_serial = None
        self._workspace_context = "devices"
        self.pages.setCurrentWidget(self.devices_page)
        self.toolbar.set_context_title("Device management")
        self.toolbar.set_context("devices")
        self.live_log.show()

    def _navigate_to_page(self, page_index: int) -> None:
        if page_index == 0:
            self._open_devices()
        elif page_index == 1:
            self._open_accounts()
        elif page_index == 2:
            self.device_controller.load_archived_accounts()
        elif page_index == 3:
            self._open_activity_log()
        elif page_index == 4:
            self._open_templates()
        elif page_index == 5:
            self._open_global_settings()

    def _open_accounts(self) -> None:
        self._managed_phone_serial = None
        self._workspace_context = "accounts"
        accounts = [
            account
            for device in self.device_controller.managed_devices
            for account in device.accounts
        ]
        self.phone_accounts_page.set_all_accounts(accounts)
        self.pages.setCurrentWidget(self.phone_accounts_page)
        self.toolbar.set_context_title("All accounts")
        self.toolbar.set_context("accounts")
        self.live_log.show()

    def _open_archived(self, accounts: list[AssignedAccount]) -> None:
        self._managed_phone_serial = None
        self._workspace_context = "archived"
        self.phone_accounts_page.set_archived(accounts)
        self.pages.setCurrentWidget(self.phone_accounts_page)
        self.toolbar.set_context_title("Archived accounts")
        self.toolbar.set_context("archived")
        self.live_log.show()

    def _open_account(self, account: AssignedAccount) -> None:
        self._account_return_context = self._workspace_context
        device = next(
            (
                item
                for item in self.device_controller.managed_devices
                if item.serial == account.device_id
            ),
            None,
        )
        phone_name = device.phone_name if device else ""
        self.account_page.set_account(account, phone_name)
        if hasattr(self.device_controller._service, "account_configuration"):
            self.device_controller.load_account_configuration(account)
        self.pages.setCurrentWidget(self.account_page)
        self.toolbar.set_context_title(account.username)
        self.toolbar.set_context(
            "account", self.phone_accounts_page.build_account_options(account)
        )
        self.live_log.show()

    def _show_account_configuration(self, account, configuration) -> None:
        current = self.account_page.account
        if current is not None and current.config_path == account.config_path:
            self.account_page.set_configuration(configuration)

    def _save_account_configuration(self) -> None:
        account = self.account_page.account
        if account is not None:
            try:
                settings = self.account_page.configuration_values()
            except ValueError as error:
                self._show_account_configuration_error(str(error))
                return
            self.device_controller.save_account_configuration(
                account,
                self.account_page.username.text(),
                self.account_page.password.text(),
                self.account_page.application_id.text(),
                settings,
            )

    def _on_account_configuration_saved(self, account) -> None:
        current = self.account_page.account
        if current is not None:
            self.account_page.account = account
            self.account_page.page_header.title.setText(account.username)
            self.toolbar.set_context_title(account.username)
            self.toolbar.set_context(
                "account", self.phone_accounts_page.build_account_options(account)
            )
            self.account_page.mark_clean()
            self.statusBar().showMessage("Account changes saved.", 3000)

    def _set_account_dirty(self, dirty: bool) -> None:
        account = self.account_page.account
        if account is not None:
            suffix = " *" if dirty else ""
            self.account_page.page_header.title.setText(account.username + suffix)

    def _load_installed_packages(self) -> None:
        account = self.account_page.account
        if account is not None:
            self.device_controller.load_installed_packages(account.device_id)

    def _detect_foreground_package(self) -> None:
        account = self.account_page.account
        if account is not None:
            self.device_controller.detect_foreground_package(account.device_id)

    def _show_package_selection(self, packages: list[str]) -> None:
        dialog = PackageSelectionDialog(packages, self)
        if dialog.exec() == QDialog.Accepted and dialog.selected_package:
            self.account_page.set_application_id(dialog.selected_package)

    def _show_account_configuration_error(self, message: str) -> None:
        ErrorDialog("Account Configuration Error", message, self).exec()

    def _return_from_account(self) -> None:
        if self._account_return_context == "archived":
            self.device_controller.load_archived_accounts()
        elif self._account_return_context == "accounts":
            self._open_accounts()
        elif self._managed_phone_serial:
            self.device_controller.open_phone_accounts(self._managed_phone_serial)
        else:
            self._open_devices()

    def _return_after_account_action(self, result) -> None:
        if self.pages.currentWidget() is self.account_page:
            self._return_from_account()

    def _open_activity_log(self) -> None:
        self._managed_phone_serial = None
        self._workspace_context = "activity"
        self.pages.setCurrentWidget(self.activity_log_page)
        self.toolbar.set_context_title("Activity log")
        self.toolbar.set_context("activity")
        self.live_log.hide()

    def _open_global_settings(self) -> None:
        self._managed_phone_serial = None
        self._workspace_context = "settings"
        self.pages.setCurrentWidget(self.global_settings_page)
        self.toolbar.set_context_title("Global settings")
        self.toolbar.set_context("settings")
        self.live_log.show()

    def _open_templates(self) -> None:
        self._managed_phone_serial = None
        self._workspace_context = "templates"
        self.pages.setCurrentWidget(self.templates_page)
        self.toolbar.set_context_title("Account templates")
        self.toolbar.set_context("templates")
        self.live_log.show()
        self.device_controller.load_templates()

    def _templates_changed(self, templates) -> None:
        self._templates = tuple(templates)
        self.templates_page.set_templates(self._templates)

    def _create_template(self) -> None:
        name, accepted = TextInputDialog.get_text(
            "Create Template", "Template name", "", self
        )
        if accepted:
            self.device_controller.create_template(name)

    def _rename_template(self, name: str) -> None:
        new_name, accepted = TextInputDialog.get_text(
            "Rename Template", "Template name", name, self
        )
        if accepted:
            self.device_controller.rename_template(name, new_name)

    def _delete_template(self, name: str) -> None:
        if ConfirmationDialog.confirm(
            "Delete Template",
            name,
            "This deletes only the template. Existing accounts are not changed.",
            self,
        ):
            self.device_controller.delete_template(name)

    def _edit_template_configuration(self, name: str, values: dict) -> None:
        dialog = TemplateEditorDialog(name, values, self)
        dialog.save_requested.connect(
            lambda configuration: self.device_controller.save_template(
                name, configuration
            )
        )

        def saved(saved_name: str) -> None:
            if saved_name == name:
                dialog.save_succeeded()

        dialog_error = lambda message: dialog.save_failed(message)
        self.device_controller.template_saved.connect(saved)
        self.device_controller.template_operation_failed.connect(dialog_error)
        try:
            dialog.exec()
        finally:
            self.device_controller.template_saved.disconnect(saved)
            self.device_controller.template_operation_failed.disconnect(dialog_error)

    def _show_template_error(self, message: str) -> None:
        ErrorDialog("Account Template", message, self).exec()

    def _show_apply_template_dialog(self, account: AssignedAccount) -> None:
        dialog = TemplateSelectionDialog(
            tuple(template.name for template in self._templates), self
        )
        if dialog.exec() == QDialog.Accepted:
            self.device_controller.apply_template(dialog.selected_template(), account)

    def _on_template_applied(self, account: AssignedAccount) -> None:
        if self.account_page.account == account:
            self.device_controller.load_account_configuration(account)

    def _delete_managed_device(self, serial: str) -> None:
        if self.devices_page._confirm_delete(serial):
            self.device_controller.delete_device(serial)

    def _show_add_account_dialog(self) -> None:
        device = next(
            (
                item
                for item in self.device_controller.managed_devices
                if item.serial == self._managed_phone_serial
            ),
            None,
        )
        if device is None:
            self._show_add_account_error(
                "The selected phone is not in the managed inventory."
            )
            return

        dialog = AddAccountDialog(
            device, tuple(template.name for template in self._templates), self
        )
        if dialog.exec():
            self.device_controller.add_account(
                dialog.username.text().strip(),
                dialog.password.text(),
                device.serial,
                dialog.selected_template(),
            )

    def _show_add_account_error(self, message: str) -> None:
        ErrorDialog("Add Account Failed", message, self).exec()

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
        self.phone_accounts_page.options_button.hide()

    def _sync_global_accounts(self, devices: list[DeviceRecord]) -> None:
        if (
            self._workspace_context == "accounts"
            and self.pages.currentWidget() is not self.account_page
        ):
            self.phone_accounts_page.set_all_accounts(
                [account for device in devices for account in device.accounts]
            )

    def closeEvent(self, event) -> None:
        self.session_controller.stop_all()
        self.live_log.detach_logging()
        super().closeEvent(event)
