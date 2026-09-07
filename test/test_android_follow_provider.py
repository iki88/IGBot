from datetime import datetime, timezone
from uuid import uuid4

import pytest

from IGBot.runtime import RuntimeContext, SessionContext
from IGBot.runtime.candidates import Candidate, CandidateProviderType
from IGBot.runtime.follow import (
    AndroidFollowProvider,
    AndroidFollowStatus,
)


def node(
    text="",
    resource_id="",
    bounds="[0,0][100,100]",
    description="",
    scrollable=False,
):
    return (
        f'<node text="{text}" resource-id="{resource_id}" '
        f'bounds="{bounds}" content-desc="{description}" '
        f'scrollable="{str(scrollable).lower()}" />'
    )


def hierarchy(*nodes):
    return "<hierarchy>" + "".join(nodes) + "</hierarchy>"


def instagram_id(name):
    return f"com.instagram.android:id/{name}"


class StubLogger:
    def debug(self, message, **fields):
        pass

    def info(self, message, **fields):
        pass

    def warning(self, message, **fields):
        pass

    def error(self, message, **fields):
        pass


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


def make_provider(device, scraper=None, *, sleeps=None, verification_delay=2):
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
    )


def candidate():
    return Candidate("exact_user", "source_user", CandidateProviderType.FOLLOWERS)


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
            hierarchy(
                node(
                    text="exact_user",
                    resource_id=instagram_id("row_search_user_username"),
                    bounds="[20,0][30,10]",
                )
            ),
        )
    )
    provider = make_provider(device)

    result = provider.locate_source(make_context(tmp_path), "exact_user")

    assert result.status is AndroidFollowStatus.SUCCESS
    assert device.keys == [("exact_user", True)]
    assert device.clicks[-1] == (25, 5)


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
            hierarchy(
                node(
                    text="exact_user",
                    resource_id=instagram_id("row_user_primary_name"),
                    bounds="[140,0][160,20]",
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
    wrong = node(
        text="exact_user_fan",
        resource_id=instagram_id("row_user_primary_name"),
        bounds="[200,0][220,20]",
    )
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
                node(text="exact_user", resource_id=instagram_id("action_bar_title"))
            ),
        )
    )

    profile = make_provider(device).open_profile(make_context(tmp_path), candidate())

    assert profile.username == "exact_user"


def test_contact_scraping_opens_delegates_and_closes_popup(tmp_path):
    popup = hierarchy(node(text="target@example.com"))
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

    result = make_provider(device, scraper).scrape_contact(make_context(tmp_path))

    assert result.status is AndroidFollowStatus.CONTACT_NOT_AVAILABLE
    assert scraper.calls == []
    assert device.presses == []


def test_contact_scraping_fails_when_profile_does_not_return(tmp_path):
    device = FakeDevice(
        (
            hierarchy(
                node(
                    description="Contact",
                    resource_id=instagram_id("button_container"),
                )
            ),
            hierarchy(node(text="target@example.com")),
            hierarchy(node(text="Contact")),
        )
    )

    result = make_provider(device).scrape_contact(make_context(tmp_path))

    assert result.status is AndroidFollowStatus.FOLLOW_FAILED
    assert "profile screen did not return" in result.detail
    assert device.presses == ["back"]


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
    assert 3 in sleeps


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

    assert 2 in sleeps


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
