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


def test_archived_accounts_search_filters_usernames_case_insensitively():
    application = QApplication.instance() or QApplication([])
    page = PhoneAccountsPage()
    accounts = [
        AssignedAccount(
            username=username,
            device_id="ARCHIVED_ACCOUNTS",
            app_id="com.instagram.android",
            config_path=Path(f"accounts/{username}/config.yml"),
        )
        for username in ("MadisonParker", "another_account")
    ]

    page.set_archived(accounts)

    assert page.search.isVisibleTo(page)
    assert page.proxy_model.rowCount() == 2

    page.search.setText("MADISON")

    assert page.proxy_model.rowCount() == 1
    assert page.proxy_model.index(0, 0).data() == "MadisonParker"

    page.search.clear()

    assert page.proxy_model.rowCount() == 2
    assert application is not None


def test_archived_search_is_hidden_and_reset_for_phone_accounts():
    application = QApplication.instance() or QApplication([])
    page = PhoneAccountsPage()

    page.set_archived([])
    page.search.setText("archived")
    page.set_phone(DeviceRecord("phone-a", "Rack One", True), [])

    assert not page.search.isVisibleTo(page)
    assert page.search.text() == ""
    assert application is not None


def test_active_account_options_include_transfer_archive_and_open_folder():
    application = QApplication.instance() or QApplication([])
    page = PhoneAccountsPage()
    account = AssignedAccount(
        username="real_account",
        device_id="phone-a",
        app_id="com.instagram.android",
        config_path=Path("accounts/real_account/config.yml"),
    )
    page.set_phone(DeviceRecord("phone-a", "Rack One", True), [account])
    index = page.proxy_model.index(0, page.model.HEADERS.index("Actions"))

    menu = page._build_account_options(index)

    assert [action.text() for action in menu.actions()] == [
        "Transfer Account",
        "Archive Account",
        "Open Account Folder",
    ]
    assert all(action.isEnabled() for action in menu.actions())
    assert application is not None


def test_archived_account_options_include_restore_open_folder_and_delete():
    application = QApplication.instance() or QApplication([])
    page = PhoneAccountsPage()
    account = AssignedAccount(
        username="archived_account",
        device_id="ARCHIVED_ACCOUNTS",
        app_id="com.instagram.android",
        config_path=Path("accounts/archived_account/config.yml"),
    )
    page.set_archived([account])
    index = page.proxy_model.index(0, page.model.HEADERS.index("Actions"))
    opened_folders = []
    restore_requests = []
    delete_requests = []
    page.account_folder_requested.connect(opened_folders.append)
    page.restore_requested.connect(restore_requests.append)
    page.account_delete_requested.connect(delete_requests.append)

    menu = page._build_account_options(index)
    actions = menu.actions()

    assert [action.text() for action in actions] == [
        "Restore Account",
        "Open Account Folder",
        "Delete Account",
    ]
    assert actions[0].isEnabled()
    assert actions[1].isEnabled()
    assert actions[2].isEnabled()

    actions[0].trigger()
    actions[1].trigger()
    actions[2].trigger()

    assert restore_requests == ["archived_account"]
    assert opened_folders == [str(Path("accounts/archived_account"))]
    assert delete_requests == ["archived_account"]
    assert application is not None
