from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from uuid import uuid4

from IGBot.runtime import RuntimeContext, SessionContext
from IGBot.runtime.database import FollowRecord, RuntimeDatabase
from IGBot.runtime.scheduler import ModuleExecutionOutcome
from IGBot.runtime.unfollow import (
    AndroidFollowingListSearchUnfollowProvider,
    AndroidUnfollowResult,
    AndroidUnfollowStatus,
    UnfollowModule,
    UnfollowSettings,
)


class Logger:
    def info(self, _message, **_fields):
        pass

    def warning(self, _message, **_fields):
        pass


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


def hierarchy(*nodes):
    return "<hierarchy>" + "".join(nodes) + "</hierarchy>"


def following_row(username):
    return (
        '<node resource-id="com.instagram.clone:id/follow_list_container" '
        'bounds="[0,100][1080,300]">'
        f'<node text="{username}" resource-id="com.instagram.clone:id/'
        'follow_list_username" bounds="[0,0][100,100]" />'
        '<node text="" resource-id="com.instagram.clone:id/media_option_button" '
        'content-desc="More options" bounds="[0,0][100,100]" />'
        "</node>"
    )


class StubAndroid:
    def __init__(self, status):
        self.status = status
        self.usernames = []

    def execute(self, _context, username):
        self.usernames.append(username)
        return AndroidUnfollowResult(self.status, username=username)


def seed_follow(database, username, followed_at, *, unfollowed=False):
    user = database.users.create(username, followed_at, "FOLLOW")
    database.follow.save(
        FollowRecord(
            user.id,
            username,
            "source",
            followed_at,
            unfollowed=unfollowed,
            unfollow_date=followed_at if unfollowed else None,
        )
    )
    return user.id


def search_node(text="Search"):
    return Mock(
        text=text,
        resource_id="com.instagram.androie:id/row_search_edit_text",
    )


def test_list_search_uses_exact_inspected_following_row(tmp_path):
    android = Mock()
    android._device.return_value = device = Mock()
    android._id_has_suffix.side_effect = lambda value, ids: any(
        value.rsplit("/", 1)[-1] == identifier for identifier in ids
    )
    sleeper = Mock()
    settle_delay = Mock(return_value=2.4)
    provider = AndroidFollowingListSearchUnfollowProvider(
        android, sleeper=sleeper, search_settle_delay=settle_delay
    )
    provider._opened = True
    provider._clear_search = Mock(return_value=True)
    provider._wait_for_node = Mock(return_value=search_node())
    provider._wait_for_exact_row = Mock(
        return_value=provider._rows(hierarchy(following_row("target_user")))[0]
    )
    provider._unfollow_row = Mock(
        return_value=AndroidUnfollowResult(
            AndroidUnfollowStatus.SUCCESS, username="target_user"
        )
    )

    result = provider.execute(context(tmp_path), "target_user")

    assert result.status is AndroidUnfollowStatus.SUCCESS
    device.send_keys.assert_called_once_with("target_user", clear=True)
    settle_delay.assert_called_once_with()
    sleeper.assert_called_once_with(2.4)
    assert provider._clear_search.call_count == 2


def test_missing_username_clears_search_and_reports_search_failure(tmp_path):
    android = Mock()
    android._device.return_value = device = Mock()
    provider = AndroidFollowingListSearchUnfollowProvider(android)
    provider._opened = True
    provider._clear_search = Mock(return_value=True)
    provider._wait_for_node = Mock(return_value=search_node())
    provider._wait_for_exact_row = Mock(return_value=None)

    result = provider.execute(context(tmp_path), "missing_user")

    assert result.status is AndroidUnfollowStatus.SEARCH_FAILED
    device.send_keys.assert_called_once_with("missing_user", clear=True)
    assert provider._clear_search.call_count == 2


def test_search_reset_is_verified_after_clear(tmp_path):
    android = Mock()
    device = Mock()
    provider = AndroidFollowingListSearchUnfollowProvider(android)
    provider._wait_for_node = Mock(side_effect=(search_node("target"), search_node()))

    assert provider._clear_search(context(tmp_path), device)

    device.send_keys.assert_called_once_with("", clear=True)


class MissingThenSuccessfulAndroid:
    def __init__(self):
        self.usernames = []

    def execute(self, _context, username):
        self.usernames.append(username)
        if username == "missing_user":
            return AndroidUnfollowResult(
                AndroidUnfollowStatus.SEARCH_FAILED, username=username
            )
        return AndroidUnfollowResult(AndroidUnfollowStatus.SUCCESS, username=username)


def test_list_search_continues_after_missing_persisted_username(tmp_path):
    now = datetime.now(timezone.utc)
    with RuntimeDatabase(tmp_path) as database:
        missing_id = seed_follow(database, "missing_user", now - timedelta(days=10))
        found_id = seed_follow(database, "found_user", now - timedelta(days=9))
    ctx = context(tmp_path)
    android = MissingThenSuccessfulAndroid()
    module = UnfollowModule(
        ctx,
        UnfollowSettings(True, True, 1, 10, 10, 0),
        android,
        continue_after_search_failure=True,
    )
    module.start()

    result = module.execute(ctx, None)

    assert result.outcome is ModuleExecutionOutcome.SUCCESS
    assert android.usernames == ["missing_user", "found_user"]
    with RuntimeDatabase(tmp_path) as database:
        assert not database.follow.get(missing_id).unfollowed
        assert database.follow.get(found_id).unfollowed


def test_only_non_followers_excludes_follow_back_records(tmp_path):
    now = datetime.now(timezone.utc)
    with RuntimeDatabase(tmp_path) as database:
        followed_back = seed_follow(database, "followed_back", now - timedelta(days=10))
        record = database.follow.get(followed_back)
        database.follow.save(replace(record, follow_back=True))
        seed_follow(database, "non_follower", now - timedelta(days=9))
    ctx = context(tmp_path)
    android = StubAndroid(AndroidUnfollowStatus.SUCCESS)
    module = UnfollowModule(
        ctx,
        UnfollowSettings(True, True, 1, 10, 10, 0, True),
        android,
        continue_after_search_failure=True,
    )
    module.start()

    module.execute(ctx, None)

    assert android.usernames == ["non_follower"]
