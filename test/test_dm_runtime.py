from datetime import datetime, timezone
from html import escape
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pytest

from IGBot.runtime import RuntimeContext, SessionContext
from IGBot.runtime.action_delay import ActionDelay
from IGBot.runtime.database import FollowRecord, RuntimeDatabase
from IGBot.runtime.dm import (
    AndroidDMProvider,
    AndroidDMResult,
    AndroidDMStatus,
    DMMessageRenderer,
    DMModule,
    DMSettings,
    SpecificDMPersistence,
    SpecificDMRecipients,
    SpecificDMSynchronizer,
)
from IGBot.runtime.follow import (
    AndroidContactScraper,
    AndroidFollowProvider,
    AndroidFollowStatus,
)
from IGBot.runtime.follow.android_models import AndroidFollowResult
from IGBot.runtime.ignore import IgnoreService
from IGBot.runtime.modules import InteractionModule
from IGBot.runtime.native_integration import _FollowModuleProvider
from IGBot.runtime.navigation import NavigationResult, NavigationStatus
from IGBot.runtime.scheduler import ExecutionBudget, ModuleExecutionOutcome


def node(text="", resource_id="", description="", bounds="[0,0][100,100]"):
    return (
        f'<node text="{escape(text, quote=True)}" '
        f'resource-id="com.instagram.android:id/{resource_id}" '
        f'content-desc="{escape(description, quote=True)}" bounds="{bounds}" />'
    )


def test_action_delay_uses_interruptible_runtime_wait():
    waits = []
    sleeps = []
    delay = ActionDelay(
        30,
        selector=lambda _minimum, _maximum: 30,
        sleeper=sleeps.append,
    )

    elapsed = delay.wait(
        lambda: True,
        cancellation_wait=lambda seconds: waits.append(seconds) or True,
    )

    assert elapsed == 30
    assert waits == [30]
    assert sleeps == []


def hierarchy(*nodes):
    return "<hierarchy>" + "".join(nodes) + "</hierarchy>"


def search_row(username):
    return (
        '<node resource-id="com.instagram.android:id/row_search_user_container" '
        'bounds="[0,0][100,100]">'
        + node(username, "row_search_user_username")
        + "</node>"
    )


def profile(username, *, message=True):
    nodes = [node(username, "action_bar_title")]
    if message:
        nodes.append(node(resource_id="button_container", description="Message"))
    return hierarchy(*nodes)


def private_profile(username):
    return hierarchy(
        node(username, "action_bar_title"),
        node(description="Options"),
        node(
            "This account is private", "row_profile_header_empty_profile_notice_title"
        ),
    )


def private_options_sheet():
    return hierarchy(
        node(resource_id="bottom_sheet_container"),
        node(resource_id="action_sheet_container"),
        node("Send message", "action_sheet_row_text_view"),
    )


def thread(composer="Message…", *, outgoing=None):
    nodes = [
        node(resource_id="direct_thread_header"),
        node(resource_id="message_thread_container"),
        node(resource_id="message_composer_bar"),
        node(composer, "row_thread_composer_edittext"),
    ]
    if composer not in {"", "Message…"}:
        nodes.append(
            node(
                resource_id="row_thread_composer_send_button_container",
                description="Send",
            )
        )
    if outgoing is not None:
        nodes.append(node(outgoing))
    return hierarchy(*nodes)


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
        self.keys = []
        self.clicks = []

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


def context(tmp_path, ignored=()):
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
        ignore_service=IgnoreService(frozenset(ignored)),
    )


def provider(device, clock):
    search = AndroidFollowProvider(
        AndroidContactScraper(),
        device_factory=lambda _serial: device,
        sleeper=clock.sleep,
        clock=clock,
        navigation_wait=0,
        search_timeout=2,
        search_poll_interval=0.1,
        search_settle_delay=lambda: 0,
    )
    return AndroidDMProvider(
        search, sleeper=clock.sleep, clock=clock, timeout=1, poll_interval=0.1
    )


@pytest.mark.parametrize(
    "filename",
    (
        "2026-09-27_19-48-48.xml",
        "2026-09-27_19-49-25.xml",
        "2026-09-27_19-50-44.xml",
    ),
)
def test_production_profile_snapshots_expose_verified_message_button(filename):
    xml = (
        Path(__file__).parents[1] / "snapshots" / "R5CR61HA38V" / filename
    ).read_text(encoding="utf-8")
    android = provider(Device((xml,)), Clock())
    nodes = android._search._nodes(xml)

    assert android._search._profile_username(nodes)
    assert android._message_button(nodes) is not None


@pytest.mark.parametrize(
    "filename",
    (
        "2026-09-27_19-46-54.xml",
        "2026-09-27_19-47-24.xml",
        "2026-09-27_19-47-38.xml",
        "2026-09-27_19-49-41.xml",
        "2026-09-27_19-50-10.xml",
        "2026-09-28_17-05-54.xml",
        "2026-09-28_17-06-43.xml",
        "2026-09-28_17-06-56.xml",
    ),
)
def test_production_thread_snapshots_expose_verified_thread_and_composer(filename):
    xml = (
        Path(__file__).parents[1] / "snapshots" / "R5CR61HA38V" / filename
    ).read_text(encoding="utf-8")
    android = provider(Device((xml,)), Clock())

    assert android._thread_open(android._search._nodes(xml))


def test_production_private_profile_and_options_sheet_selectors():
    root = Path(__file__).parents[1] / "snapshots" / "R5CR61HA38V"
    android = provider(Device((hierarchy(),)), Clock())
    profile_xml = (root / "2026-09-28_17-02-28.xml").read_text(encoding="utf-8")
    sheet_xml = (root / "2026-09-28_17-05-17.xml").read_text(encoding="utf-8")
    profile_nodes = android._search._nodes(profile_xml)
    sheet_nodes = android._search._nodes(sheet_xml)

    assert android._is_private(profile_nodes)
    assert any(node.description == "Options" for node in profile_nodes)
    assert android._search._find_by_id(sheet_nodes, android._PRIVATE_OPTIONS_SHEET_IDS)
    assert any(
        node.resource_id.endswith("/action_sheet_row_text_view")
        and node.text == "Send message"
        for node in sheet_nodes
    )


def search_prefix(username):
    return (
        hierarchy(node(resource_id="search_tab")),
        hierarchy(node(resource_id="action_bar_search_edit_text")),
        hierarchy(search_row(username)),
        profile(username),
        profile(username),
    )


def test_android_dm_sends_only_after_verified_profile_thread_and_text(tmp_path):
    username = "new.follower"
    message = "Welcome!"
    device = Device(
        search_prefix(username)
        + (
            thread(),
            thread(),
            thread(message),
            thread(message),
            thread(outgoing=message),
        )
    )

    result = provider(device, Clock()).execute(context(tmp_path), username, message)

    assert result.status is AndroidDMStatus.SUCCESS
    assert device.keys == [(username, True), (message, True)]


def test_android_dm_records_missing_message_button_without_opening_thread(tmp_path):
    username = "no.message"
    device = Device(search_prefix(username)[:-1] + (profile(username, message=False),))

    result = provider(device, Clock()).execute(context(tmp_path), username, "Hello")

    assert result.status is AndroidDMStatus.MESSAGE_BUTTON_NOT_FOUND


def test_android_dm_private_profile_uses_options_send_message_fallback(tmp_path):
    username = "private.user"
    message = "Welcome"
    device = Device(
        search_prefix(username)[:-1]
        + (
            private_profile(username),
            private_options_sheet(),
            thread(),
            thread(),
            thread(message),
            thread(message),
            thread(outgoing=message),
        )
    )
    android = provider(device, Clock())

    result = android._execute(
        context(tmp_path),
        username,
        message,
        private_fallback=True,
        bounded_search=True,
    )

    assert result.status is AndroidDMStatus.SUCCESS


def test_dm_search_recovery_is_bounded_and_handles_thread_then_profile(tmp_path):
    search = Mock()
    search._device.return_value = Mock()
    search._nodes.return_value = ()
    search._find_by_id.return_value = None
    search.return_to_search.side_effect = (
        AndroidFollowResult(AndroidFollowStatus.FOLLOW_FAILED),
        AndroidFollowResult(AndroidFollowStatus.SUCCESS),
    )
    android = AndroidDMProvider(search)

    assert android._restore_search(context(tmp_path))
    assert search.return_to_search.call_count == 2


class StubAndroid:
    def __init__(self, results):
        self.results = list(results)
        self.usernames = []
        self.messages = []

    def execute(self, _context, username, message, **_options):
        self.usernames.append(username)
        self.messages.append(message)
        return self.results.pop(0)


def test_native_dm_spintax_supports_multiple_blocks_without_changing_layout():
    choices = iter(("Hi", "Thank you"))
    renderer = DMMessageRenderer(lambda _options: next(choices))

    rendered = renderer.render("{Hello|Hi} 👋\n\n{Thanks|Thank you} for following.")

    assert rendered == "Hi 👋\n\nThank you for following."


def test_dm_module_renders_once_per_recipient_and_persists_rendered_message(tmp_path):
    with RuntimeDatabase(tmp_path) as database:
        user_id = seed_follow_back(database, "render.user")
    ctx = context(tmp_path)
    android = StubAndroid((AndroidDMResult(AndroidDMStatus.SUCCESS),))
    renderer = DMMessageRenderer(lambda options: options[-1])
    module = DMModule(
        ctx,
        DMSettings(True, True, "{Hello|Hi}\nWelcome 😊", 1, 5, 5),
        android,
        message_renderer=renderer,
    )
    module.start()

    module.execute(ctx, None)

    assert android.messages == ["Hi\nWelcome 😊"]
    with RuntimeDatabase(tmp_path) as database:
        assert database.dm.get(user_id).last_message == "Hi\nWelcome 😊"


def seed_follow_back(database, username, source="source"):
    user = database.users.create(username, "2026-09-27 10:00:00", "FOLLOW")
    database.follow.save(
        FollowRecord(
            user.id,
            username,
            source,
            follow_date="2026-09-27 10:00:00",
            follow_back=True,
            follow_back_date="2026-09-27 11:00:00",
        )
    )
    return user.id


def test_dm_module_skips_ignored_and_persists_only_verified_success(tmp_path):
    with RuntimeDatabase(tmp_path) as database:
        ignored_id = seed_follow_back(database, "ignored.user")
        allowed_id = seed_follow_back(database, "allowed.user")
    ctx = context(tmp_path, ignored=("ignored.user",))
    android = StubAndroid((AndroidDMResult(AndroidDMStatus.SUCCESS),))
    module = DMModule(ctx, DMSettings(True, True, "Welcome", 1, 5, 5), android)
    module.start()

    result = module.execute(ctx, None)

    assert result.outcome is ModuleExecutionOutcome.SUCCESS
    assert android.usernames == ["allowed.user"]
    with RuntimeDatabase(tmp_path) as database:
        assert database.dm.get(ignored_id) is None
        saved = database.dm.get(allowed_id)
        assert saved.dm_count == 1
        assert saved.last_message == "Welcome"
        assert saved.status == "SUCCESS"


def test_dm_module_failure_status_does_not_exclude_future_retry(tmp_path):
    with RuntimeDatabase(tmp_path) as database:
        user_id = seed_follow_back(database, "retry.user")
    ctx = context(tmp_path)
    module = DMModule(
        ctx,
        DMSettings(True, True, "Welcome", 1, 5, 5),
        StubAndroid((AndroidDMResult(AndroidDMStatus.SEND_FAILED),)),
    )
    module.start()

    module.execute(ctx, None)

    with RuntimeDatabase(tmp_path) as database:
        assert database.dm.get(user_id).status == "SEND_FAILED"
        assert database.dm.eligible_new_followers() == (
            (user_id, "retry.user", "source"),
        )


def test_verified_dm_persists_success_but_returns_navigation_failure(tmp_path):
    with RuntimeDatabase(tmp_path) as database:
        user_id = seed_follow_back(database, "handoff.user")
    ctx = context(tmp_path)
    module = DMModule(
        ctx,
        DMSettings(True, True, "Welcome", 1, 5, 5),
        StubAndroid(
            (
                AndroidDMResult(
                    AndroidDMStatus.SUCCESS,
                    navigation=NavigationResult(
                        NavigationStatus.FAILED,
                        "Search could not be restored.",
                        expected="Instagram Search",
                        actual="Unknown",
                    ),
                ),
            )
        ),
    )
    module.start()

    result = module.execute(ctx, None)

    assert result.outcome is ModuleExecutionOutcome.NAVIGATION_FAILED
    assert result.verified_successes == 1
    with RuntimeDatabase(tmp_path) as database:
        saved = database.dm.get(user_id)
        assert saved.status == "SUCCESS"
        assert saved.dm_count == 1


def test_dm_module_uses_resolved_target_and_delays_only_between_successes(tmp_path):
    with RuntimeDatabase(tmp_path) as database:
        first_id = seed_follow_back(database, "first.user")
        failed_id = seed_follow_back(database, "failed.user")
        second_id = seed_follow_back(database, "second.user")
    ctx = context(tmp_path)
    android = StubAndroid(
        (
            AndroidDMResult(AndroidDMStatus.SUCCESS),
            AndroidDMResult(AndroidDMStatus.SEND_FAILED),
            AndroidDMResult(AndroidDMStatus.SUCCESS),
        )
    )
    delays = []
    action_delay = ActionDelay(
        "4-8", selector=lambda minimum, maximum: 6.5, sleeper=delays.append
    )
    module = DMModule(
        ctx,
        DMSettings(True, True, "Welcome", "2-4", 10, 10, "4-8"),
        android,
        action_delay=action_delay,
    )
    module.start()
    budget = ExecutionBudget(InteractionModule.DM, "2-4", 2, 10, 2)

    result = module.execute(ctx, budget)

    assert result.outcome is ModuleExecutionOutcome.SUCCESS
    assert result.verified_successes == 2
    assert module.session_complete
    assert module.daily_remaining == 8
    assert android.usernames == ["first.user", "failed.user", "second.user"]
    assert delays == [6.5]
    with RuntimeDatabase(tmp_path) as database:
        assert database.dm.get(first_id).dm_count == 1
        assert database.dm.get(failed_id).dm_count == 0
        assert database.dm.get(second_id).dm_count == 1


def test_dm_daily_limit_counts_only_success_and_stops_only_dm_module(tmp_path):
    with RuntimeDatabase(tmp_path) as database:
        seed_follow_back(database, "failed.user")
        seed_follow_back(database, "first.user")
        seed_follow_back(database, "second.user")
    ctx = context(tmp_path)
    android = StubAndroid(
        (
            AndroidDMResult(AndroidDMStatus.SEND_FAILED),
            AndroidDMResult(AndroidDMStatus.SUCCESS),
            AndroidDMResult(AndroidDMStatus.SUCCESS),
        )
    )
    delays = []
    module = DMModule(
        ctx,
        DMSettings(True, True, "Welcome", 5, 2, 10, 0),
        android,
        action_delay=ActionDelay(0, sleeper=delays.append),
    )
    module.start()
    budget = ExecutionBudget(InteractionModule.DM, "5", 5, 2, 2)

    result = module.execute(ctx, budget)

    assert result.outcome is ModuleExecutionOutcome.DAILY_LIMIT_REACHED
    assert result.verified_successes == 2
    assert module.daily_remaining == 0
    assert len(android.usernames) == 3
    assert delays == []


def test_specific_dm_sync_normalizes_deduplicates_and_excludes_ignored(tmp_path):
    lists = tmp_path / "Lists"
    lists.mkdir()
    (lists / "dmspecific.txt").write_text(
        " First.User \nfirst.user\nIGNORED.USER\nsecond_user\n\n",
        encoding="utf-8",
    )

    synchronized = SpecificDMSynchronizer().synchronize(
        tmp_path, IgnoreService(frozenset(("ignored.user",)))
    )

    assert synchronized == ("first.user", "second_user")
    with RuntimeDatabase(tmp_path) as database:
        assert database.specific_dm.pending_dm_users() == (
            (1, "first.user"),
            (2, "second_user"),
        )


def test_specific_dm_success_is_skipped_and_failure_waits_for_future_session(tmp_path):
    lists = tmp_path / "Lists"
    lists.mkdir()
    (lists / "dmspecific.txt").write_text("first\nsecond\n", encoding="utf-8")
    SpecificDMSynchronizer().synchronize(tmp_path)
    ctx = context(tmp_path)
    android = StubAndroid(
        (
            AndroidDMResult(AndroidDMStatus.SEND_FAILED),
            AndroidDMResult(AndroidDMStatus.SUCCESS),
        )
    )
    module = DMModule(
        ctx,
        DMSettings(True, True, "Welcome", 1, 5, 5),
        android,
        recipients=SpecificDMRecipients(),
        persistence=SpecificDMPersistence(),
        private_fallback=True,
        bounded_search=True,
    )
    module.start()
    module.execute(ctx, None)
    module.mark_ready()
    module.start()
    module.execute(ctx, None)

    assert android.usernames == ["first", "second"]
    with RuntimeDatabase(tmp_path) as database:
        rows = database._connection.execute(
            "SELECT username, dm_count, status FROM specific_dm ORDER BY user_id"
        ).fetchall()
        assert [tuple(row) for row in rows] == [
            ("first", 0, "SEND_FAILED"),
            ("second", 1, "SUCCESS"),
        ]
        assert database.specific_dm.pending_dm_users() == ((1, "first"),)


def test_native_module_provider_composes_enabled_welcome_dm(tmp_path):
    messages = tmp_path / "Messages"
    messages.mkdir()
    (messages / "welcome_dm.txt").write_text("Hello\nWelcome", encoding="utf-8")
    ctx = context(tmp_path)
    modules = _FollowModuleProvider(
        {
            "pm-percentage": "1",
            "total-pm-limit": "5",
            "igbot-dm-budget": "2-4",
            "igbot-dm-action-delay": "10-20",
        },
        {},
        {"maximum_dms_per_hour": 10},
        Mock(),
        Mock(),
    ).modules_for(ctx)

    dm = next(module for module in modules if module.module.value == "DM")
    assert dm.enabled
    assert dm.daily_remaining == 5
    assert dm.hourly_remaining == 10
    assert dm._settings.message == "Hello\nWelcome"
    assert dm.budget_configuration == "2-4"
    assert dm._settings.action_delay == "10-20"


def test_native_module_provider_loads_exact_welcome_dm_message_file(tmp_path):
    messages = tmp_path / "Messages"
    messages.mkdir()
    expected = "  Hello 😊\n\nWelcome  "
    (messages / "welcome_dm.txt").write_text(expected, encoding="utf-8")
    ctx = context(tmp_path)

    modules = _FollowModuleProvider(
        {"pm-percentage": "1", "total-pm-limit": "5"},
        {},
        {"maximum_dms_per_hour": 10},
        Mock(),
        Mock(),
    ).modules_for(ctx)

    dm = next(module for module in modules if module.module.value == "DM")
    assert dm._settings.message == expected


@pytest.mark.parametrize("message", ("", " \n\t "))
def test_native_module_provider_skips_empty_welcome_dm_without_status(tmp_path, message):
    messages = tmp_path / "Messages"
    messages.mkdir()
    (messages / "welcome_dm.txt").write_text(message, encoding="utf-8")
    # A legacy file must not be consulted.
    (tmp_path / "pm_list.txt").write_text("Legacy message", encoding="utf-8")
    ctx = context(tmp_path)

    modules = _FollowModuleProvider(
        {"pm-percentage": "1", "total-pm-limit": "5"},
        {},
        {"maximum_dms_per_hour": 10},
        Mock(),
        Mock(),
    ).modules_for(ctx)

    assert all(module.module.value != "DM" for module in modules)
    with RuntimeDatabase(tmp_path) as database:
        assert database._connection.execute("SELECT COUNT(*) FROM dm").fetchone()[0] == 0


def test_native_module_provider_composes_specific_dm_from_account_list(tmp_path):
    messages = tmp_path / "Messages"
    messages.mkdir()
    (messages / "welcome_dm.txt").write_text("Welcome", encoding="utf-8")
    lists = tmp_path / "Lists"
    lists.mkdir()
    (lists / "dmspecific.txt").write_text(" Target.User \n", encoding="utf-8")
    ctx = context(tmp_path)
    modules = _FollowModuleProvider(
        {
            "pm-percentage": "1",
            "total-pm-limit": "5",
            "igbot-dm-method": "specific-users",
        },
        {},
        {"maximum_dms_per_hour": 10},
        Mock(),
        Mock(),
    ).modules_for(ctx)

    dm = next(module for module in modules if module.module.value == "DM")
    assert isinstance(dm._recipients, SpecificDMRecipients)
    assert isinstance(dm._persistence, SpecificDMPersistence)
    assert dm._private_fallback
    assert dm._bounded_search
    with RuntimeDatabase(tmp_path) as database:
        assert database.specific_dm.pending_dm_users() == ((1, "target.user"),)
