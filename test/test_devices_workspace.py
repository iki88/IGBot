import os
from pathlib import Path

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from IGBot.core.device import AssignedAccount, DeviceFleetSnapshot, DeviceRecord
from IGBot.core.session_engine import SessionState
from IGBot.ui.controllers.device_controller import DeviceController
from IGBot.ui.main_window import MainWindow
from IGBot.ui.models.device_table_model import DeviceTableModel
from IGBot.ui.pages.devices_page import DevicesPage
from IGBot.ui.widgets.device_actions_delegate import DeviceActionsDelegate

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class _Controller(QObject):
    refresh_started = Signal()
    devices_changed = Signal(list)
    discovery_failed = Signal(str)
    deletion_started = Signal(str)
    operation_failed = Signal(str)

    def __init__(self):
        super().__init__()
        self.managed_serials = []
        self.deleted_serials = []

    def refresh(self):
        return None

    def open_phone_accounts(self, serial):
        self.managed_serials.append(serial)

    def delete_device(self, serial):
        self.deleted_serials.append(serial)


class _DeviceService:
    def refresh(self):
        return DeviceFleetSnapshot(())

    def delete(self, serial):
        return None


@pytest.fixture(scope="module")
def application():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def devices_page(application):
    controller = _Controller()
    page = DevicesPage(controller)
    page._set_devices(
        [
            DeviceRecord("serial-alpha", "Rack One", True),
            DeviceRecord("serial-beta", "Rack Two", False),
        ]
    )
    return page, controller


def test_search_filters_by_device_id_and_phone_name(devices_page):
    page, _ = devices_page

    page.search.setText("beta")
    assert page.proxy_model.rowCount() == 1
    assert page.proxy_model.index(0, DeviceTableModel.DEVICE_ID).data() == "serial-beta"

    page.search.setText("rack one")
    assert page.proxy_model.rowCount() == 1
    assert (
        page.proxy_model.index(0, DeviceTableModel.DEVICE_ID).data() == "serial-alpha"
    )


def test_double_click_opens_phone_accounts_workspace(devices_page):
    page, controller = devices_page
    index = page.proxy_model.index(0, DeviceTableModel.PHONE)

    page.table.doubleClicked.emit(index)

    assert controller.managed_serials == ["serial-alpha"]


def test_copy_device_id_uses_clipboard(devices_page, application):
    page, _ = devices_page
    notifications = []
    page.notification_requested.connect(
        lambda message, timeout: notifications.append((message, timeout))
    )

    page._copy_device_id("serial-alpha")

    assert application.clipboard().text() == "serial-alpha"
    assert notifications == [("Device ID copied.", 2500)]


def test_fleet_counters_include_offline_devices(devices_page):
    page, _ = devices_page

    assert page.fleet_summary.text() == "2 Phones"
    assert page.connection_summary.text() == "1 Connected"
    assert page.offline_summary.text() == "1 Offline"

    page._set_devices([DeviceRecord("serial-alpha", "Rack One", False)])

    assert page.fleet_summary.text() == "1 Phones"
    assert page.connection_summary.text() == "0 Connected"
    assert page.offline_summary.text() == "1 Offline"


def test_delete_requires_both_confirmations(devices_page, mocker):
    page, _ = devices_page
    dialogs = mocker.patch.object(page, "_show_delete_dialog")
    dialogs.side_effect = [True, False]

    assert page._confirm_delete("serial-alpha") is False
    assert dialogs.call_count == 2

    dialogs.reset_mock(side_effect=True)
    dialogs.side_effect = [True, True]
    assert page._confirm_delete("serial-alpha") is True
    assert dialogs.call_count == 2


def test_start_action_is_present_and_enabled():
    runtime = next(
        button
        for button in DeviceActionsDelegate._BUTTONS
        if button.action == "runtime"
    )

    assert runtime.enabled is True


def test_action_order_is_runtime_settings_delete():
    assert [button.action for button in DeviceActionsDelegate._BUTTONS] == [
        "runtime",
        "manage",
        "delete",
    ]


def test_device_start_action_routes_to_runtime_signal(devices_page):
    page, _ = devices_page
    requested = []
    page.runtime_start_requested.connect(requested.append)

    page._handle_row_action("start", "serial-alpha")

    assert requested == ["serial-alpha"]


def test_device_runtime_action_changes_to_stop_for_running_phone(devices_page):
    page, _ = devices_page
    stopped = []
    page.runtime_stop_requested.connect(stopped.append)

    page.set_runtime_status("serial-alpha", "Running")
    index = page.proxy_model.index(0, DeviceTableModel.ACTIONS)

    assert page.actions_delegate._resolved_action("runtime", index) == "stop"
    assert page.model.index(0, DeviceTableModel.STATUS).data() == "Running"
    page._handle_row_action("stop", "serial-alpha")
    assert stopped == ["serial-alpha"]


def test_sidebar_devices_item_returns_from_phone_accounts(application):
    window = MainWindow(_DeviceService())
    window._open_phone_accounts(DeviceRecord("phone-a", "", True), [])
    assert window.pages.currentWidget() is window.phone_accounts_page

    devices_item = window.sidebar.navigation.item(0)
    window.sidebar.navigation.itemClicked.emit(devices_item)

    assert window.pages.currentWidget() is window.devices_page
    assert window.toolbar.title.text() == "Device management"
    window.close()


def test_sidebar_contains_workspace_and_settings_navigation(application):
    window = MainWindow(_DeviceService())

    assert [
        window.sidebar.navigation.item(index).text()
        for index in range(window.sidebar.navigation.count())
    ] == ["Devices", "Accounts", "Archived", "Activity Log", "Templates"]
    assert window.sidebar.settings_navigation.item(0).text() == "Global Settings"
    window.close()


def test_global_accounts_workspace_excludes_archived_accounts(application):
    window = MainWindow(_DeviceService())
    account = AssignedAccount(
        "active_account",
        "phone-a",
        "com.instagram.android",
        Path("accounts/active_account/config.yml"),
    )
    window.device_controller._records = {
        "phone-a": DeviceRecord("phone-a", "Rack One", True, (account,))
    }

    accounts_item = window.sidebar.navigation.item(1)
    window.sidebar.navigation.itemClicked.emit(accounts_item)

    assert window.pages.currentWidget() is window.phone_accounts_page
    assert window.phone_accounts_page.model.rowCount() == 1
    assert window.phone_accounts_page.model.account_at(0) == account
    assert not window.toolbar.add_device_action.isVisible()
    window.close()


def test_account_navigation_uses_context_specific_toolbar(application):
    window = MainWindow(_DeviceService())
    account = AssignedAccount(
        "active_account",
        "phone-a",
        "com.instagram.android",
        Path("accounts/active_account/config.yml"),
    )
    device = DeviceRecord("phone-a", "Rack One", True, (account,))
    window.device_controller._records = {"phone-a": device}

    window._open_phone_accounts(device, [account])

    assert window.toolbar.add_account_action.isVisible()
    assert window.toolbar.runtime_action.isVisible()
    assert window.toolbar.view_phone_action.isVisible()
    assert window.toolbar.view_phone_action.isEnabled()
    assert not window.toolbar.save_action.isVisible()

    window._open_account(account)

    assert window.pages.currentWidget() is window.account_page
    assert window.account_page.account == account
    assert window.toolbar.save_action.isVisible()
    assert window.toolbar.save_action.isEnabled()
    assert window.toolbar.options_button.text() == "Account Options"
    assert not window.toolbar.add_account_action.isVisible()
    assert not window.toolbar.runtime_action.isVisible()
    assert not window.toolbar.view_phone_action.isVisible()
    assert [
        window.account_page.tabs.tabText(i)
        for i in range(window.account_page.tabs.count())
    ] == list(window.account_page.TABS)
    window.close()


def test_phone_toolbar_actions_use_compact_icons(application):
    window = MainWindow(_DeviceService())
    window._open_phone_accounts(DeviceRecord("phone-a", "Rack One", True), [])

    actions = (
        window.toolbar.add_account_action,
        window.toolbar.today_action,
        window.toolbar.runtime_action,
        window.toolbar.view_phone_action,
    )

    assert [action.text() for action in actions] == [
        "Add Account",
        "Today",
        "Start",
        "View Phone",
    ]
    assert all(action.isVisible() and not action.icon().isNull() for action in actions)
    assert window.toolbar.add_account_action.isEnabled()
    assert not window.toolbar.today_action.isEnabled()
    assert window.toolbar.runtime_action.isEnabled()
    assert window.toolbar.view_phone_action.isEnabled()
    assert window.toolbar.iconSize().width() == 16
    assert not window.toolbar.options_button.icon().isNull()
    window.close()


def test_devices_toolbar_exposes_fleet_runtime_actions(application, mocker):
    device = DeviceRecord("phone-a", "Rack One", True)
    service = _DeviceService()
    mocker.patch.object(service, "refresh", return_value=DeviceFleetSnapshot((device,)))
    window = MainWindow(service)
    application.processEvents()
    window.device_controller._records = {device.serial: device}
    start = mocker.patch.object(window.session_controller, "start")
    stop_all = mocker.patch.object(window.session_controller, "stop_all")

    assert window.toolbar.start_all_action.isVisible()
    assert window.toolbar.stop_all_action.isVisible()
    assert window.toolbar.start_all_action.text() == "Start All"
    assert window.toolbar.stop_all_action.text() == "Stop All"

    window.toolbar.start_all_action.trigger()
    window.toolbar.stop_all_action.trigger()

    start.assert_called_once_with(device)
    stop_all.assert_called_once_with()
    window.close()


def test_phone_start_action_starts_phone_scheduler_without_account_selection(
    application, mocker
):
    account = AssignedAccount(
        "active_account",
        "phone-a",
        "com.instagram.android",
        Path("accounts/active_account/config.yml"),
    )
    device = DeviceRecord("phone-a", "Rack One", True, (account,))
    service = _DeviceService()
    mocker.patch.object(service, "refresh", return_value=DeviceFleetSnapshot((device,)))
    window = MainWindow(service)
    application.processEvents()
    window.device_controller._records = {device.serial: device}
    window._open_phone_accounts(device, [account])
    start = mocker.patch.object(window.session_controller, "start")
    error = mocker.patch.object(window, "_show_runtime_error")

    assert window.toolbar.runtime_action.isEnabled()

    window.toolbar.runtime_action.trigger()
    application.processEvents()

    start.assert_called_once_with(device)
    error.assert_not_called()
    assert "Start clicked in Phone workspace" in window.live_log.output.toPlainText()
    window.close()


def test_device_row_start_calls_session_controller_for_real_accounts(
    application, mocker
):
    account = AssignedAccount(
        "active_account",
        "phone-a",
        "com.instagram.android",
        Path("accounts/active_account/config.yml"),
    )
    device = DeviceRecord("phone-a", "Rack One", True, (account,))
    service = _DeviceService()
    mocker.patch.object(service, "refresh", return_value=DeviceFleetSnapshot((device,)))
    window = MainWindow(service)
    application.processEvents()
    window.device_controller._records = {device.serial: device}
    start = mocker.patch.object(window.session_controller, "start")

    window.devices_page.runtime_start_requested.emit("phone-a")
    application.processEvents()

    start.assert_called_once_with(device)
    assert "Start clicked for phone phone-a" in window.live_log.output.toPlainText()
    assert window.toolbar.runtime_action.toolTip() == "Start this phone's scheduler"
    window.close()


def test_phone_stop_action_calls_session_controller_and_logs(application, mocker):
    account = AssignedAccount(
        "active_account",
        "phone-a",
        "com.instagram.android",
        Path("accounts/active_account/config.yml"),
    )
    device = DeviceRecord("phone-a", "Rack One", True, (account,))
    service = _DeviceService()
    mocker.patch.object(service, "refresh", return_value=DeviceFleetSnapshot((device,)))
    window = MainWindow(service)
    application.processEvents()
    window._open_phone_accounts(device, [account])
    mocker.patch.object(
        window.session_controller, "state_for", return_value=SessionState.RUNNING
    )
    stop = mocker.patch.object(window.session_controller, "stop")
    window._update_runtime_toolbar(None)

    assert window.toolbar.runtime_action.isEnabled()
    assert window.toolbar.runtime_action.text() == "Stop"
    window.toolbar.runtime_action.trigger()
    application.processEvents()

    stop.assert_called_once_with("phone-a")
    assert "Stop clicked in Phone workspace" in window.live_log.output.toPlainText()
    window.close()


def test_detect_app_id_controller_updates_ui_and_writes_live_log(
    application, mocker, caplog
):
    service = _DeviceService()
    service.foreground_package = mocker.Mock(return_value="com.instagram.detected")
    window = MainWindow(service)
    account = AssignedAccount("account", "phone-a", "", Path("account/config.yml"))
    window.device_controller._records = {
        "phone-a": DeviceRecord("phone-a", "T1", True, (account,))
    }
    window._open_account(account)
    started = mocker.patch.object(window.device_controller._thread_pool, "start")

    with caplog.at_level("INFO"):
        window.account_page.detect_app_id_button.click()
        task = started.call_args.args[0]
        task.run()

    assert window.account_page.application_id.text() == "com.instagram.detected"
    assert "Detect App ID started for phone-a" in caplog.text
    assert (
        "Foreground package detected for phone-a: com.instagram.detected" in caplog.text
    )
    window.close()


def test_detect_app_id_failure_is_logged_and_emitted(application, mocker, caplog):
    service = _DeviceService()
    service.foreground_package = mocker.Mock(
        side_effect=RuntimeError("No foreground package")
    )
    controller = DeviceController(service)
    started = mocker.patch.object(controller._thread_pool, "start")
    failures = []
    controller.foreground_package_failed.connect(failures.append)

    with caplog.at_level("ERROR"):
        controller.detect_foreground_package("phone-a")
        task = started.call_args.args[0]
        task.run()

    assert failures == ["No foreground package"]
    assert "Detect App ID failed for phone-a: No foreground package" in caplog.text


def test_archived_account_opens_shared_account_page(application):
    window = MainWindow(_DeviceService())
    account = AssignedAccount(
        "archived_account",
        "ARCHIVED_ACCOUNTS",
        "com.instagram.android",
        Path("accounts/archived_account/config.yml"),
    )

    window._open_archived([account])
    window._open_account(account)

    assert window.pages.currentWidget() is window.account_page
    assert window.account_page.device.text() == "Archived"
    assert [
        action.text() for action in window.toolbar.options_button.menu().actions()
    ] == [
        "Restore Account",
        "Open Account Folder",
        "Delete Account",
    ]
    window.close()


def test_activity_log_and_global_settings_routes(application):
    window = MainWindow(_DeviceService())

    window._navigate_to_page(3)

    assert window.pages.currentWidget() is window.activity_log_page
    assert (
        window.activity_log_page.output.document() is window.live_log.output.document()
    )
    assert window.live_log.isHidden()

    settings_item = window.sidebar.settings_navigation.item(0)
    window.sidebar.settings_navigation.itemClicked.emit(settings_item)

    assert window.pages.currentWidget() is window.global_settings_page
    assert window.toolbar.title.text() == "Global settings"
    window.close()
