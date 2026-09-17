from datetime import datetime, timezone
from uuid import uuid4

from IGBot.runtime import RuntimeContext, SessionContext
from IGBot.runtime.candidates import DiscoveryStatus, FollowersDiscoverySettings
from IGBot.runtime.follow import AndroidFollowProvider
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
