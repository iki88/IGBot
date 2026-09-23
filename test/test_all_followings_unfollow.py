from datetime import datetime, timezone
from unittest.mock import Mock
from uuid import uuid4

from IGBot.runtime import RuntimeContext, SessionContext
from IGBot.runtime.follow import AndroidFollowResult, AndroidFollowStatus
from IGBot.runtime.scheduler import ModuleExecutionOutcome
from IGBot.runtime.unfollow import (
    AllFollowingsUnfollowModule,
    AndroidFollowingListUnfollowProvider,
    AndroidUnfollowResult,
    AndroidUnfollowStatus,
    FollowingListDatabase,
    UnfollowSettings,
)


def node(text="", resource_id="", description="", bounds="[0,0][100,100]"):
    return (
        f'<node text="{text}" resource-id="com.instagram.clone:id/{resource_id}" '
        f'content-desc="{description}" bounds="{bounds}" />'
    )


def hierarchy(*nodes):
    return "<hierarchy>" + "".join(nodes) + "</hierarchy>"


def following_row(username, action="Message"):
    return (
        '<node resource-id="com.instagram.clone:id/follow_list_container" '
        'bounds="[0,100][1080,300]">'
        + node(username, "follow_list_username")
        + node(action, "follow_list_row_large_follow_button")
        + node(resource_id="media_option_button", description="More options")
        + "</node>"
    )


class Logger:
    def __init__(self):
        self.messages = []

    def info(self, message, **fields):
        self.messages.append(("info", message, fields))

    def warning(self, message, **fields):
        self.messages.append(("warning", message, fields))

    def error(self, message, **fields):
        self.messages.append(("error", message, fields))

    def debug(self, message, **fields):
        self.messages.append(("debug", message, fields))


def context(tmp_path):
    return RuntimeContext(
        SessionContext(
            uuid4(),
            "account",
            "phone",
            "com.instagram.clone",
            tmp_path,
            datetime.now(timezone.utc),
        ),
        Logger(),
    )


def android_mock():
    android = Mock()
    android._id_has_suffix.side_effect = lambda value, ids: any(
        value.rsplit("/", 1)[-1] == identifier for identifier in ids
    )
    android._contains.return_value = True
    return android


def test_following_rows_use_inspected_username_and_menu_ids():
    rows = AndroidFollowingListUnfollowProvider._rows(
        hierarchy(following_row("target_user"))
    )

    assert len(rows) == 1
    assert rows[0].username == "target_user"
    assert rows[0].menu is not None
    assert rows[0].action_state == "message"


def test_following_rows_ignore_information_sections_and_capture_followed_states():
    categories = (
        '<node resource-id="com.instagram.clone:id/container" '
        'content-desc="Least interacted with">'
        + node("Least interacted with", "title")
        + "</node>"
    )

    rows = AndroidFollowingListUnfollowProvider._rows(
        hierarchy(
            categories,
            following_row("message_user", "Message"),
            following_row("following_user", "Following"),
            following_row("completed_user", "Follow"),
        )
    )

    assert [(row.username, row.action_state) for row in rows] == [
        ("message_user", "message"),
        ("following_user", "following"),
        ("completed_user", "follow"),
    ]


def test_default_sorting_performs_no_ui_action(tmp_path):
    android = android_mock()
    provider = AndroidFollowingListUnfollowProvider(android, sorting="default")
    provider._wait_for_node = Mock()

    provider._apply_sorting(context(tmp_path), object())

    android._tap.assert_not_called()
    provider._wait_for_node.assert_not_called()


def test_following_list_open_waits_for_populated_list_and_retries_once(tmp_path):
    android = android_mock()
    profile_restorer = Mock()
    profile_restorer.ensure_profile_page.return_value = True
    provider = AndroidFollowingListUnfollowProvider(
        android, profile_restorer=profile_restorer
    )
    following = object()
    list_shell = object()
    ready = object()
    provider._wait_for_node = Mock(side_effect=(following, list_shell, None, ready))
    provider._apply_sorting = Mock()
    ctx = context(tmp_path)

    result = provider._open_following_list(ctx, object())

    assert result is None
    assert provider._wait_for_node.call_count == 4
    provider._apply_sorting.assert_called_once()
    assert [message for _level, message, _fields in ctx.logger.messages][-3:] == [
        "[Following List] Waiting for Following list...",
        "[Following List] Following list loaded.",
        "[Following List] Beginning processing...",
    ]


def test_following_list_open_continues_on_first_ready_snapshot(tmp_path):
    android = android_mock()
    profile_restorer = Mock()
    profile_restorer.ensure_profile_page.return_value = True
    provider = AndroidFollowingListUnfollowProvider(
        android, profile_restorer=profile_restorer
    )
    provider._wait_for_node = Mock(side_effect=(object(), object(), object()))
    provider._apply_sorting = Mock()

    result = provider._open_following_list(context(tmp_path), object())

    assert result is None
    assert provider._wait_for_node.call_count == 3
    provider._apply_sorting.assert_called_once()


def test_non_default_sorting_is_applied_before_waiting_for_rows(tmp_path):
    android = android_mock()
    profile_restorer = Mock()
    profile_restorer.ensure_profile_page.return_value = True
    provider = AndroidFollowingListUnfollowProvider(
        android, sorting="latest", profile_restorer=profile_restorer
    )
    provider._wait_for_node = Mock(
        side_effect=(
            object(),  # Profile Following control.
            object(),  # Following-list shell.
            object(),  # Sort button.
            object(),  # Sort dialog.
            object(),  # Latest option.
            object(),  # Selected-option verification.
            object(),  # Populated sorted list.
        )
    )
    ctx = context(tmp_path)

    result = provider._open_following_list(ctx, object())

    assert result is None
    messages = [message for _level, message, _fields in ctx.logger.messages]
    assert messages.index(
        "[Following List] Applying sorting: Date followed: Latest"
    ) < messages.index("[Following List] Waiting for Following list...")
    assert provider._wait_for_node.call_count == 7
    assert android._tap.call_count == 3


def test_earliest_sorting_is_applied_before_waiting_for_rows(tmp_path):
    android = android_mock()
    profile_restorer = Mock()
    profile_restorer.ensure_profile_page.return_value = True
    provider = AndroidFollowingListUnfollowProvider(
        android, sorting="earliest", profile_restorer=profile_restorer
    )
    provider._wait_for_node = Mock(side_effect=(object(),) * 7)
    ctx = context(tmp_path)

    result = provider._open_following_list(ctx, object())

    assert result is None
    messages = [message for _level, message, _fields in ctx.logger.messages]
    assert messages.index(
        "[Following List] Applying sorting: Date followed: Earliest"
    ) < messages.index("[Following List] Waiting for Following list...")


def test_following_list_open_fails_after_two_readiness_attempts(tmp_path):
    android = android_mock()
    profile_restorer = Mock()
    profile_restorer.ensure_profile_page.return_value = True
    provider = AndroidFollowingListUnfollowProvider(
        android, profile_restorer=profile_restorer
    )
    provider._wait_for_node = Mock(side_effect=(object(), object(), None, None))
    provider._apply_sorting = Mock()

    result = provider._open_following_list(context(tmp_path), object())

    assert result.status is AndroidUnfollowStatus.NAVIGATION_FAILED
    assert result.detail == "Following list did not finish loading."
    provider._apply_sorting.assert_not_called()


def test_following_list_ready_accepts_row_or_verified_empty_state():
    android = android_mock()
    provider = AndroidFollowingListUnfollowProvider(android)
    list_node = object()
    title = Mock(resource_id="com.instagram.clone:id/title", text="41 Following")
    android._find_by_id.side_effect = (list_node, object(), object(), None)

    assert provider._following_list_ready((title,)) is list_node

    android._find_by_id.side_effect = (list_node, None, None, object())

    assert provider._following_list_ready((title,)) is list_node


def test_sort_dialog_retries_once_then_applies_configured_sort(tmp_path):
    android = android_mock()
    provider = AndroidFollowingListUnfollowProvider(android, sorting="latest")
    sort_button = object()
    dialog = object()
    option = object()
    indicator = object()
    provider._wait_for_node = Mock(
        side_effect=(sort_button, None, sort_button, dialog, option, indicator)
    )

    provider._apply_sorting(context(tmp_path), object())

    assert android._tap.call_count == 3
    assert provider._wait_for_node.call_count == 6


def test_row_menu_retries_once_and_handles_private_confirmation(tmp_path):
    android = android_mock()
    provider = AndroidFollowingListUnfollowProvider(android)
    menu = object()
    unfollow = object()
    provider._wait_for_node = Mock(side_effect=(None, menu, unfollow))
    dialog = object()
    confirm = Mock(text="Unfollow")
    android._find_by_id.side_effect = (dialog, confirm, None)
    device = Mock()
    device.dump_hierarchy.side_effect = (
        hierarchy(following_row("target_user", "Message")),
        hierarchy(following_row("target_user", "Follow")),
    )
    row = type("Row", (), {"username": "target_user", "menu": object()})()

    result = provider._unfollow_row(context(tmp_path), device, row)

    assert result.status is AndroidUnfollowStatus.SUCCESS
    assert android._tap.call_count == 4
    assert provider._wait_for_node.call_count == 3


def test_success_refreshes_rows_and_advances_without_scrolling(tmp_path):
    android = android_mock()
    device = android._device.return_value
    visible = hierarchy(
        following_row("first_user", "Message"),
        following_row("second_user", "Following"),
    )
    after_success = hierarchy(
        following_row("first_user", "Follow"),
        following_row("second_user", "Following"),
    )
    device.dump_hierarchy.side_effect = (
        visible,
        after_success,
        after_success,
        after_success,
    )
    provider = AndroidFollowingListUnfollowProvider(android)
    provider._opened = True
    provider._unfollow_row = Mock(
        side_effect=(
            AndroidUnfollowResult(AndroidUnfollowStatus.SUCCESS, username="first_user"),
            AndroidUnfollowResult(
                AndroidUnfollowStatus.SUCCESS, username="second_user"
            ),
        )
    )
    ctx = context(tmp_path)

    first = provider.execute_next(ctx, frozenset())
    second = provider.execute_next(ctx, frozenset())

    assert first.username == "first_user"
    assert second.username == "second_user"
    assert [
        call.args[2].username for call in provider._unfollow_row.call_args_list
    ] == [
        "first_user",
        "second_user",
    ]
    android.scroll_following_list.assert_not_called()


def test_completed_follow_state_is_never_processed(tmp_path):
    android = android_mock()
    android._device.return_value.dump_hierarchy.return_value = hierarchy(
        following_row("completed_user", "Follow")
    )
    android.scroll_followers.return_value = AndroidFollowResult(
        AndroidFollowStatus.FOLLOW_FAILED
    )
    provider = AndroidFollowingListUnfollowProvider(android)
    provider._opened = True
    provider._unfollow_row = Mock()

    result = provider.execute_next(context(tmp_path), frozenset())

    assert result.status is AndroidUnfollowStatus.NO_CANDIDATES
    provider._unfollow_row.assert_not_called()


class SuccessfulListAndroid:
    def execute_next(self, _context, processed):
        assert "completed_user" in processed
        return AndroidUnfollowResult(AndroidUnfollowStatus.SUCCESS, username="new_user")


def test_all_followings_history_resumes_and_updates_only_after_success(tmp_path):
    ctx = context(tmp_path)
    with FollowingListDatabase(tmp_path) as database:
        database.mark_unfollowed("completed_user", "2026-09-22 10:00:00", "old-session")
    module = AllFollowingsUnfollowModule(
        ctx,
        UnfollowSettings(True, True, 1, 5, 5, 0),
        SuccessfulListAndroid(),
    )
    module.start()

    result = module.execute(ctx, None)

    assert result.outcome is ModuleExecutionOutcome.SUCCESS
    with FollowingListDatabase(tmp_path) as database:
        saved = database.get("new_user")
        assert saved is not None
        assert saved.unfollowed
        assert saved.last_session_id == str(ctx.session.session_id)


class FailedListAndroid:
    def execute_next(self, _context, _processed):
        return AndroidUnfollowResult(AndroidUnfollowStatus.VERIFICATION_FAILED)


def test_failed_unfollow_does_not_update_following_list_database(tmp_path):
    ctx = context(tmp_path)
    module = AllFollowingsUnfollowModule(
        ctx,
        UnfollowSettings(True, True, 1, 5, 5, 0),
        FailedListAndroid(),
    )
    module.start()

    module.execute(ctx, None)

    with FollowingListDatabase(tmp_path) as database:
        assert not database.processed_usernames()


def test_scroll_failure_finishes_list(tmp_path):
    android = android_mock()
    android._device.return_value.dump_hierarchy.return_value = hierarchy()
    android.scroll_following_list.return_value = AndroidFollowResult(
        AndroidFollowStatus.FOLLOW_FAILED
    )
    provider = AndroidFollowingListUnfollowProvider(android)
    provider._opened = True

    result = provider.execute_next(context(tmp_path), frozenset())

    assert result.status is AndroidUnfollowStatus.NO_CANDIDATES
