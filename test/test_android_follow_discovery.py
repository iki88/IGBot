from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from IGBot.runtime import RuntimeContext, SessionContext
from IGBot.runtime.candidates import DiscoveryStatus, FollowersDiscoverySettings
from IGBot.runtime.follow import AndroidFollowProvider
from IGBot.runtime.follow.fast_filters import FollowFastFilters
from IGBot.runtime.native_integration import AndroidFollowersDiscovery


class Logger:
    def __init__(self):
        self.messages = []

    def debug(self, message, **fields):
        self.messages.append((message, fields))

    info = debug
    warning = debug
    error = debug


class Device:
    def __init__(self, hierarchy):
        self.hierarchy = hierarchy

    def dump_hierarchy(self, compressed=False):
        assert compressed is False
        return self.hierarchy


def context(tmp_path):
    return RuntimeContext(
        SessionContext(
            uuid4(),
            "operator",
            "phone",
            "com.instagram.clone",
            tmp_path,
            datetime.now(timezone.utc),
        ),
        Logger(),
    )


def row(username, button):
    return f"""<node resource-id="com.instagram.androie:id/follow_list_container">
      <node text="{username}" resource-id="com.instagram.androie:id/follow_list_username" />
      <node text="{button}" resource-id="com.instagram.androie:id/follow_list_row_large_follow_button" />
    </node>"""


def discovery(tmp_path, rows, *, follow_back_enabled=False):
    device = Device(f"<hierarchy>{''.join(rows)}</hierarchy>")
    android = AndroidFollowProvider(
        object(), device_factory=lambda _serial: device, navigation_wait=0
    )
    return AndroidFollowersDiscovery(android, follow_back_enabled=follow_back_enabled)


SETTINGS = FollowersDiscoverySettings(scrolling_timeout_seconds=30)


def test_message_rows_are_skipped_before_opening_a_profile(tmp_path):
    runtime_context = context(tmp_path)
    provider = discovery(
        tmp_path,
        [row("already_followed", "Message"), row("eligible", "Follow")],
    )

    result = provider.next_follower(runtime_context, "source", SETTINGS)

    assert result.status is DiscoveryStatus.ACCOUNT_FOUND
    assert result.observation.username == "eligible"
    assert (
        "[Candidate] Skipping already-followed account",
        {"button": "Message", "username": "already_followed"},
    ) in runtime_context.logger.messages


def test_follow_back_row_respects_follow_setting(tmp_path):
    disabled_context = context(tmp_path)
    disabled = discovery(
        tmp_path,
        [row("follower", "Follow back"), row("eligible", "Follow")],
    )
    enabled_context = context(tmp_path)
    enabled = discovery(
        tmp_path, [row("follower", "Follow back")], follow_back_enabled=True
    )

    skipped = disabled.next_follower(disabled_context, "source", SETTINGS)
    accepted = enabled.next_follower(enabled_context, "source", SETTINGS)

    assert skipped.observation.username == "eligible"
    assert accepted.observation.username == "follower"


def test_see_more_is_clicked_before_suggested_boundary_stops_discovery(tmp_path):
    collapsed = (
        "<hierarchy>"
        + row("already_seen", "Message")
        + '<node text="See more" resource-id="clone:id/see_more_button" bounds="[0,100][100,140]"/>'
        + '<node text="Suggested for you" resource-id="clone:id/row_header_textview"/>'
        + row("suggested_account", "Follow")
        + "</hierarchy>"
    )
    expanded = (
        "<hierarchy>"
        + row("real_follower", "Follow")
        + '<node text="Suggested for you" resource-id="clone:id/row_header_textview"/>'
        + row("suggested_account", "Follow")
        + "</hierarchy>"
    )

    class ExpandingDevice:
        def __init__(self):
            self.hierarchy = collapsed
            self.clicks = []

        def dump_hierarchy(self, compressed=False):
            return self.hierarchy

        def click(self, x, y):
            self.clicks.append((x, y))
            self.hierarchy = expanded

    device = ExpandingDevice()
    android = AndroidFollowProvider(
        object(), device_factory=lambda _: device, navigation_wait=0
    )
    provider = AndroidFollowersDiscovery(android)

    result = provider.next_follower(context(tmp_path), "source", SETTINGS)

    assert result.status is DiscoveryStatus.ACCOUNT_FOUND
    assert result.observation.username == "real_follower"
    assert device.clicks == [(50, 120)]


def test_suggested_rows_are_never_discovery_candidates(tmp_path):
    provider = discovery(
        tmp_path,
        [
            row("already_seen", "Message"),
            '<node text="Suggested for you" resource-id="clone:id/row_header_textview"/>',
            row("suggested_account", "Follow"),
        ],
    )

    result = provider.next_follower(context(tmp_path), "source", SETTINGS)

    assert result.status is DiscoveryStatus.SOURCE_EXHAUSTED


def test_fast_filters_skip_literal_subtitles_and_return_next_row(tmp_path):
    # Reduced rows from the inspected Followers hierarchy: subtitle is distinct
    # from the username and is not inferred from a profile or an image.
    rows = [
        row("einfach_nur_dori", "Follow").replace(
            "</node>",
            '<node text="Dori" resource-id="com.instagram.androie:id/follow_list_subtitle"/></node>',
            1,
        ),
        row("fara_nails", "Follow").replace(
            "</node>",
            '<node text="Fara_nails" resource-id="com.instagram.androie:id/follow_list_subtitle"/></node>',
            1,
        ),
    ]
    provider = discovery(tmp_path, rows)
    provider._fast_filters = FollowFastFilters(blocked_words=("DORI",))
    runtime_context = context(tmp_path)
    result = provider.next_follower(runtime_context, "source", SETTINGS)
    assert result.observation.username == "fara_nails"
    assert result.observation.display_name == "Fara_nails"
    assert (
        "[FastFilter] Blocked keyword detected.",
        {},
    ) in runtime_context.logger.messages


def test_fast_alphabets_ignore_username_and_skip_unsupported_subtitle(tmp_path):
    rows = [
        row("latin_username", "Follow").replace(
            "</node>",
            '<node text="Ирина" resource-id="com.instagram.androie:id/follow_list_subtitle"/></node>',
            1,
        ),
        row("another_latin_username", "Follow"),
    ]
    provider = discovery(tmp_path, rows)
    provider._fast_filters = FollowFastFilters(allowed_alphabets=("latin",))
    runtime_context = context(tmp_path)
    result = provider.next_follower(runtime_context, "source", SETTINGS)
    assert result.observation.username == "another_latin_username"
    assert (
        "[FastFilter] Allowed alphabet rejected.",
        {},
    ) in runtime_context.logger.messages
    # A Latin username does not invalidate an allowed Cyrillic subtitle.
    assert FollowFastFilters(allowed_alphabets=("cyrillic",)).accepts(
        runtime_context, "Ирина"
    )


def test_fast_filters_never_require_missing_profile_information(tmp_path):
    runtime_context = context(tmp_path)
    fast = FollowFastFilters(allowed_alphabets=("latin",), blocked_words=("giveaway",))
    assert fast.accepts(runtime_context, "")
    assert fast.accepts(runtime_context, "Junior🇧🇷")
    assert fast.accepts(
        runtime_context, "Zwischen Bergen & Herzblut - einfach echt Lina"
    )
    assert runtime_context.logger.messages == []


def test_inspected_story_ring_structure_drives_active_story_fast_filter(tmp_path):
    hierarchy = Path("snapshots/R5CR61HA38V/2026-09-17_22-44-28.xml").read_text(
        encoding="utf-8"
    )
    provider = discovery(tmp_path, [])
    rows = {
        username: active
        for username, _button, _subtitle, active in provider._follower_rows(hierarchy)
    }
    assert rows["einfach_nur_dori"] is False
    assert rows["moosen.beirin"] is True

    runtime_context = context(tmp_path)
    fast = FollowFastFilters(only_active_stories=True)
    assert not fast.accepts(
        runtime_context, "Dori", "einfach_nur_dori", has_active_story=False
    )
    assert fast.accepts(runtime_context, "Lina", "moosen.beirin", has_active_story=True)
    assert (
        "[FastFilter] Active story required. Candidate skipped.",
        {},
    ) in runtime_context.logger.messages
    assert (
        "[FastFilter] Active story detected.",
        {},
    ) in runtime_context.logger.messages


def test_disabled_active_story_filter_preserves_candidates_without_story(tmp_path):
    runtime_context = context(tmp_path)
    assert FollowFastFilters().accepts(
        runtime_context, "Dori", "einfach_nur_dori", has_active_story=False
    )
    assert runtime_context.logger.messages == []


def test_fast_blocked_keyword_in_username_skips_to_next_candidate(tmp_path):
    provider = discovery(
        tmp_path, [row("giveaway_account", "Follow"), row("eligible", "Follow")]
    )
    provider._fast_filters = FollowFastFilters(blocked_words=("GIVEAWAY",))
    runtime_context = context(tmp_path)
    result = provider.next_follower(runtime_context, "source", SETTINGS)
    assert result.observation.username == "eligible"
    assert (
        "[FastFilter] Blocked keyword detected.",
        {},
    ) in runtime_context.logger.messages


def test_required_row_matches_are_positive_only_and_alphabets_ignore_username(
    tmp_path, mocker
):
    runtime_context = context(tmp_path)
    fast = FollowFastFilters(
        allowed_alphabets=("cyrillic",), required_words=("rescue",)
    )
    spy = mocker.spy(fast, "required_keyword_visible")
    assert fast.accepts(runtime_context, "Ирина", "rescue_account")
    assert spy.spy_return is True
    assert fast.accepts(runtime_context, "Ирина", "other_account")
    assert spy.spy_return is False
    assert runtime_context.logger.messages == []
    subtitle_match = FollowFastFilters(required_words=("Dori",))
    assert subtitle_match.accepts(runtime_context, "Dori", "ordinary_username")
    assert subtitle_match.required_keyword_visible("ordinary_username dori")
