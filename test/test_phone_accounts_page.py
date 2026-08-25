from pathlib import Path

from PySide6.QtCore import Qt
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
    assert page.model.index(0, page.model.USERNAME).data() == "real_account"
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
    assert page.proxy_model.index(0, page.model.USERNAME).data() == "MadisonParker"

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
    menu = page.build_account_options(account)

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
    opened_folders = []
    restore_requests = []
    delete_requests = []
    page.account_folder_requested.connect(opened_folders.append)
    page.restore_requested.connect(restore_requests.append)
    page.account_delete_requested.connect(delete_requests.append)

    menu = page.build_account_options(account)
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


def test_phone_account_double_click_opens_selected_account():
    application = QApplication.instance() or QApplication([])
    page = PhoneAccountsPage()
    account = AssignedAccount(
        username="real_account",
        device_id="phone-a",
        app_id="com.instagram.android",
        config_path=Path("accounts/real_account/config.yml"),
    )
    page.set_phone(DeviceRecord("phone-a", "Rack One", True), [account])
    opened = []
    page.account_open_requested.connect(opened.append)

    page.table.doubleClicked.emit(page.proxy_model.index(0, page.model.USERNAME))

    assert opened == [account]
    assert "Actions" not in page.model.HEADERS
    assert application is not None


def test_global_accounts_workspace_supports_username_search():
    application = QApplication.instance() or QApplication([])
    page = PhoneAccountsPage()
    accounts = [
        AssignedAccount(
            username=username,
            device_id=device,
            app_id="com.instagram.android",
            config_path=Path(f"accounts/{username}/config.yml"),
        )
        for username, device in (("first_account", "phone-a"), ("second", "phone-b"))
    ]

    page.set_all_accounts(accounts)
    page.search.setText("FIRST")

    assert page.page_header.title.text() == "Accounts"
    assert page.proxy_model.rowCount() == 1
    assert page.proxy_model.index(0, page.model.USERNAME).data() == "first_account"
    assert not page.device_context.isVisibleTo(page)
    assert application is not None


def test_phone_account_table_uses_final_dense_operator_columns():
    application = QApplication.instance() or QApplication([])
    page = PhoneAccountsPage()
    account = AssignedAccount(
        username="real_account",
        device_id="phone-a",
        app_id="com.instagram.android",
        config_path=Path("accounts/real_account/config.yml"),
    )
    page.set_phone(DeviceRecord("phone-a", "Rack One", True), [account])

    assert page.model.HEADERS == (
        "Start Hour",
        "End Hour",
        "Username",
        "Followers",
        "Following",
        "Followed",
        "Unfollowed",
        "Story",
        "Like",
        "Comment",
        "DM",
        "Posted",
        "Status",
    )
    assert page.table.verticalHeader().defaultSectionSize() == 34
    assert page.table.columnWidth(page.model.STATUS) == 96
    assert page.model.index(0, page.model.STATUS).data() == "—"
    assert (
        page.model.index(0, page.model.STATUS).data(Qt.TextAlignmentRole)
        == Qt.AlignCenter
    )
    assert application is not None
