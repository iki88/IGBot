from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from uuid import uuid4
from xml.etree import ElementTree

from IGBot.runtime import RuntimeContext, SessionContext
from IGBot.runtime.database import FollowRecord, RuntimeDatabase
from IGBot.runtime.follow import AndroidContactScraper, AndroidFollowProvider
from IGBot.runtime.scheduler import ModuleExecutionOutcome
from IGBot.runtime.unfollow import (
    AndroidUnfollowProvider,
    AndroidUnfollowResult,
    AndroidUnfollowStatus,
    UnfollowModule,
    UnfollowSettings,
)


def node(text="", resource_id="", bounds="[0,0][100,100]"):
    return (
        f'<node text="{text}" resource-id="com.instagram.androie:id/{resource_id}" '
        f'bounds="{bounds}" content-desc="" />'
    )


def hierarchy(*nodes):
    return "<hierarchy>" + "".join(nodes) + "</hierarchy>"


def search_row(username):
    return (
        '<node resource-id="com.instagram.androie:id/row_search_user_container" '
        'bounds="[0,0][100,100]">'
        + node(username, "row_search_user_username")
        + "</node>"
    )


def profile(username, state="Following"):
    return hierarchy(
        node(username, "action_bar_title"),
        node(state, "profile_header_follow_button"),
    )


class Logger:
    def __init__(self):
        self.messages = []

    def _add(self, level, message, **fields):
        self.messages.append((level, message, fields))

    def debug(self, message, **fields):
        self._add("debug", message, **fields)

    def info(self, message, **fields):
        self._add("info", message, **fields)

    def warning(self, message, **fields):
        self._add("warning", message, **fields)

    def error(self, message, **fields):
        self._add("error", message, **fields)


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class Device:
    def __init__(self, hierarchies):
        self.hierarchies = list(hierarchies)
        self.current = self.hierarchies[-1]
        self.clicks = []
        self.keys = []

    def dump_hierarchy(self, compressed=False):
        assert not compressed
        if self.hierarchies:
            self.current = self.hierarchies.pop(0)
        return self.current

    def click(self, x, y):
        self.clicks.append((x, y))

    def send_keys(self, value, clear=False):
        self.keys.append((value, clear))

    def press(self, _key):
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


def android_provider(device, clock):
    search = AndroidFollowProvider(
        AndroidContactScraper(),
        device_factory=lambda _serial: device,
        sleeper=clock.sleep,
        clock=clock,
        navigation_wait=0,
        search_timeout=2,
        search_poll_interval=0.1,
        search_settle_delay=lambda: 0.5,
    )
    return AndroidUnfollowProvider(
        search, clock=clock, sleeper=clock.sleep, timeout=2, poll_interval=0.1
    )


def search_prefix(username):
    return (
        hierarchy(node(resource_id="search_tab")),
        hierarchy(node(resource_id="action_bar_search_edit_text")),
        hierarchy(search_row(username)),
        hierarchy(node(username, "action_bar_title")),
        profile(username),
    )


def test_android_unfollow_public_profile_is_verified(tmp_path):
    username = "target_user"
    device = Device(
        search_prefix(username)
        + (
            hierarchy(node("Unfollow", "follow_sheet_unfollow_row")),
            profile(username, "Follow"),
        )
    )
    result = android_provider(device, Clock()).execute(context(tmp_path), username)

    assert result.status is AndroidUnfollowStatus.SUCCESS
    assert device.keys == [(username, True)]


def test_android_unfollow_handles_private_confirmation_dialog(tmp_path):
    username = "private_user"
    dialog = hierarchy(
        node(resource_id="dialog_container"), node("Unfollow", "primary_button")
    )
    device = Device(
        search_prefix(username)
        + (
            hierarchy(node("Unfollow", "follow_sheet_unfollow_row")),
            dialog,
            profile(username, "Follow"),
        )
    )
    ctx = context(tmp_path)
    result = android_provider(device, Clock()).execute(ctx, username)

    assert result.status is AndroidUnfollowStatus.SUCCESS
    assert any(
        message == "[Unfollow] Confirmation dialog detected."
        for _level, message, _fields in ctx.logger.messages
    )


def test_relationship_menu_first_tap_success(tmp_path):
    provider = android_provider(Device((hierarchy(),)), Clock())
    provider._search._tap = Mock()
    menu = ElementTree.fromstring(node("Unfollow", "follow_sheet_unfollow_row"))
    provider._wait_for_id = Mock(return_value=menu)
    ctx = context(tmp_path)

    result = provider._open_relationship_menu(ctx, object(), object())

    assert result is menu
    assert provider._search._tap.call_count == 1
    assert provider._wait_for_id.call_count == 1


def test_relationship_menu_retries_one_ignored_tap(tmp_path):
    provider = android_provider(Device((hierarchy(),)), Clock())
    provider._search._tap = Mock()
    menu = ElementTree.fromstring(node("Unfollow", "follow_sheet_unfollow_row"))
    provider._wait_for_id = Mock(side_effect=(None, menu))
    ctx = context(tmp_path)

    result = provider._open_relationship_menu(ctx, object(), object())

    assert result is menu
    assert provider._search._tap.call_count == 2
    assert provider._wait_for_id.call_count == 2
    assert any(
        message == "[Unfollow] Relationship menu not detected. Retrying..."
        for _level, message, _fields in ctx.logger.messages
    )


def test_relationship_menu_starts_recovery_after_two_failed_attempts(tmp_path):
    provider = android_provider(Device((hierarchy(),)), Clock())
    provider._search._tap = Mock()
    provider._wait_for_id = Mock(side_effect=(None, None))
    ctx = context(tmp_path)

    result = provider._open_relationship_menu(ctx, object(), object())

    assert result is None
    assert provider._search._tap.call_count == 2
    assert provider._wait_for_id.call_count == 2
    assert any(
        message == "[Unfollow] Relationship menu unavailable. Starting recovery."
        for _level, message, _fields in ctx.logger.messages
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


def test_unfollow_module_selects_delayed_record_and_updates_only_after_success(
    tmp_path,
):
    now = datetime.now(timezone.utc)
    with RuntimeDatabase(tmp_path) as database:
        old_id = seed_follow(database, "old_user", now - timedelta(days=10))
        seed_follow(database, "recent_user", now - timedelta(days=1))
        seed_follow(database, "done_user", now - timedelta(days=20), unfollowed=True)
    ctx = context(tmp_path)
    android = StubAndroid(AndroidUnfollowStatus.SUCCESS)
    module = UnfollowModule(ctx, UnfollowSettings(True, True, 1, 10, 10, 5), android)
    module.start()

    result = module.execute(ctx, None)

    assert result.outcome is ModuleExecutionOutcome.SUCCESS
    assert android.usernames == ["old_user"]
    with RuntimeDatabase(tmp_path) as database:
        record = database.follow.get(old_id)
        assert record.unfollowed
        assert record.unfollow_date is not None


def test_unfollow_module_does_not_persist_failed_verification(tmp_path):
    now = datetime.now(timezone.utc)
    with RuntimeDatabase(tmp_path) as database:
        user_id = seed_follow(database, "target", now - timedelta(days=10))
    ctx = context(tmp_path)
    module = UnfollowModule(
        ctx,
        UnfollowSettings(True, True, 1, 10, 10, 0),
        StubAndroid(AndroidUnfollowStatus.VERIFICATION_FAILED),
    )
    module.start()

    module.execute(ctx, None)

    with RuntimeDatabase(tmp_path) as database:
        assert not database.follow.get(user_id).unfollowed
