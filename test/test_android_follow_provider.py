import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from IGBot.runtime import RuntimeContext, SessionContext
from IGBot.runtime.candidates import Candidate, CandidateProviderType
from IGBot.runtime.follow import (
    AndroidContactScraper,
    AndroidFollowProvider,
    AndroidFollowStatus,
    ConfiguredFollowCandidateQualifier,
    FollowFilterSettings,
    FollowModuleResultStatus,
    TextFilterSettings,
)
from IGBot.runtime.native_integration import _ProfilePersistence
from IGBot.runtime.profile_database import GlobalDatabaseWriter
from IGBot.runtime.profile_ready import wait_for_profile_ready


def node(
    text="",
    resource_id="",
    bounds="[0,0][100,100]",
    description="",
    scrollable=False,
    class_name="",
    checkable=False,
    checked=False,
):
    return (
        f'<node text="{text}" resource-id="{resource_id}" '
        f'bounds="{bounds}" content-desc="{description}" '
        f'scrollable="{str(scrollable).lower()}" class="{class_name}" '
        f'checkable="{str(checkable).lower()}" '
        f'checked="{str(checked).lower()}" />'
    )


def hierarchy(*nodes):
    return "<hierarchy>" + "".join(nodes) + "</hierarchy>"


def search_user_row(username, bounds="[0,0][100,100]"):
    return (
        f'<node resource-id="com.instagram.androie:id/row_search_user_container" '
        f'bounds="{bounds}">'
        f'<node text="{username}" '
        'resource-id="com.instagram.androie:id/row_search_user_username" '
        f'bounds="{bounds}" />'
        "</node>"
    )


def instagram_id(name):
    return f"com.instagram.android:id/{name}"


def profile_metrics():
    return (
        node(
            text="104",
            resource_id=instagram_id("profile_header_familiar_post_count_value"),
        ),
        node(
            text="432",
            resource_id=instagram_id("profile_header_familiar_followers_value"),
        ),
        node(
            text="199",
            resource_id=instagram_id("profile_header_familiar_following_value"),
        ),
    )


class StubLogger:
    def __init__(self):
        self.messages = []

    def debug(self, message, **fields):
        self.messages.append(("debug", message, fields))

    def info(self, message, **fields):
        self.messages.append(("info", message, fields))

    def warning(self, message, **fields):
        self.messages.append(("warning", message, fields))

    def error(self, message, **fields):
        self.messages.append(("error", message, fields))


class FakeDevice:
    def __init__(self, hierarchies):
        self.hierarchies = list(hierarchies)
        self.last_hierarchy = self.hierarchies[-1]
        self.clicks = []
        self.keys = []
        self.presses = []
        self.swipes = []

    def dump_hierarchy(self, compressed=False):
        assert compressed is False
        if self.hierarchies:
            self.last_hierarchy = self.hierarchies.pop(0)
        return self.last_hierarchy

    def click(self, x, y):
        self.clicks.append((x, y))

    def send_keys(self, value, clear=False):
        self.keys.append((value, clear))

    def press(self, key):
        self.presses.append(key)

    def swipe(self, *args, **kwargs):
        self.swipes.append((args, kwargs))


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class RecordingContactScraper:
    def __init__(self, result=None):
        self.result = result or {"email": "target@example.com"}
        self.calls = []

    def scrape(self, context, hierarchy_xml):
        self.calls.append((context, hierarchy_xml))
        return self.result


def make_context(tmp_path):
    return RuntimeContext(
        SessionContext(
            session_id=uuid4(),
            account_username="account",
            phone_id="phone-1",
            application_id="com.instagram.clone",
            account_directory=tmp_path,
            created_at=datetime.now(timezone.utc),
        ),
        StubLogger(),
    )


def make_provider(
    device,
    scraper=None,
    *,
    sleeps=None,
    verification_delay=2,
    search_timeout=0.01,
    search_settle_delay=lambda: 0.5,
    mute_after_follow=False,
):
    return AndroidFollowProvider(
        scraper or RecordingContactScraper(),
        device_factory=lambda serial: device if serial == "phone-1" else None,
        sleeper=(
            (lambda seconds: sleeps.append(seconds))
            if sleeps is not None
            else lambda _seconds: None
        ),
        navigation_wait=0,
        verification_delay=verification_delay,
        search_timeout=search_timeout,
        search_poll_interval=0.001,
        search_settle_delay=search_settle_delay,
        mute_after_follow=mute_after_follow,
    )


def candidate():
    return Candidate("exact_user", "source_user", CandidateProviderType.FOLLOWERS)


def test_letter_search_uses_inspected_followers_field_without_global_navigation(
    tmp_path,
):
    device = FakeDevice(
        (
            hierarchy(
                node(
                    resource_id="com.instagram.androie:id/row_search_edit_text",
                    text="Search",
                    bounds="[48,458][1032,564]",
                ),
                node(
                    resource_id=instagram_id("action_bar_search_edit_text"),
                    bounds="[0,0][100,100]",
                ),
            ),
        )
    )
    result = make_provider(device).search_followers(make_context(tmp_path), "AE")
    assert result.status is AndroidFollowStatus.SUCCESS
    assert device.clicks == [(540, 511)]
    assert device.keys == [("AE", True)]
    assert device.presses == []


def test_letter_search_does_not_accept_generic_global_search_field(tmp_path):
    device = FakeDevice(
        (hierarchy(node(resource_id=instagram_id("search_edit_text"))),)
    )
    result = make_provider(device).search_followers(make_context(tmp_path), "AE")
    assert result.status is AndroidFollowStatus.FOLLOW_FAILED
    assert device.clicks == []
    assert device.keys == []
    assert device.presses == []


def test_source_search_opens_immediately_visible_exact_username(tmp_path):
    device = FakeDevice(
        (
            hierarchy(
                node(resource_id=instagram_id("search_tab"), bounds="[0,0][10,10]")
            ),
            hierarchy(
                node(
                    resource_id=instagram_id("action_bar_search_edit_text"),
                    bounds="[10,0][20,10]",
                )
            ),
            hierarchy(search_user_row("exact_user", "[20,0][30,10]")),
            hierarchy(
                node(
                    text="exact_user",
                    resource_id=instagram_id("action_bar_title"),
                )
            ),
        )
    )
    provider = make_provider(device)

    result = provider.locate_source(make_context(tmp_path), "exact_user")

    assert result.status is AndroidFollowStatus.SUCCESS
    assert device.keys == [("exact_user", True)]
    assert device.clicks[-1] == (25, 5)


@pytest.mark.parametrize("delay", (2.0, 2.5, 3.0))
def test_source_search_waits_once_after_typing_before_first_inspection(tmp_path, delay):
    events = []

    class OrderedDevice(FakeDevice):
        def send_keys(self, value, clear=False):
            events.append("typed")
            super().send_keys(value, clear=clear)

        def dump_hierarchy(self, compressed=False):
            events.append("inspected")
            return super().dump_hierarchy(compressed=compressed)

    device = OrderedDevice(
        (
            hierarchy(node(resource_id=instagram_id("search_tab"))),
            hierarchy(node(resource_id=instagram_id("action_bar_search_edit_text"))),
            hierarchy(search_user_row("exact_user")),
            hierarchy(
                node(text="exact_user", resource_id=instagram_id("action_bar_title"))
            ),
        )
    )

    def settle(seconds):
        events.append(("settled", seconds))

    provider = AndroidFollowProvider(
        RecordingContactScraper(),
        device_factory=lambda _serial: device,
        sleeper=settle,
        navigation_wait=0,
        search_timeout=1,
        search_poll_interval=0.001,
        search_settle_delay=lambda: delay,
    )

    result = provider.locate_source(make_context(tmp_path), "exact_user")

    assert result.status is AndroidFollowStatus.SUCCESS
    typed = events.index("typed")
    settled = events.index(("settled", delay))
    assert typed < settled
    assert events[settled + 1] == "inspected"
    assert events.count(("settled", delay)) == 1


def test_source_search_uses_search_and_accounts_before_exact_match(tmp_path):
    device = FakeDevice(
        (
            hierarchy(node(resource_id=instagram_id("search_tab"))),
            hierarchy(node(resource_id=instagram_id("action_bar_search_edit_text"))),
            hierarchy(
                node(
                    text="different",
                    resource_id=instagram_id("row_user_primary_name"),
                )
            ),
            hierarchy(node(text="Search", bounds="[100,0][120,20]")),
            hierarchy(
                node(
                    text="Accounts",
                    resource_id=instagram_id("accounts_tab"),
                    bounds="[120,0][140,20]",
                )
            ),
            hierarchy(search_user_row("exact_user", "[140,0][160,20]")),
            hierarchy(
                node(
                    text="exact_user",
                    resource_id=instagram_id("action_bar_title"),
                )
            ),
        )
    )

    result = make_provider(device).locate_source(make_context(tmp_path), "exact_user")

    assert result.status is AndroidFollowStatus.SUCCESS
    assert (110, 10) in device.clicks
    assert (130, 10) in device.clicks
    assert device.clicks[-1] == (150, 10)


def test_source_search_never_opens_non_exact_result(tmp_path):
    wrong = search_user_row("exact_user_fan", "[200,0][220,20]")
    device = FakeDevice(
        (
            hierarchy(node(resource_id=instagram_id("search_tab"))),
            hierarchy(node(resource_id=instagram_id("action_bar_search_edit_text"))),
            hierarchy(wrong),
            hierarchy(node(text="Search")),
            hierarchy(node(text="Accounts", resource_id=instagram_id("accounts_tab"))),
            hierarchy(wrong),
        )
    )

    result = make_provider(device).locate_source(make_context(tmp_path), "exact_user")

    assert result.status is AndroidFollowStatus.SOURCE_NOT_FOUND
    assert (210, 10) not in device.clicks


def test_search_ignores_keyword_suggestion_and_clicks_exact_account_row(tmp_path):
    results = hierarchy(
        node(
            text="familytraveldiary_",
            resource_id="com.instagram.androie:id/row_search_keyword_title",
            bounds="[240,338][593,391]",
        ),
        search_user_row("familytraveldiary__", "[0,452][1080,626]"),
        search_user_row("familytraveldiary_", "[0,626][1080,800]"),
    )
    device = FakeDevice(
        (
            hierarchy(node(resource_id=instagram_id("search_tab"))),
            hierarchy(node(resource_id=instagram_id("action_bar_search_edit_text"))),
            results,
            hierarchy(
                node(
                    text="familytraveldiary_",
                    resource_id=instagram_id("action_bar_title"),
                )
            ),
        )
    )
    context = make_context(tmp_path)

    result = make_provider(device).locate_source(context, "familytraveldiary_")

    assert result.status is AndroidFollowStatus.SUCCESS
    assert device.clicks[-1] == (540, 713)
    assert "[Search] Keyword suggestion ignored" in [
        message for _level, message, _fields in context.logger.messages
    ]


def test_source_search_diagnostics_identify_accounts_result_failure(tmp_path):
    device = FakeDevice(
        (
            hierarchy(node(resource_id=instagram_id("search_tab"))),
            hierarchy(node(resource_id=instagram_id("action_bar_search_edit_text"))),
            hierarchy(
                node(
                    text="different", resource_id=instagram_id("row_user_primary_name")
                )
            ),
            hierarchy(node(text="Search")),
            hierarchy(node(text="Accounts", resource_id=instagram_id("accounts_tab"))),
            hierarchy(
                node(
                    text="still_different",
                    resource_id=instagram_id("row_user_primary_name"),
                )
            ),
        )
    )
    context = make_context(tmp_path)

    result = make_provider(device).locate_source(context, "exact_user")

    assert result.status is AndroidFollowStatus.SOURCE_NOT_FOUND
    messages = [message for _level, message, _fields in context.logger.messages]
    assert messages[:3] == [
        "[Search] Starting source search",
        "[Search] Opening Search tab",
        "[Search] Waiting for Search tab UI hierarchy",
    ]
    assert "[Search] Accounts tab detected" in messages
    assert "[Search] Opening Accounts tab" in messages
    assert "[Search] Retry scheduled" in messages
    assert messages[-1] == "[Search] Source failed after all search strategies"


def test_keyword_only_results_execute_search_before_opening_exact_account(tmp_path):
    device = FakeDevice(
        (
            hierarchy(node(resource_id=instagram_id("search_tab"))),
            hierarchy(node(resource_id=instagram_id("action_bar_search_edit_text"))),
            hierarchy(
                node(
                    text="thisisyules",
                    resource_id="com.instagram.androie:id/row_search_keyword_title",
                ),
                search_user_row("thisisjules"),
            ),
            hierarchy(search_user_row("thisisyules", "[0,410][1080,614]")),
            hierarchy(
                node(text="thisisyules", resource_id=instagram_id("action_bar_title"))
            ),
        )
    )
    context = make_context(tmp_path)

    result = make_provider(device).locate_source(context, "thisisyules")

    assert result.status is AndroidFollowStatus.SUCCESS
    assert device.presses == ["enter"]
    assert device.clicks[-1] == (540, 512)
    messages = [message for _level, message, _fields in context.logger.messages]
    assert messages.index("[Search] Executing search") < messages.index(
        "[Search] Opening source profile"
    )


def test_keyword_search_uses_inspected_accounts_tab_when_needed(tmp_path):
    device = FakeDevice(
        (
            hierarchy(node(resource_id=instagram_id("search_tab"))),
            hierarchy(node(resource_id=instagram_id("action_bar_search_edit_text"))),
            hierarchy(
                node(
                    text="thisisyules",
                    resource_id="com.instagram.androie:id/row_search_keyword_title",
                )
            ),
            hierarchy(
                node(
                    text="Accounts",
                    resource_id="com.instagram.androie:id/tab_button_name_text",
                    bounds="[309,317][501,371]",
                )
            ),
            hierarchy(search_user_row("thisisyules", "[0,410][1080,614]")),
            hierarchy(
                node(text="thisisyules", resource_id=instagram_id("action_bar_title"))
            ),
        )
    )
    context = make_context(tmp_path)

    result = make_provider(device).locate_source(context, "thisisyules")

    assert result.status is AndroidFollowStatus.SUCCESS
    assert device.presses == ["enter"]
    assert (405, 344) in device.clicks
    assert device.clicks[-1] == (540, 512)
    messages = [message for _level, message, _fields in context.logger.messages]
    assert "[Search] Exact account detected after Accounts" in messages


def test_next_source_reuses_and_clears_existing_search_field(tmp_path):
    class SearchDevice(FakeDevice):
        def __init__(self):
            super().__init__((hierarchy(node(resource_id=instagram_id("search_tab"))),))
            self.source = ""
            self.profile_open = False

        def dump_hierarchy(self, compressed=False):
            if self.profile_open:
                return hierarchy(
                    node(
                        text="second_source",
                        resource_id=instagram_id("action_bar_title"),
                    )
                )
            if self.source == "second_source":
                return hierarchy(
                    node(resource_id=instagram_id("action_bar_search_edit_text")),
                    search_user_row("second_source"),
                )
            if self.source == "first_source":
                return hierarchy(
                    node(resource_id=instagram_id("action_bar_search_edit_text")),
                    node(
                        text="first_source",
                        resource_id="com.instagram.androie:id/row_search_keyword_title",
                    ),
                )
            return hierarchy(
                node(resource_id=instagram_id("search_tab")),
                node(resource_id=instagram_id("action_bar_search_edit_text")),
            )

        def send_keys(self, value, clear=False):
            super().send_keys(value, clear=clear)
            self.source = value

        def click(self, x, y):
            super().click(x, y)
            if self.source == "second_source" and (x, y) == (50, 50):
                self.profile_open = True

    device = SearchDevice()
    provider = make_provider(device, search_timeout=0.001)
    context = make_context(tmp_path)

    first = provider.locate_source(context, "first_source")
    second = provider.locate_source(context, "second_source")

    assert first.status is AndroidFollowStatus.SOURCE_NOT_FOUND
    assert second.status is AndroidFollowStatus.SUCCESS
    assert device.keys == [("first_source", True), ("second_source", True)]
    assert device.presses == ["enter"]


def test_followers_navigation_actions_preserve_existing_list(tmp_path):
    device = FakeDevice(
        (
            hierarchy(
                node(
                    description="651followers",
                    resource_id=instagram_id(
                        "profile_header_followers_stacked_familiar"
                    ),
                )
            ),
            hierarchy(node(text="See more", bounds="[0,100][100,120]")),
            hierarchy(node(resource_id=instagram_id("follow_list_search"))),
            hierarchy(
                node(
                    resource_id=instagram_id("follow_list_container"),
                    bounds="[0,100][300,700]",
                    scrollable=True,
                )
            ),
            hierarchy(
                node(
                    resource_id=instagram_id("follow_list_container"),
                    scrollable=True,
                )
            ),
        )
    )
    provider = make_provider(device)
    context = make_context(tmp_path)

    assert provider.open_followers(context).status is AndroidFollowStatus.SUCCESS
    assert provider.show_more_followers(context).status is AndroidFollowStatus.SUCCESS
    assert (
        provider.search_followers(context, "az").status is AndroidFollowStatus.SUCCESS
    )
    assert provider.scroll_followers(context).status is AndroidFollowStatus.SUCCESS
    assert provider.return_to_followers(context).status is AndroidFollowStatus.SUCCESS

    assert device.keys == [("az", True)]
    assert device.swipes == [((150, 699, 150, 101), {"duration": 0.4})]
    assert device.presses == ["back"]


def test_following_list_scrolls_with_overlapping_viewports(tmp_path):
    scrollable = hierarchy(
        node(
            resource_id="android:id/list",
            bounds="[0,100][300,700]",
            scrollable=True,
        )
    )
    device = FakeDevice((scrollable, scrollable))
    provider = make_provider(device)
    context = make_context(tmp_path)

    assert provider.scroll_following_list(context).status is AndroidFollowStatus.SUCCESS
    assert provider.scroll_following_list(context).status is AndroidFollowStatus.SUCCESS

    assert device.swipes == [
        ((150, 699, 150, 309), {"duration": 0.4}),
        ((150, 699, 150, 309), {"duration": 0.4}),
    ]


def test_following_navigation_uses_inspected_profile_control(tmp_path):
    device = FakeDevice(
        (
            hierarchy(
                node(
                    description="1,103 following",
                    resource_id=instagram_id(
                        "profile_header_following_stacked_familiar"
                    ),
                    bounds="[700,100][1000,220]",
                )
            ),
        )
    )
    provider = make_provider(device)

    result = provider.open_following(make_context(tmp_path))

    assert result.status is AndroidFollowStatus.SUCCESS
    assert device.clicks == [(850, 160)]


def test_open_candidate_profile_requires_exact_username_and_reads_profile(tmp_path):
    device = FakeDevice(
        (
            hierarchy(
                node(
                    text="exact_user",
                    resource_id=instagram_id("follow_list_username"),
                    bounds="[0,0][100,20]",
                )
            ),
            hierarchy(
                node(text="exact_user", resource_id=instagram_id("action_bar_title")),
                node(
                    text="Exact Name",
                    resource_id=instagram_id("profile_header_full_name_above_vanity"),
                ),
                node(text="Profile bio", resource_id=instagram_id("profile_bio")),
                *profile_metrics(),
                node(
                    text="This account is private",
                    resource_id=instagram_id(
                        "row_profile_header_empty_profile_notice_title"
                    ),
                ),
            ),
        )
    )
    provider = make_provider(device)

    result = provider.open_candidate_profile(make_context(tmp_path), candidate())

    assert result.status is AndroidFollowStatus.SUCCESS
    assert result.profile.username == "exact_user"
    assert result.profile.display_name == "Exact Name"
    assert result.profile.biography == "Profile bio"
    assert result.profile.is_private is True


def test_candidate_profile_provider_contract_returns_profile_only(tmp_path):
    device = FakeDevice(
        (
            hierarchy(
                node(
                    text="exact_user",
                    resource_id=instagram_id("follow_list_username"),
                )
            ),
            hierarchy(
                node(text="exact_user", resource_id=instagram_id("action_bar_title")),
                *profile_metrics(),
            ),
        )
    )

    profile = make_provider(device).open_profile(make_context(tmp_path), candidate())

    assert profile.username == "exact_user"


def test_profile_ready_returns_immediately_for_complete_snapshot():
    complete = hierarchy(
        node(text="exact_user", resource_id=instagram_id("action_bar_title")),
        node(
            text="0",
            resource_id=instagram_id("profile_header_familiar_post_count_value"),
        ),
        node(
            text="0",
            resource_id=instagram_id("profile_header_familiar_followers_value"),
        ),
        node(
            text="0",
            resource_id=instagram_id("profile_header_familiar_following_value"),
        ),
    )
    device = FakeDevice((complete,))
    clock = FakeClock()

    result = wait_for_profile_ready(
        device,
        complete,
        username_ids=("action_bar_title",),
        metric_ids=(
            "profile_header_familiar_post_count_value",
            "profile_header_familiar_followers_value",
            "profile_header_familiar_following_value",
        ),
        clock=clock,
        sleeper=clock.sleep,
    )

    assert result == complete
    assert clock.sleeps == []


def test_candidate_profile_waits_for_metrics_before_parsing(tmp_path, monkeypatch):
    incomplete = hierarchy(
        node(text="exact_user", resource_id=instagram_id("action_bar_title")),
        node(
            text="104",
            resource_id=instagram_id("profile_header_familiar_post_count_value"),
        ),
    )
    complete = hierarchy(
        node(text="exact_user", resource_id=instagram_id("action_bar_title")),
        *profile_metrics(),
    )
    device = FakeDevice(
        (
            hierarchy(
                node(
                    text="exact_user", resource_id=instagram_id("follow_list_username")
                )
            ),
            incomplete,
            incomplete,
            complete,
        )
    )
    clock = FakeClock()
    original_count = AndroidFollowProvider._profile_count.__func__
    parsed_at = []

    def checked_count(cls, nodes, identifiers):
        parsed_at.append(clock.now)
        assert all(
            cls._find_by_id(nodes, (identifier,)) is not None
            for identifier in (
                "profile_header_familiar_post_count_value",
                "profile_header_familiar_followers_value",
                "profile_header_familiar_following_value",
            )
        )
        return original_count(cls, nodes, identifiers)

    monkeypatch.setattr(
        AndroidFollowProvider, "_profile_count", classmethod(checked_count)
    )
    provider = AndroidFollowProvider(
        RecordingContactScraper(),
        device_factory=lambda _serial: device,
        sleeper=clock.sleep,
        clock=clock,
        navigation_wait=0,
    )
    context = make_context(tmp_path)

    profile = provider.open_profile(context, candidate())

    assert profile.followers == 432
    assert clock.sleeps == [0, 0, 0, 0.25, 0.25]
    assert parsed_at == [0.5, 0.5, 0.5]
    assert any(
        message == "[Profile] Profile ready."
        for _, message, _ in context.logger.messages
    )


def test_candidate_profile_timeout_skips_without_parsing(tmp_path, monkeypatch):
    incomplete = hierarchy(
        node(text="exact_user", resource_id=instagram_id("action_bar_title")),
    )
    followers = hierarchy(node(resource_id=instagram_id("follow_list_container")))
    device = FakeDevice(
        (
            hierarchy(
                node(
                    text="exact_user", resource_id=instagram_id("follow_list_username")
                )
            ),
            incomplete,
            *([incomplete] * 12),
            followers,
        )
    )
    clock = FakeClock()
    monkeypatch.setattr(
        AndroidFollowProvider,
        "_profile_count",
        classmethod(
            lambda _cls, _nodes, _identifiers: pytest.fail("parsed before ready")
        ),
    )
    provider = AndroidFollowProvider(
        RecordingContactScraper(),
        device_factory=lambda _serial: device,
        sleeper=clock.sleep,
        clock=clock,
        navigation_wait=0,
    )
    context = make_context(tmp_path)

    result = provider.open_candidate_profile(context, candidate())

    assert result.status is AndroidFollowStatus.FOLLOW_FAILED
    assert result.detail == "Profile loading timeout."
    assert result.profile is None
    assert clock.now == 3.0
    assert device.presses == ["back"]
    assert any(
        message == "[Profile] Profile loading timeout."
        for _, message, _ in context.logger.messages
    )


def test_specific_candidate_profile_timeout_returns_to_instagram_search(
    tmp_path, monkeypatch
):
    incomplete = hierarchy(
        node(text="exact_user", resource_id=instagram_id("action_bar_title")),
    )
    search = hierarchy(node(resource_id=instagram_id("action_bar_search_edit_text")))
    device = FakeDevice((incomplete, incomplete, *([incomplete] * 12), search))
    clock = FakeClock()
    monkeypatch.setattr(
        AndroidFollowProvider,
        "_profile_count",
        classmethod(
            lambda _cls, _nodes, _identifiers: pytest.fail("parsed before ready")
        ),
    )
    provider = AndroidFollowProvider(
        RecordingContactScraper(),
        device_factory=lambda _serial: device,
        sleeper=clock.sleep,
        clock=clock,
        navigation_wait=0,
    )
    context = make_context(tmp_path)
    specific = Candidate(
        "exact_user", "specific_users", CandidateProviderType.SPECIFIC_ACCOUNTS
    )

    result = provider.open_candidate_profile(context, specific)

    assert result.status is AndroidFollowStatus.FOLLOW_FAILED
    assert result.detail == "Profile loading timeout."
    assert device.presses == ["back"]
    messages = [message for _level, message, _fields in context.logger.messages]
    assert "[Specific] Returning to Instagram Search..." in messages
    assert "[Specific] Instagram Search restored." in messages
    assert "[Candidate] Returning to Followers list..." not in messages


def test_candidate_profile_reads_inspected_profile_facts_and_notifies_observer(
    tmp_path,
):
    observed = []
    profile_hierarchy = """<hierarchy>
      <node text="exact_user" resource-id="com.instagram.androie:id/action_bar_title" bounds="[0,0][100,20]" />
      <node text="Exact User" resource-id="com.instagram.androie:id/profile_header_full_name_above_vanity" bounds="[0,20][100,40]" />
      <node text="Carpenter" resource-id="com.instagram.androie:id/profile_header_business_category" bounds="[0,40][100,60]" />
      <node resource-id="com.instagram.androie:id/profile_user_info_compose_view" bounds="[0,60][100,100]">
        <node text="Visible biography" class="android.widget.TextView" resource-id="" bounds="[0,60][100,80]" />
      </node>
      <node text="example.com" resource-id="com.instagram.androie:id/text_view" bounds="[0,100][100,120]" />
      <node resource-id="com.instagram.androie:id/profile_links_view" bounds="[0,120][100,140]" />
      <node text="Main Street" resource-id="com.instagram.androie:id/address_text" bounds="[0,120][100,140]" />
      <node text="104" resource-id="com.instagram.androie:id/profile_header_familiar_post_count_value" bounds="[0,140][100,160]" />
      <node text="432" resource-id="com.instagram.androie:id/profile_header_familiar_followers_value" bounds="[0,160][100,180]" />
      <node text="199" resource-id="com.instagram.androie:id/profile_header_familiar_following_value" bounds="[0,180][100,200]" />
      <node text="Follow" resource-id="com.instagram.androie:id/profile_header_follow_button" bounds="[0,200][100,220]" />
      <node resource-id="com.instagram.androie:id/action_bar_title_verified_badge" bounds="[0,220][20,240]" />
    </hierarchy>"""
    device = FakeDevice(
        (
            hierarchy(
                node(
                    text="exact_user",
                    resource_id="com.instagram.androie:id/follow_list_username",
                )
            ),
            profile_hierarchy,
        )
    )
    provider = AndroidFollowProvider(
        RecordingContactScraper(),
        device_factory=lambda _serial: device,
        sleeper=lambda _seconds: None,
        navigation_wait=0,
        profile_observer=lambda context, profile: observed.append((context, profile)),
    )
    context = make_context(tmp_path)

    profile = provider.open_profile(context, candidate())

    assert profile.display_name == "Exact User"
    assert profile.biography == "Visible biography"
    assert profile.category == "Carpenter"
    assert profile.website == "example.com"
    assert profile.address == "Main Street"
    assert (profile.posts, profile.followers, profile.following) == (104, 432, 199)
    assert profile.is_business is True
    assert profile.is_verified is True
    assert profile.follow_status == "follow"
    assert profile.has_external_links is True
    assert observed == [(context, profile)]


def _compose_biography_profile(biography: str, *, expandable: bool) -> str:
    return hierarchy(
        node(text="exact_user", resource_id=instagram_id("action_bar_title")),
        *profile_metrics(),
        '<node resource-id="com.instagram.androie:id/profile_user_info_compose_view" '
        'bounds="[48,542][1032,757]">'
        f'<node class="android.view.View" clickable="{str(expandable).lower()}" '
        'bounds="[48,542][1032,757]">'
        f'<node class="android.widget.TextView" text="{biography}" '
        'bounds="[48,542][1032,757]" />'
        "</node></node>",
    )


def test_short_biography_does_not_add_an_expansion_tap(tmp_path):
    device = FakeDevice(
        (
            hierarchy(
                node(
                    text="exact_user", resource_id=instagram_id("follow_list_username")
                )
            ),
            _compose_biography_profile("Short biography", expandable=True),
        )
    )

    profile = make_provider(device).open_profile(make_context(tmp_path), candidate())

    assert profile.biography == "Short biography"
    assert len(device.clicks) == 1


def test_expanded_biography_reaches_filters_language_and_global_profile(tmp_path):
    collapsed = _compose_biography_profile("Near… more", expandable=True)
    full = "Near the river. Photography in Deutschland."
    expanded = _compose_biography_profile(full, expandable=False)
    device = FakeDevice(
        (
            hierarchy(
                node(
                    text="exact_user", resource_id=instagram_id("follow_list_username")
                )
            ),
            collapsed,
            expanded,
        )
    )
    writer = GlobalDatabaseWriter(tmp_path)
    persistence = _ProfilePersistence(writer)
    context = make_context(tmp_path)
    provider = AndroidFollowProvider(
        RecordingContactScraper(),
        device_factory=lambda _serial: device,
        sleeper=lambda _seconds: None,
        navigation_wait=0,
        profile_observer=persistence.observe,
    )
    try:
        profile = provider.open_profile(context, candidate())
        writer.flush()
    finally:
        writer.close()

    assert profile.biography == full
    assert len(device.clicks) == 2
    assert device.clicks[-1] == (540, 649)
    qualifier = ConfiguredFollowCandidateQualifier(lambda text: "de")
    required = qualifier.qualify(
        context,
        profile,
        FollowFilterSettings(keywords=TextFilterSettings(required=("photography",))),
    )
    blocked = qualifier.qualify(
        context,
        profile,
        FollowFilterSettings(keywords=TextFilterSettings(blocked=("photography",))),
    )
    detected_text = []
    language = ConfiguredFollowCandidateQualifier(
        lambda text: detected_text.append(text) or "de"
    ).qualify(context, profile, FollowFilterSettings(biography_languages=("de",)))
    assert required.status is FollowModuleResultStatus.READY_TO_FOLLOW
    assert blocked.status is FollowModuleResultStatus.FILTER_REJECTED
    assert language.status is FollowModuleResultStatus.READY_TO_FOLLOW
    assert detected_text == [full]
    with sqlite3.connect(tmp_path / "global_profiles.db") as connection:
        stored = connection.execute(
            "SELECT biography FROM profiles WHERE username = ?", ("exact_user",)
        ).fetchone()
    assert stored == (full,)


def test_contact_scraping_opens_delegates_and_closes_popup(tmp_path):
    popup = hierarchy(
        node(
            resource_id=instagram_id("contact_options_rv"),
        )
    )
    device = FakeDevice(
        (
            hierarchy(
                node(
                    description="Contact",
                    resource_id=instagram_id("button_container"),
                )
            ),
            popup,
            hierarchy(
                node(text="exact_user", resource_id=instagram_id("action_bar_title"))
            ),
        )
    )
    scraper = RecordingContactScraper()
    context = make_context(tmp_path)

    result = make_provider(device, scraper).scrape_contact(context)

    assert result.status is AndroidFollowStatus.CONTACT_SCRAPED
    assert result.contact_details == {"email": "target@example.com"}
    assert scraper.calls == [(context, popup)]
    assert device.presses == ["back"]


def test_missing_contact_does_not_open_popup(tmp_path):
    device = FakeDevice((hierarchy(node(text="Message")),))
    scraper = RecordingContactScraper()
    context = make_context(tmp_path)

    result = make_provider(device, scraper).scrape_contact(context)

    assert result.status is AndroidFollowStatus.CONTACT_NOT_AVAILABLE
    assert scraper.calls == []
    assert device.presses == []
    assert any(
        message == "[Contact] No Contact button found. Profile metadata saved."
        for _level, message, _fields in context.logger.messages
    )


def test_contact_scraping_fails_when_profile_does_not_return(tmp_path):
    device = FakeDevice(
        (
            hierarchy(
                node(
                    description="Contact",
                    resource_id=instagram_id("button_container"),
                )
            ),
            hierarchy(node(resource_id=instagram_id("contact_options_rv"))),
            hierarchy(node(text="Contact")),
        )
    )

    result = make_provider(device).scrape_contact(make_context(tmp_path))

    assert result.status is AndroidFollowStatus.FOLLOW_FAILED
    assert "profile screen did not return" in result.detail
    assert device.presses == ["back"]


def test_contact_scraper_reads_dynamic_rows_from_inspected_resource_ids(tmp_path):
    popup = """<hierarchy><node resource-id="com.instagram.androie:id/contact_options_rv">
      <node><node text="Call" resource-id="com.instagram.androie:id/contact_option_header" />
      <node text="+43 699" resource-id="com.instagram.androie:id/contact_option_sub_text" /></node>
      <node><node text="Email" resource-id="com.instagram.androie:id/contact_option_header" />
      <node text="office@example.com" resource-id="com.instagram.androie:id/contact_option_sub_text" /></node>
      <node><node text="Address" resource-id="com.instagram.androie:id/contact_option_header" />
      <node text="Main Street" resource-id="com.instagram.androie:id/contact_option_sub_text" /></node>
    </node></hierarchy>"""
    context = make_context(tmp_path)

    details = AndroidContactScraper().scrape(context, popup)

    assert details == {
        "phone": "+43 699",
        "email": "office@example.com",
        "address": "Main Street",
    }
    messages = [message for _level, message, _fields in context.logger.messages]
    assert "[Contact] Phone found." in messages
    assert "[Contact] Email found." in messages
    assert "[Contact] Address found." in messages


@pytest.mark.parametrize(
    ("state", "expected"),
    (
        ("Following", AndroidFollowStatus.ALREADY_FOLLOWING),
        ("Requested", AndroidFollowStatus.REQUESTED),
        ("Follow back", AndroidFollowStatus.FOLLOW_BACK),
    ),
)
def test_existing_follow_states_are_never_tapped(tmp_path, state, expected):
    device = FakeDevice(
        (
            hierarchy(
                node(
                    text=state,
                    resource_id=instagram_id("profile_header_follow_button"),
                )
            ),
        )
    )

    result = make_provider(device).execute_follow(make_context(tmp_path))

    assert result.status is expected
    assert device.clicks == []
    assert device.presses == ["back"]


@pytest.mark.parametrize(
    ("verified_state", "expected"),
    (
        ("Following", AndroidFollowStatus.SUCCESS),
        ("Requested", AndroidFollowStatus.REQUESTED),
        ("Follow", AndroidFollowStatus.GHOST_BLOCK_DETECTED),
        ("Message", AndroidFollowStatus.FOLLOW_FAILED),
    ),
)
def test_follow_tap_verifies_result_after_configured_delay(
    tmp_path, verified_state, expected
):
    sleeps = []
    device = FakeDevice(
        (
            hierarchy(
                node(
                    text="Follow",
                    resource_id=instagram_id("profile_header_follow_button"),
                )
            ),
            hierarchy(
                node(
                    text=verified_state,
                    resource_id=instagram_id("profile_header_follow_button"),
                )
            ),
        )
    )

    result = make_provider(device, sleeps=sleeps, verification_delay=3).execute_follow(
        make_context(tmp_path)
    )

    assert result.status is expected
    assert device.clicks == [(50, 50)]
    assert device.presses == ["back"]
    assert sum(sleeps) == pytest.approx(3)


def test_verification_delay_defaults_to_two_seconds(tmp_path):
    sleeps = []
    device = FakeDevice(
        (
            hierarchy(
                node(
                    text="Follow",
                    resource_id=instagram_id("profile_header_follow_button"),
                )
            ),
            hierarchy(
                node(
                    text="Following",
                    resource_id=instagram_id("profile_header_follow_button"),
                )
            ),
        )
    )

    make_provider(device, sleeps=sleeps).execute_follow(make_context(tmp_path))

    assert sum(sleeps) == pytest.approx(2)


def test_verified_follow_dynamically_enables_mute_switches_and_returns(tmp_path):
    follow = hierarchy(
        node(
            text="Follow",
            resource_id=instagram_id("profile_header_user_action_follow_button"),
        )
    )
    following = hierarchy(
        node(
            text="Following",
            resource_id=instagram_id("profile_header_user_action_follow_button"),
        )
    )
    following_sheet = hierarchy(
        node(
            resource_id=instagram_id("follow_sheet_mute_row"),
            bounds="[0,1359][1080,1521]",
        )
    )
    mute_sheet = """<hierarchy><node text="Mute"
      resource-id="com.instagram.androie:id/title_text_view"
      bounds="[300,475][780,610]" />
      <node resource-id="com.instagram.androie:id/bottom_sheet_container_view"
      bounds="[0,611][1080,1776]">
        <node><node class="android.widget.ToggleButton" checkable="true"
        checked="false" visible-to-user="true"
        resource-id="com.instagram.androie:id/posts_mute_setting_row_switch"
        bounds="[876,644][1032,740]" /></node>
        <node><node class="android.widget.ToggleButton" checkable="true"
        checked="true" visible-to-user="true"
        resource-id="com.instagram.androie:id/stories_mute_setting_row_switch"
        bounds="[876,806][1032,902]" /></node>
        <node><node class="android.widget.ToggleButton" checkable="true"
        checked="false" visible-to-user="true"
        resource-id="com.instagram.androie:id/igds_textcell_switch"
        bounds="[876,959][1032,1055]" /></node>
      </node></hierarchy>"""
    posts_enabled_mute_sheet = mute_sheet.replace(
        'checked="false"', 'checked="true"', 1
    )
    enabled_mute_sheet = mute_sheet.replace('checked="false"', 'checked="true"')
    profile = hierarchy(
        node(text="exact_user", resource_id=instagram_id("action_bar_title"))
    )
    followers = hierarchy(node(resource_id=instagram_id("follow_list_container")))
    device = FakeDevice(
        (
            follow,
            following,
            following,
            following,
            following_sheet,
            mute_sheet,
            posts_enabled_mute_sheet,
            enabled_mute_sheet,
            profile,
            followers,
        )
    )
    context = make_context(tmp_path)
    sleeps = []

    result = make_provider(
        device,
        sleeps=sleeps,
        verification_delay=0,
        mute_after_follow=True,
    ).execute_follow(context)

    assert result.status is AndroidFollowStatus.SUCCESS
    assert result.muted is True
    assert (954, 692) in device.clicks
    assert (954, 1007) in device.clicks
    assert (954, 854) not in device.clicks
    assert device.swipes == []
    assert all(wait <= 0.1 for wait in sleeps)
    assert device.presses == ["back"]
    messages = [message for _level, message, _fields in context.logger.messages]
    assert "[Mute] Mute settings opened." in messages
    assert "[Mute] Mute switches ready." in messages
    assert messages[-1] == "[Mute] Mute completed."


def test_follow_success_does_not_report_muted_when_mute_menu_fails(tmp_path):
    follow = hierarchy(
        node(
            text="Follow",
            resource_id=instagram_id("profile_header_user_action_follow_button"),
        )
    )
    following = hierarchy(
        node(
            text="Following",
            resource_id=instagram_id("profile_header_user_action_follow_button"),
        )
    )
    followers = hierarchy(node(resource_id=instagram_id("follow_list_container")))
    device = FakeDevice((follow, following, following, following, followers, followers))

    result = make_provider(
        device, verification_delay=0, mute_after_follow=True
    ).execute_follow(make_context(tmp_path))

    assert result.status is AndroidFollowStatus.SUCCESS
    assert result.muted is False
    assert "Mute could not be completed" in (result.detail or "")


@pytest.mark.parametrize("verified_state", ("Requested", "Follow"))
def test_mute_never_runs_without_verified_following(tmp_path, verified_state):
    device = FakeDevice(
        (
            hierarchy(
                node(
                    text="Follow",
                    resource_id=instagram_id(
                        "profile_header_user_action_follow_button"
                    ),
                )
            ),
            hierarchy(
                node(
                    text=verified_state,
                    resource_id=instagram_id(
                        "profile_header_user_action_follow_button"
                    ),
                )
            ),
        )
    )
    context = make_context(tmp_path)

    make_provider(device, verification_delay=0, mute_after_follow=True).execute_follow(
        context
    )

    messages = [message for _level, message, _fields in context.logger.messages]
    assert not any(message.startswith("[Mute]") for message in messages)
    assert device.presses == ["back"]


def test_all_required_android_result_states_are_available():
    assert {status.value for status in AndroidFollowStatus} == {
        "SUCCESS",
        "REQUESTED",
        "ALREADY_FOLLOWING",
        "FOLLOW_BACK",
        "PRIVATE_SKIPPED",
        "SOURCE_NOT_FOUND",
        "CONTACT_SCRAPED",
        "CONTACT_NOT_AVAILABLE",
        "GHOST_BLOCK_DETECTED",
        "FOLLOW_FAILED",
    }
