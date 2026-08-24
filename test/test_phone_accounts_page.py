from pathlib import Path

from PySide6.QtWidgets import QApplication

from IGBot.core.device import AssignedAccount, DeviceRecord
from IGBot.ui.pages.phone_accounts_page import PhoneAccountsPage


def test_phone_accounts_page_shows_clean_empty_state():
    application = QApplication.instance() or QApplication([])
    page = PhoneAccountsPage()

    page.set_phone(DeviceRecord("phone-a", "", True), [])

    assert page.empty_state.isVisibleTo(page)
    assert (
        page.empty_state.description.text()
        == "No Instagram accounts assigned to this phone."
    )
    assert page.model.rowCount() == 0
    assert application is not None


def test_phone_accounts_page_displays_real_assignments():
    application = QApplication.instance() or QApplication([])
    page = PhoneAccountsPage()
    account = AssignedAccount(
        username="real_account",
        device_id="phone-a",
        app_id="com.instagram.android",
        config_path=Path("accounts/real_account/config.yml"),
    )

    page.set_phone(DeviceRecord("phone-a", "Rack One", True, (account,)), [account])

    assert page.model.rowCount() == 1
    assert page.model.index(0, 0).data() == "real_account"
    assert not page.empty_state.isVisibleTo(page)
    assert application is not None
