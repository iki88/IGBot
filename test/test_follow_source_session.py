"""Source-session exploration contracts with a mocked Android boundary."""

import time
from types import SimpleNamespace

import pytest

from IGBot.runtime.candidates import (
    CandidateObservation,
    DiscoveryResult,
    DiscoveryStatus,
    FollowersDiscoverySettings,
)
from IGBot.runtime.follow import AndroidFollowProvider, AndroidFollowStatus
from IGBot.runtime.follow.source_session import FollowSourcesProvider, SourceSession
from IGBot.runtime.native_integration import AndroidFollowersDiscovery


@pytest.mark.parametrize("followers", (0, 2000, 6532, 9999, None))
def test_small_sources_never_choose_letters(followers):
    session = SourceSession()
    session.choose_strategy(followers)
    assert not session.letter_search


@pytest.mark.parametrize("followers", (10000, 218430))
def test_large_sources_always_choose_letters(followers):
    session = SourceSession()
    session.choose_strategy(followers)
    assert session.letter_search


@pytest.mark.parametrize(
    "followers, strategy", ((6532, "Scroll"), (218430, "Letter Search"))
)
def test_logged_follower_count_is_the_strategy_input(monkeypatch, followers, strategy):
    messages = []
    logger = SimpleNamespace(info=lambda message, **_: messages.append(message))
    android = SimpleNamespace(_device=lambda _: object())
    discovery = AndroidFollowersDiscovery(android, cancellation_requested=lambda: True)
    discovery._source_followers = followers
    discovery.next_follower(
        SimpleNamespace(logger=logger), "source", FollowersDiscoverySettings(30)
    )
    assert messages == [
        f"[Source] Followers detected: {followers:,}",
        f"[Source] Strategy: {strategy}",
    ]


def test_following_discovery_always_uses_scroll_strategy():
    messages = []
    logger = SimpleNamespace(info=lambda message, **_: messages.append(message))
    android = SimpleNamespace(_device=lambda _: object())
    discovery = AndroidFollowersDiscovery(
        android, following=True, cancellation_requested=lambda: True
    )
    discovery._source_followers = 218_430

    discovery.next_follower(
        SimpleNamespace(logger=logger), "source", FollowersDiscoverySettings(30)
    )

    assert discovery.session.letter_search is False
    assert messages == [
        "[Source] Following detected: 218,430",
        "[Source] Strategy: Scroll",
    ]


def test_letters_are_unique_and_failed_letters_reset_with_session():
    session = SourceSession(letter_search=True)
    letters = [
        session.next_letter("AAI", "EO", lambda values: values[0]) for _ in range(4)
    ]
    assert len(set(letters)) == 4
    session.failed_letters.add(letters[0])
    assert session.next_letter("AI", "EO") is None
    fresh = SourceSession()
    assert fresh.used_letters == fresh.failed_letters == set()
    assert fresh.next_letter("AI", "EO", lambda values: values[0]) == letters[0]


def test_first_letter_waits_for_results_and_next_letter_survives_old_scroll_timeout():
    messages = []

    class Device:
        letter = ""
        reads = 0

        def dump_hierarchy(self, compressed=False):
            self.reads += 1
            rows = ""
            # Instagram briefly returns an empty hierarchy after typing.
            if self.letter and self.reads > 2:
                rows = (
                    '<node resource-id="clone:id/follow_list_container">'
                    f'<node text="user_{self.letter}" resource-id="clone:id/follow_list_username"/>'
                    '<node text="Follow" resource-id="clone:id/follow_list_row_large_follow_button"/>'
                    "</node>"
                )
            return (
                '<hierarchy><node resource-id="clone:id/row_search_edit_text" bounds="[0,0][100,20]"/>'
                + rows
                + "</hierarchy>"
            )

        def click(self, *args):
            pass

        def send_keys(self, value, clear=False):
            self.letter = value
            self.reads = 0

    now = [0.0]
    device = Device()
    android = AndroidFollowProvider(
        object(),
        device_factory=lambda _: device,
        navigation_wait=0,
        clock=lambda: now[0],
        sleeper=lambda seconds: now.__setitem__(0, now[0] + seconds),
    )
    discovery = AndroidFollowersDiscovery(android)
    discovery._strategy_selected = True
    discovery.session.letter_search = True
    discovery._source_started = time.monotonic() - 1000
    original = discovery.session.next_letter
    discovery.session.next_letter = lambda a, b: original(
        a, b, lambda values: values[0]
    )
    android.scroll_followers = lambda _: SimpleNamespace(
        status=AndroidFollowStatus.SUCCESS
    )
    context = SimpleNamespace(
        logger=SimpleNamespace(info=lambda message, **_: messages.append(message)),
        session=SimpleNamespace(phone_id="phone"),
    )
    settings = FollowersDiscoverySettings(30, True, "AI", "O")
    first = discovery.next_follower(context, "source", settings)
    assert first.observation.username == "user_AO"
    assert "[Search] Letter completed." not in messages
    assert discovery.session.failed_letters == set()
    second = discovery.next_follower(context, "source", settings)
    assert second.observation.username == "user_IO"
    assert messages.count("[Search] Letter completed.") == 1
    assert discovery.session.failed_letters == set()


class Logger:
    def info(self, *args, **kwargs):
        pass

    warning = info


def test_source_summary_logging_repeats_after_rotation():
    messages = []
    context = SimpleNamespace(
        logger=SimpleNamespace(info=lambda message: messages.append(message))
    )

    class Discovery:
        session = SourceSession()

        def open_source(self, context, source):
            self.session = SourceSession()
            return True

        def next_follower(self, context, source, settings):
            if not self.session.evaluated:
                context.logger.info("[Source] Followers detected: 6,532")
                context.logger.info("[Source] Strategy: Scroll")
            return DiscoveryResult(
                DiscoveryStatus.ACCOUNT_FOUND, CandidateObservation("candidate")
            )

    provider = FollowSourcesProvider(
        ("first", "second"),
        Discovery(),
        SimpleNamespace(biography_required=False, accepts_visible=lambda *_: True),
        object(),
        FollowersDiscoverySettings(30),
    )
    provider.next_candidate(context)
    assert messages == [
        "[Source] Available configured sources: 2",
        "[Source] Randomly selected: first (1/2)",
        "[Source] Followers detected: 6,532",
        "[Source] Strategy: Scroll",
    ]
    for _ in range(50):
        provider.record_evaluated(context)
    provider.next_candidate(context)
    assert messages[4:] == [
        "[Source] Source Session finished (evaluated_profiles=50)",
        "[Source] Rotating to next source.",
        "[Source] Available configured sources: 2",
        "[Source] Randomly selected: second (2/2)",
        "[Source] Followers detected: 6,532",
        "[Source] Strategy: Scroll",
    ]


@pytest.mark.parametrize("sources, next_index", ((["a", "b"], 1), (["a"], 0)))
def test_rotation_only_after_exactly_50_evaluations(monkeypatch, sources, next_index):
    discovery = SimpleNamespace(session=SourceSession())
    provider = FollowSourcesProvider(sources, discovery, object(), object(), object())
    context = SimpleNamespace(logger=Logger())
    monkeypatch.setattr(
        "IGBot.runtime.candidates.providers.FollowersProvider.next_candidate",
        lambda *_: None,
    )
    provider._source_open = True
    for _ in range(49):
        provider.record_evaluated(context)
    provider.next_candidate(context)
    assert provider._source_index == 0
    assert provider._source_open
    provider.record_evaluated(context)
    provider.next_candidate(context)
    assert provider._source_index == next_index
    assert not provider._source_open
    assert discovery.session.evaluated == 0


def test_next_letter_restores_search_field_and_clears_text():
    class Device:
        def __init__(self):
            self.top = False
            self.actions = []

        def dump_hierarchy(self, compressed=False):
            if self.top:
                return '<hierarchy><node resource-id="com.instagram.androie:id/row_search_edit_text" bounds="[48,458][1032,564]" /></hierarchy>'
            return '<hierarchy><node scrollable="true" bounds="[0,20][100,200]" /></hierarchy>'

        def swipe(self, *args, **kwargs):
            self.actions.append("scroll to top")
            self.top = True

        def click(self, *args):
            self.actions.append("click")

        def send_keys(self, value, clear=False):
            self.actions.append((value, clear))

    device = Device()
    android = AndroidFollowProvider(
        object(), device_factory=lambda _: device, navigation_wait=0
    )
    discovery = AndroidFollowersDiscovery(android)
    context = SimpleNamespace(
        logger=Logger(), session=SimpleNamespace(phone_id="phone")
    )
    settings = FollowersDiscoverySettings(30, True, "A", "E")
    assert discovery._next_letter(context, settings, device)
    assert device.actions == [
        "scroll to top",
        "click",
        ("", True),
        ("AE", True),
    ]
    assert discovery.session.used_letters == {"AE"}


def test_next_letter_recovers_search_field_without_scrollable_node():
    class Device:
        def __init__(self):
            self.swipes = 0
            self.keys = []

        def dump_hierarchy(self, compressed=False):
            if self.swipes >= 2:
                return '<hierarchy><node resource-id="clone:id/row_search_edit_text" bounds="[48,458][1032,564]" /></hierarchy>'
            return '<hierarchy><node bounds="[0,0][1080,1776]" /></hierarchy>'

        def window_size(self):
            return 1080, 1776

        def swipe(self, *args, **kwargs):
            self.swipes += 1

        def click(self, *args):
            pass

        def send_keys(self, value, clear=False):
            self.keys.append((value, clear))

    device = Device()
    android = AndroidFollowProvider(
        object(),
        device_factory=lambda _: device,
        navigation_wait=0,
        sleeper=lambda _: None,
    )
    discovery = AndroidFollowersDiscovery(android)
    context = SimpleNamespace(
        logger=Logger(), session=SimpleNamespace(phone_id="phone")
    )

    assert discovery._next_letter(
        context, FollowersDiscoverySettings(30, True, "A", "E"), device
    )
    assert device.swipes == 2
    assert device.keys == [("", True), ("AE", True)]


def test_exhausted_letter_continues_with_next_unused_combination():
    messages = []

    class Device:
        letter = ""

        def dump_hierarchy(self, compressed=False):
            rows = ""
            if self.letter == "IO":
                rows = (
                    '<node resource-id="clone:id/follow_list_container">'
                    '<node text="next_candidate" resource-id="clone:id/follow_list_username"/>'
                    '<node text="Follow" resource-id="clone:id/follow_list_row_large_follow_button"/>'
                    "</node>"
                )
            return (
                '<hierarchy><node resource-id="clone:id/row_search_edit_text" bounds="[0,0][100,20]"/>'
                + rows
                + "</hierarchy>"
            )

        def click(self, *args):
            pass

        def send_keys(self, value, clear=False):
            self.letter = value

    now = [0.0]
    device = Device()
    android = AndroidFollowProvider(
        object(),
        device_factory=lambda _: device,
        navigation_wait=0,
        clock=lambda: now[0],
        sleeper=lambda seconds: now.__setitem__(0, now[0] + seconds),
    )
    discovery = AndroidFollowersDiscovery(android)
    discovery._strategy_selected = True
    discovery.session.letter_search = True
    original = discovery.session.next_letter
    discovery.session.next_letter = lambda a, b: original(
        a, b, lambda values: values[0]
    )
    context = SimpleNamespace(
        logger=SimpleNamespace(info=lambda message, **_: messages.append(message)),
        session=SimpleNamespace(phone_id="phone"),
    )

    result = discovery.next_follower(
        context, "source", FollowersDiscoverySettings(30, True, "AI", "O")
    )

    assert result.observation.username == "next_candidate"
    assert discovery.session.used_letters == {"AO", "IO"}
    assert messages.count("[Search] Letter completed.") == 1


@pytest.mark.parametrize("count", (1, 2, 5))
def test_zero_results_advance_letters_but_small_result_sets_are_returned(count):
    class Device:
        letter = ""

        def dump_hierarchy(self, compressed=False):
            rows = ""
            if self.letter == "IO":
                rows = "".join(
                    f'<node resource-id="clone:id/follow_list_container"><node text="candidate{i}" resource-id="clone:id/follow_list_username"/><node text="Follow" resource-id="clone:id/follow_list_row_large_follow_button"/></node>'
                    for i in range(count)
                )
            return (
                '<hierarchy><node resource-id="com.instagram.androie:id/row_search_edit_text" bounds="[48,458][1032,564]"/>'
                + rows
                + "</hierarchy>"
            )

        def click(self, *args):
            pass

        def send_keys(self, value, clear=False):
            self.letter = value

    device = Device()
    android = AndroidFollowProvider(
        object(), device_factory=lambda _: device, navigation_wait=0
    )
    discovery = AndroidFollowersDiscovery(android)
    discovery._strategy_selected = True
    discovery.session.letter_search = True
    context = SimpleNamespace(
        logger=Logger(), session=SimpleNamespace(phone_id="phone")
    )
    # Bind the choice explicitly: default callable was captured when defined.
    original = discovery.session.next_letter
    discovery.session.next_letter = lambda a, b: original(
        a, b, lambda values: values[0]
    )
    discovery._source_started = time.monotonic()
    results = [
        discovery.next_follower(
            context, "source", FollowersDiscoverySettings(30, True, "AI", "O")
        )
        for _ in range(count)
    ]
    assert [result.observation.username for result in results] == [
        f"candidate{i}" for i in range(count)
    ]
    assert discovery.session.failed_letters == {"AO"}
    assert discovery.session.used_letters == {"AO", "IO"}
