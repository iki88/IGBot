from datetime import datetime, timedelta, timezone
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from IGBot.core.device import AssignedAccount, DeviceRecord
from IGBot.runtime.analytics import AnalyticsDatabase
from IGBot.services.account_metadata_service import AccountMetadataService
from IGBot.ui.pages.account_statistics_page import AccountStatisticsPage
from IGBot.ui.pages.phone_accounts_page import PhoneAccountsPage
from IGBot.ui.widgets.trend_indicator_delegate import TrendIndicatorDelegate


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
    ignore_requests = []
    page.ignore_list_requested.connect(ignore_requests.append)
    menu = page.build_account_options(account)

    assert [action.text() for action in menu.actions()] == [
        "Transfer Account",
        "Archive Account",
        "Apply Template...",
        "Ignored Accounts List...",
        "Open Account Folder",
        "Enable Debug Logging",
    ]
    assert all(action.isEnabled() for action in menu.actions())
    menu.actions()[3].trigger()
    assert ignore_requests == [account]
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
        "Ignored Accounts List...",
        "Open Account Folder",
        "Enable Debug Logging",
        "Delete Account",
    ]
    assert actions[0].isEnabled()
    assert actions[1].isEnabled()
    assert actions[2].isEnabled()
    assert actions[3].isEnabled()
    assert actions[4].isEnabled()

    actions[0].trigger()
    actions[2].trigger()
    actions[4].trigger()

    assert restore_requests == ["archived_account"]
    assert opened_folders == [str(Path("accounts/archived_account"))]
    assert delete_requests == ["archived_account"]
    assert application is not None


def test_account_options_reflect_and_emit_existing_debug_setting(tmp_path):
    application = QApplication.instance() or QApplication([])
    directory = tmp_path / "accounts" / "real_account"
    directory.mkdir(parents=True)
    config_path = directory / "config.yml"
    config_path.write_text(
        "username: real_account\ndebug: true\n", encoding="utf-8"
    )
    account = AssignedAccount(
        "real_account", "phone-a", "com.instagram.android", config_path
    )
    page = PhoneAccountsPage()
    requests = []
    page.debug_logging_requested.connect(
        lambda selected, enabled: requests.append((selected, enabled))
    )

    menu = page.build_account_options(account)
    action = next(
        item for item in menu.actions() if item.text() == "Enable Debug Logging"
    )
    assert action.isChecked()

    action.trigger()

    assert requests == [(account, False)]
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
    assert page.model.HEADERS[-1] == "Actions"
    assert application is not None


def test_account_actions_are_shared_and_route_existing_workflows():
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
    archived = []
    page.account_open_requested.connect(opened.append)
    page.archive_requested.connect(
        lambda username, device: archived.append((username, device))
    )

    assert [action.name for action in page.actions_delegate.ACTIONS] == [
        "analytics",
        "edit",
    ]
    assert [action.tooltip for action in page.actions_delegate.ACTIONS] == [
        "Statistics",
        "Edit Account",
    ]
    assert [action.name for action in page.actions_delegate.visible_actions()] == [
        "analytics",
        "edit",
        "archive",
    ]

    page._handle_account_action("edit", account)
    page._handle_account_action("archive", account)

    assert opened == [account]
    assert archived == [("real_account", "phone-a")]
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
    assert [action.name for action in page.actions_delegate.visible_actions()] == [
        "analytics",
        "edit",
        "archive",
    ]
    assert page.table.columnWidth(page.model.ACTIONS) == 112
    assert application is not None


def test_accounts_and_phone_accounts_display_configured_tag(tmp_path):
    application = QApplication.instance() or QApplication([])
    directory = tmp_path / "accounts" / "tagged"
    directory.mkdir(parents=True)
    config_path = directory / "config.yml"
    config_path.write_text("username: tagged\n", encoding="utf-8")
    AccountMetadataService().save(
        directory, "tagged", "secret", "phone-a", tag="Warmup"
    )
    account = AssignedAccount("tagged", "phone-a", "com.instagram.android", config_path)
    page = PhoneAccountsPage()

    page.set_all_accounts([account])
    assert page.model.index(0, page.model.TAG).data() == "Warmup"
    page.set_phone(DeviceRecord("phone-a", "Rack One", True), [account])
    assert page.model.index(0, page.model.TAG).data() == "Warmup"
    assert page.model.HEADERS[page.model.USERNAME + 1] == "Tag"
    assert application is not None


def test_statistics_action_always_routes_account():
    application = QApplication.instance() or QApplication([])
    page = PhoneAccountsPage()
    account = AssignedAccount(
        "real_account",
        "phone-a",
        "com.instagram.android",
        Path("accounts/real_account/config.yml"),
    )
    requested = []
    page.statistics_requested.connect(requested.append)

    page._handle_account_action("analytics", account)

    assert requested == [account]
    assert page.actions_delegate._is_enabled("analytics", account)
    assert application is not None


def test_statistics_dialog_handles_missing_and_existing_analytics(tmp_path):
    application = QApplication.instance() or QApplication([])
    directory = tmp_path / "accounts" / "statistics"
    directory.mkdir(parents=True)
    config_path = directory / "config.yml"
    config_path.write_text("username: statistics\n", encoding="utf-8")
    account = AssignedAccount(
        "statistics", "phone-a", "com.instagram.android", config_path
    )

    empty = AccountStatisticsPage()
    empty.set_account(account)
    assert empty.empty.isVisibleTo(empty)
    assert not empty.table.isVisibleTo(empty)
    assert not (directory / "analytics.db").exists()

    with AnalyticsDatabase(directory) as database:
        database.update_snapshot("statistics", posts=4, followers=20, following=8)
    populated = AccountStatisticsPage()
    populated.set_account(account)
    assert populated.table.objectName() == "statisticsTable"
    assert populated.table.rowCount() == 1
    assert populated.table.item(0, 0).text() == datetime.now(timezone.utc).date().isoformat()
    assert populated.table.item(0, 3).text() == "20"
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
        "Tag",
        "Followers",
        "Following",
        "Posts",
        "Followed",
        "Unfollowed",
        "Story",
        "Like",
        "Comment",
        "DM",
        "Posted",
        "Status",
        "Actions",
    )
    assert page.table.verticalHeader().defaultSectionSize() == 34
    assert page.table.columnWidth(page.model.STATUS) == 96
    assert page.table.columnWidth(page.model.ACTIONS) == 112
    assert page.model.index(0, page.model.STATUS).data() == "Idle"
    assert (
        page.model.index(0, page.model.STATUS).data(Qt.TextAlignmentRole)
        == Qt.AlignCenter
    )
    assert application is not None


def test_phone_accounts_reads_today_analytics_and_computes_snapshot_delta(tmp_path):
    application = QApplication.instance() or QApplication([])
    directory = tmp_path / "accounts" / "analytic_account"
    directory.mkdir(parents=True)
    config_path = directory / "config.yml"
    config_path.write_text("username: analytic_account\n", encoding="utf-8")
    account = AssignedAccount(
        "analytic_account", "phone-a", "com.instagram.android", config_path
    )
    with AnalyticsDatabase(directory) as database:
        previous_day = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
        database._connection.execute(
            """
            INSERT INTO daily_summary (
                date, username, posts, followers, following
            ) VALUES (?, 'analytic_account', 10, 100, 50)
            """,
            (previous_day,),
        )
        database.update_snapshot(
            "analytic_account", posts=11, followers=108, following=47
        )
        database.increment("analytic_account", "followed", 2)
        database.increment("analytic_account", "liked", 3)

    page = PhoneAccountsPage()
    page.set_all_accounts([account])

    columns = {name: page.model.HEADERS.index(name) for name in page.model.HEADERS}
    assert page.model.index(0, columns["Followers"]).data() == "108 ▲8"
    assert page.model.index(0, columns["Following"]).data() == "47 ▼3"
    assert page.model.index(0, columns["Posts"]).data() == "11 ▲1"
    assert (
        page.table.itemDelegateForColumn(columns["Followers"])
        is page.trend_delegate
    )
    assert page.model.index(0, columns["Followed"]).data() == "2"
    assert page.model.index(0, columns["Like"]).data() == "3"
    assert application is not None


def test_trend_indicator_delegate_separates_only_the_arrow_for_styling():
    assert TrendIndicatorDelegate.segments("127 ▲10") == ("127 ", "▲", "10")
    assert TrendIndicatorDelegate.segments("41 ▼8") == ("41 ", "▼", "8")
    assert TrendIndicatorDelegate.segments("25") is None
    assert TrendIndicatorDelegate.INCREASE_COLOR.name() == "#22c55e"
    assert TrendIndicatorDelegate.DECREASE_COLOR.name() == "#ef4444"


def test_accounts_overview_displays_saved_timer_values(tmp_path):
    application = QApplication.instance() or QApplication([])
    directory = tmp_path / "accounts" / "scheduled_account"
    directory.mkdir(parents=True)
    config_path = directory / "config.yml"
    config_path.write_text(
        "username: scheduled_account\n"
        "device: phone-a\n"
        "app-id: com.instagram.android\n"
        "working-hours: [10.00-12.00, 15.30-17.00]\n",
        encoding="utf-8",
    )
    account = AssignedAccount(
        "scheduled_account", "phone-a", "com.instagram.android", config_path
    )
    page = PhoneAccountsPage()

    page.set_all_accounts([account])

    assert page.model.index(0, page.model.START_HOUR).data() == "10:00,15:30"
    assert page.model.index(0, page.model.END_HOUR).data() == "12:00,17:00"
    assert application is not None
