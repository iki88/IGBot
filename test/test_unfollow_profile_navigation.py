from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from uuid import uuid4

from IGBot.runtime import RuntimeContext, SessionContext
from IGBot.runtime.database import FollowRecord, RuntimeDatabase
from IGBot.runtime.follow import AndroidContactScraper, AndroidFollowProvider
from IGBot.runtime.scheduler import ModuleExecutionOutcome
from IGBot.runtime.unfollow import (
    AllFollowingsUnfollowModule,
    AndroidFollowingListSearchUnfollowProvider,
    AndroidFollowingListUnfollowProvider,
    AndroidUnfollowResult,
    AndroidUnfollowStatus,
    FollowingListProfileRestorer,
    UnfollowModule,
    UnfollowSettings,
)


class Logger:
    def info(self, _message, **_fields):
        pass

    def warning(self, _message, **_fields):
        pass


def runtime_context(tmp_path):
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


def node(text="", resource_id="", description=""):
    return (
        f'<node text="{text}" resource-id="com.instagram.clone:id/{resource_id}" '
        f'content-desc="{description}" bounds="[0,0][100,100]" />'
    )


def hierarchy(*nodes):
    return "<hierarchy>" + "".join(nodes) + "</hierarchy>"


def profile(username="account"):
    return hierarchy(
        node(username, "action_bar_title"),
        node("100", "profile_header_familiar_following_value"),
        node(resource_id="row_profile_header_following_container"),
    )


def follow_list():
    return hierarchy(node(resource_id="unified_follow_list_view_pager"))


class Clock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


class Device:
    def __init__(self, hierarchies):
        self.hierarchies = list(hierarchies)
        self.current = self.hierarchies[-1]
        self.presses = []
        self.clicks = []

    def dump_hierarchy(self, compressed=False):
        assert not compressed
        if self.hierarchies:
            self.current = self.hierarchies.pop(0)
        return self.current

    def press(self, key):
        self.presses.append(key)

    def click(self, x, y):
        self.clicks.append((x, y))


def restorer(clock):
    android = AndroidFollowProvider(
        AndroidContactScraper(), sleeper=clock.sleep, clock=clock, navigation_wait=0
    )
    return FollowingListProfileRestorer(
        android, clock=clock, sleeper=clock.sleep, timeout=0.5, poll_interval=0.1
    )


def test_profile_restoration_returns_from_followers(tmp_path):
    clock = Clock()
    device = Device((follow_list(), profile()))

    assert restorer(clock).ensure_profile_page(runtime_context(tmp_path), device)
    assert device.presses == ["back"]


def test_profile_restoration_returns_from_following(tmp_path):
    clock = Clock()
    device = Device((follow_list(), profile()))

    assert restorer(clock).ensure_profile_page(runtime_context(tmp_path), device)
    assert device.presses == ["back"]


def test_profile_restoration_accepts_verified_profile_without_navigation(tmp_path):
    clock = Clock()
    device = Device((profile(),))

    assert restorer(clock).ensure_profile_page(runtime_context(tmp_path), device)
    assert not device.presses
    assert not device.clicks


def test_profile_restoration_uses_profile_navigation_from_search(tmp_path):
    clock = Clock()
    search = hierarchy(
        node(resource_id="action_bar_search_edit_text"),
        node(resource_id="profile_tab", description="profile"),
    )
    device = Device((search, profile()))

    assert restorer(clock).ensure_profile_page(runtime_context(tmp_path), device)
    assert len(device.clicks) == 1


def test_both_following_list_providers_share_profile_restorer(tmp_path):
    android = Mock()
    shared = Mock()
    sequential = AndroidFollowingListUnfollowProvider(android, profile_restorer=shared)
    searched = AndroidFollowingListSearchUnfollowProvider(
        android, profile_restorer=shared
    )

    assert sequential._profile_restorer is shared
    assert searched._profile_restorer is shared


class NavigationFailureAndroid:
    def execute_next(self, _context, _processed):
        return AndroidUnfollowResult(AndroidUnfollowStatus.NAVIGATION_FAILED)


class SearchNavigationFailureAndroid:
    def execute(self, _context, username):
        return AndroidUnfollowResult(
            AndroidUnfollowStatus.NAVIGATION_FAILED, username=username
        )


def test_all_followings_navigation_failure_enters_backoff(tmp_path):
    context = runtime_context(tmp_path)
    module = AllFollowingsUnfollowModule(
        context,
        UnfollowSettings(True, True, 1, 5, 5, 0),
        NavigationFailureAndroid(),
    )
    module.start()

    result = module.execute(context, None)

    assert result.outcome is ModuleExecutionOutcome.SCROLL_BLOCK


def test_following_list_search_navigation_failure_enters_backoff(tmp_path):
    context = runtime_context(tmp_path)
    followed_at = datetime.now(timezone.utc) - timedelta(days=10)
    with RuntimeDatabase(tmp_path) as database:
        user = database.users.create("target", followed_at, "FOLLOW")
        database.follow.save(FollowRecord(user.id, "target", "source", followed_at))
    module = UnfollowModule(
        context,
        UnfollowSettings(True, True, 1, 5, 5, 0),
        SearchNavigationFailureAndroid(),
        continue_after_search_failure=True,
    )
    module.start()

    result = module.execute(context, None)

    assert result.outcome is ModuleExecutionOutcome.SCROLL_BLOCK
