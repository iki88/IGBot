import os

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from IGBot.core.device import DeviceFleetSnapshot, DeviceRecord
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


def test_start_action_is_present_and_disabled():
    start = next(
        button for button in DeviceActionsDelegate._BUTTONS if button.action == "start"
    )

    assert start.text == "Start"
    assert start.enabled is False


def test_action_order_is_start_manage_delete():
    assert [button.action for button in DeviceActionsDelegate._BUTTONS] == [
        "start",
        "manage",
        "delete",
    ]


def test_sidebar_devices_item_returns_from_phone_accounts(application):
    window = MainWindow(_DeviceService())
    window._open_phone_accounts(DeviceRecord("phone-a", "", True), [])
    assert window.pages.currentWidget() is window.phone_accounts_page

    devices_item = window.sidebar.navigation.item(0)
    window.sidebar.navigation.itemClicked.emit(devices_item)

    assert window.pages.currentWidget() is window.devices_page
    assert window.toolbar.title.text() == "Device management"
    window.close()
