import os

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from IGBot.core.device import DeviceRecord
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

    page._copy_device_id("serial-alpha")

    assert application.clipboard().text() == "serial-alpha"


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
