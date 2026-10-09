from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from IGBot.runtime import RuntimeContext, SessionContext
from IGBot.runtime.candidates import (
    Candidate,
    CandidateProviderType,
    CandidateResult,
    CandidateResultStatus,
)
from IGBot.runtime.database import RuntimeDatabase
from IGBot.runtime.eligibility import (
    native_account_configuration_ready,
    native_like_configuration_ready,
)
from IGBot.runtime.follow import (
    AndroidFollowResult,
    AndroidFollowStatus,
    CandidateProfile,
    ConfiguredFollowCandidateQualifier,
    FollowFilterSettings,
    TextFilterSettings,
)
from IGBot.runtime.ignore import IgnoreService
from IGBot.runtime.like import (
    AndroidLikeProvider,
    AndroidLikeResult,
    AndroidLikeStatus,
    LikeMediaType,
    LikeModule,
    LikeModuleSettings,
    LikePostFilterSettings,
    SpecificLikeCandidates,
    SpecificLikePersistence,
    SpecificLikeSynchronizer,
)
from IGBot.runtime.navigation import NavigationResult, NavigationStatus
from IGBot.runtime.scheduler import ModuleExecutionOutcome

SNAPSHOTS = Path(__file__).parents[1] / "snapshots" / "R5CR61HA38V"


class Logger:
    def __getattr__(self, _name):
        return lambda *_args, **_kwargs: None


def context(tmp_path):
    return RuntimeContext(
        SessionContext(
            uuid4(),
            "account",
            "phone",
            "com.instagram.androie",
            tmp_path,
            datetime.now(timezone.utc),
        ),
        Logger(),
    )


def hierarchy(*nodes):
    return "<hierarchy>" + "".join(nodes) + "</hierarchy>"


def node(resource_id, *, description="", bounds="[0,0][100,100]"):
    return (
        f'<node resource-id="com.instagram.androie:id/{resource_id}" '
        f'content-desc="{description}" bounds="{bounds}" />'
    )


def profile_grid(*posts, username="target"):
    return hierarchy(
        node("action_bar_title", description=username),
        node("swipeable_nav_view_pager_inner_recycler_view"),
        *(posts or (node("image_button", description="profile media"),)),
    )


class Clock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class Device:
    def __init__(self, hierarchies):
        self.hierarchies = list(hierarchies)
        self.last = self.hierarchies[-1]
        self.clicks = []
        self.presses = []
        self.swipes = []
        self.idle_waits = []

        class JsonRpc:
            def __init__(self, owner):
                self.owner = owner

            def waitForIdle(self, timeout_ms):
                self.owner.idle_waits.append(timeout_ms)

        self.jsonrpc = JsonRpc(self)

    def dump_hierarchy(self, compressed=False):
        assert compressed is False
        if self.hierarchies:
            self.last = self.hierarchies.pop(0)
        return self.last

    def click(self, x, y):
        self.clicks.append((x, y))

    def press(self, key):
        self.presses.append(key)

    def swipe(self, *args, **kwargs):
        self.swipes.append((args, kwargs))

    def window_size(self):
        return (1080, 1875)


class ProfileNavigation:
    def __init__(self, profile=None, *, followers_restore_succeeds=True):
        self.returned = 0
        self.profile = profile
        self.followers_restore_succeeds = followers_restore_succeeds

    def open_candidate_profile(self, _context, _candidate):
        return AndroidFollowResult(AndroidFollowStatus.SUCCESS, profile=self.profile)

    def return_to_followers(self, _context):
        self.returned += 1
        return AndroidFollowResult(
            AndroidFollowStatus.SUCCESS
            if self.followers_restore_succeeds
            else AndroidFollowStatus.FOLLOW_FAILED
        )


@pytest.mark.parametrize(
    ("profile_overrides", "filter_settings"),
    (
        ({"posts": 2}, FollowFilterSettings(allow_private=True, min_posts=3)),
        (
            {"followers": 9},
            FollowFilterSettings(allow_private=True, min_followers=10),
        ),
        (
            {"followers": 101},
            FollowFilterSettings(allow_private=True, max_followers=100),
        ),
        (
            {"following": 9},
            FollowFilterSettings(allow_private=True, min_following=10),
        ),
        (
            {"following": 101},
            FollowFilterSettings(allow_private=True, max_following=100),
        ),
        (
            {"biography": "Landscape photographer"},
            FollowFilterSettings(
                allow_private=True,
                keywords=TextFilterSettings(required=("ceramics",)),
            ),
        ),
        (
            {"biography": "Spam promotions"},
            FollowFilterSettings(
                allow_private=True,
                keywords=TextFilterSettings(blocked=("spam",)),
            ),
        ),
        (
            {"display_name": "Иван", "biography": "Photography"},
            FollowFilterSettings(allow_private=True, allowed_alphabets=("latin",)),
        ),
    ),
)
def test_like_profile_filters_reject_before_device_interaction(
    tmp_path, profile_overrides, filter_settings
):
    candidate = Candidate("target", "source", CandidateProviderType.FOLLOWERS)
    profile = CandidateProfile(candidate, "target", **profile_overrides)
    navigation = ProfileNavigation(profile)
    provider = AndroidLikeProvider(
        navigation,
        profile_filters=filter_settings,
        device_factory=lambda _serial: pytest.fail(
            "Rejected profiles must not begin scrolling or media selection"
        ),
    )

    result = provider.execute(context(tmp_path), candidate)

    assert result.status is AndroidLikeStatus.FILTER_REJECTED
    assert navigation.returned == 1


def test_like_biography_language_reuses_follow_language_qualifier(tmp_path):
    candidate = Candidate("target", "source", CandidateProviderType.FOLLOWERS)
    profile = CandidateProfile(
        candidate, "target", display_name="Hans", biography="Fotografie in Berlin"
    )
    navigation = ProfileNavigation(profile)
    provider = AndroidLikeProvider(
        navigation,
        profile_filters=FollowFilterSettings(
            allow_private=True, biography_languages=("en",)
        ),
        profile_qualifier=ConfiguredFollowCandidateQualifier(lambda _text: "de"),
        device_factory=lambda _serial: pytest.fail(
            "Rejected profiles must not begin scrolling or media selection"
        ),
    )

    result = provider.execute(context(tmp_path), candidate)

    assert result.status is AndroidLikeStatus.FILTER_REJECTED
    assert navigation.returned == 1


def test_specific_like_rejects_mismatched_opened_profile_before_any_interaction(
    tmp_path,
):
    wrong = CandidateProfile(
        candidate=Candidate(
            "wrong_user", "specific_users", CandidateProviderType.SPECIFIC_ACCOUNTS
        ),
        username="wrong_user",
    )
    navigation = ProfileNavigation(profile=wrong)
    provider = AndroidLikeProvider(
        navigation,
        device_factory=lambda _serial: pytest.fail(
            "Like UI must not start for a mismatched profile"
        ),
    )

    result = provider.execute(
        context(tmp_path),
        Candidate(
            "requested_user",
            "specific_users",
            CandidateProviderType.SPECIFIC_ACCOUNTS,
        ),
    )

    assert result.status is AndroidLikeStatus.PROFILE_UNAVAILABLE
    assert navigation.returned == 1


def test_like_defensive_profile_ignore_check_runs_before_interaction(tmp_path):
    candidate = Candidate("expected", "source", CandidateProviderType.FOLLOWERS)
    opened = CandidateProfile(candidate, "unexpected_ignored")
    navigation = ProfileNavigation(profile=opened)
    runtime_context = context(tmp_path)
    runtime_context.ignore_service = IgnoreService(frozenset({"unexpected_ignored"}))
    provider = AndroidLikeProvider(
        navigation,
        device_factory=lambda _serial: pytest.fail(
            "Ignored opened profile must not reach Like UI"
        ),
    )

    result = provider.execute(runtime_context, candidate)

    assert result.status is AndroidLikeStatus.IGNORED
    assert navigation.returned == 1


@pytest.mark.parametrize(
    ("opened", "expected"),
    (
        (
            AndroidFollowResult(AndroidFollowStatus.SOURCE_NOT_FOUND),
            AndroidLikeStatus.PROFILE_NOT_FOUND,
        ),
        (
            AndroidFollowResult(
                AndroidFollowStatus.FOLLOW_FAILED, navigation_failed=True
            ),
            AndroidLikeStatus.NAVIGATION_FAILED,
        ),
        (
            AndroidFollowResult(AndroidFollowStatus.FOLLOW_FAILED),
            AndroidLikeStatus.PROFILE_UNAVAILABLE,
        ),
    ),
)
def test_specific_like_preserves_search_and_profile_failure_statuses(
    tmp_path, opened, expected
):
    class FailedNavigation:
        def open_candidate_profile(self, _context, _candidate):
            return opened

    provider = AndroidLikeProvider(FailedNavigation())

    result = provider.execute(
        context(tmp_path),
        Candidate("target", "specific_users", CandidateProviderType.SPECIFIC_ACCOUNTS),
    )

    assert result.status is expected


def test_xml_selectors_identify_only_fully_visible_grid_rows():
    provider = AndroidLikeProvider(ProfileNavigation())
    xml = (SNAPSHOTS / "2026-09-23_21-06-40.xml").read_text(encoding="utf-8")

    posts = provider._fully_visible_grid_posts(xml)

    assert len(posts) == 3
    assert all(post.bounds[1] == 1326 for post in posts)
    assert any(post.description.startswith("Photo by") for post in posts)


def test_production_xml_selectors_detect_reel_and_carousel():
    provider = AndroidLikeProvider(ProfileNavigation())
    reel = (SNAPSHOTS / "2026-09-24_16-11-31.xml").read_text(encoding="utf-8")
    carousel = (SNAPSHOTS / "2026-09-23_21-08-45.xml").read_text(encoding="utf-8")

    assert provider._detect_media(reel) is LikeMediaType.REEL
    assert provider._detect_media(carousel) is LikeMediaType.CAROUSEL


def test_media_detection_uses_resource_ids_instead_of_visible_text():
    provider = AndroidLikeProvider(ProfileNavigation())
    photo = hierarchy(
        node("row_feed_profile_header", description="localized header"),
        node("row_feed_button_like", description="Like"),
    )
    carousel = hierarchy(
        node("row_feed_profile_header", description="localized header"),
        node("carousel_media_group"),
        node("row_feed_button_like", description="Like"),
    )
    reel = hierarchy(
        node("row_feed_profile_header", description="localized header"),
        node("video_container"),
        node("row_feed_button_like", description="Like"),
    )

    assert provider._detect_media(photo) is LikeMediaType.PHOTO
    assert provider._detect_media(carousel) is LikeMediaType.CAROUSEL
    assert provider._detect_media(reel) is LikeMediaType.REEL


def test_production_thumbnail_context_menu_is_detected_before_media_actions():
    xml = (SNAPSHOTS / "2026-09-24_21-44-44.xml").read_text(encoding="utf-8")
    provider = AndroidLikeProvider(ProfileNavigation(), load_timeout=0)

    destination, loaded = provider._wait_for_post(Device([xml]))

    assert destination == "overlay"
    assert loaded == xml


def test_production_peek_preview_is_detected_as_unexpected_overlay():
    xml = (SNAPSHOTS / "2026-09-26_18-10-13.xml").read_text(encoding="utf-8")
    provider = AndroidLikeProvider(ProfileNavigation(), load_timeout=0)

    destination, loaded = provider._wait_for_post(Device([xml]))

    assert destination == "overlay"
    assert loaded == xml
    nodes = provider._nodes(xml)
    assert provider._find(nodes, "context_menu") is not None
    assert provider._find(nodes, "peek_container") is not None


def test_hidden_like_controls_trigger_one_small_media_scroll():
    hidden = (SNAPSHOTS / "2026-09-24_22-15-27.xml").read_text(encoding="utf-8")
    visible = hierarchy(
        node("row_feed_profile_header"),
        node("carousel_media_group", bounds="[0,434][1080,1776]"),
        node(
            "row_feed_button_like",
            description="Like",
            bounds="[36,1574][108,1712]",
        ),
    )
    device = Device([visible, visible])
    clock = Clock()
    provider = AndroidLikeProvider(
        ProfileNavigation(),
        sleeper=clock.sleep,
        clock=clock,
        poll_interval=0.2,
    )

    prepared = provider._prepare_media_controls(device, hidden, LikeMediaType.CAROUSEL)

    assert prepared == visible
    assert device.swipes == [((540, 1775, 540, 1540), {"duration": 0.3})]
    assert device.idle_waits == [3000]


def test_visible_like_controls_do_not_scroll_media():
    visible = hierarchy(
        node("row_feed_profile_header"),
        node("carousel_media_group", bounds="[0,434][1080,1514]"),
        node(
            "row_feed_button_like",
            description="Like",
            bounds="[36,1574][108,1712]",
        ),
    )
    device = Device([visible])
    provider = AndroidLikeProvider(ProfileNavigation())

    prepared = provider._prepare_media_controls(device, visible, LikeMediaType.CAROUSEL)

    assert prepared == visible
    assert device.swipes == []
    assert device.idle_waits == []


def test_context_menu_is_swiped_down_and_profile_grid_is_verified():
    menu = hierarchy(node("context_menu", bounds="[60,1041][590,1776]"))
    profile = profile_grid()
    device = Device([profile, profile, profile])
    provider = AndroidLikeProvider(ProfileNavigation(), load_timeout=0.5)

    restored = provider._dismiss_unexpected_overlay(device, "target", menu)

    assert restored is True
    assert device.swipes == [((325, 1286, 325, 1874), {"duration": 0.3})]
    assert device.clicks == []


def test_context_menu_uses_one_outside_tap_when_swipe_does_not_restore_grid():
    menu = hierarchy(node("context_menu", bounds="[60,1041][590,1776]"))
    profile = profile_grid()
    device = Device([menu, menu, menu, profile, profile, profile])
    clock = Clock()
    provider = AndroidLikeProvider(
        ProfileNavigation(),
        sleeper=clock.sleep,
        clock=clock,
        load_timeout=0.2,
        poll_interval=0.1,
    )

    restored = provider._dismiss_unexpected_overlay(device, "target", menu)

    assert restored is True
    assert device.clicks == [(1056, 1851)]


def test_profile_recovery_cannot_succeed_while_peek_preview_remains():
    peek = hierarchy(
        node("peek_container"),
        node("action_bar_title", description="target"),
        node("swipeable_nav_view_pager_inner_recycler_view"),
        node("image_button", description="media"),
    )
    clock = Clock()
    provider = AndroidLikeProvider(
        ProfileNavigation(),
        sleeper=clock.sleep,
        clock=clock,
        load_timeout=0.2,
        poll_interval=0.1,
    )

    assert (
        provider._wait_for_profile_grid(Device([peek, peek, peek]), "target") is False
    )


def test_thumbnail_is_revalidated_from_fresh_hierarchy_before_tap():
    bounds = "[0,1000][356,1450]"
    original = hierarchy(node("image_button", description="media-a", bounds=bounds))
    changed = hierarchy(node("image_button", description="media-b", bounds=bounds))
    device = Device([changed, changed])
    provider = AndroidLikeProvider(ProfileNavigation(), choice=lambda posts: posts[0])
    attempted = set()

    state, selected = provider._select_revalidated_thumbnail(
        device, original, attempted
    )

    assert state == "selected"
    assert selected.description == "media-b"
    assert ("description", "media-a") in attempted
    assert device.clicks == []


def test_previously_processed_thumbnail_is_not_selected_again():
    first = node("image_button", description="media-a", bounds="[0,1000][356,1450]")
    second = node("image_button", description="media-b", bounds="[362,1000][718,1450]")
    current = hierarchy(first, second)
    device = Device([current])
    provider = AndroidLikeProvider(ProfileNavigation(), choice=lambda posts: posts[0])

    state, selected = provider._select_revalidated_thumbnail(
        device, current, {("description", "media-a")}
    )

    assert state == "selected"
    assert selected.description == "media-b"


def test_configured_view_times_use_shared_range_resolution():
    provider = AndroidLikeProvider(
        ProfileNavigation(),
        photo_view_time="2-4",
        reel_view_time="5-7",
        random_seconds=lambda minimum, maximum: (minimum + maximum) / 2,
    )

    assert provider._view_time(LikeMediaType.PHOTO) == 3
    assert provider._view_time(LikeMediaType.CAROUSEL) == 3
    assert provider._view_time(LikeMediaType.REEL) == 6


def test_zero_view_time_likes_immediately():
    provider = AndroidLikeProvider(
        ProfileNavigation(), photo_view_time="0-0", reel_view_time="0-0"
    )

    assert provider._view_time(LikeMediaType.PHOTO) == 0
    assert provider._view_time(LikeMediaType.CAROUSEL) == 0
    assert provider._view_time(LikeMediaType.REEL) == 0


def test_verified_photo_like_returns_to_followers(tmp_path):
    grid = hierarchy(
        node(
            "image_button",
            description="Photo by Target at Row 1, Column 2",
            bounds="[362,1000][718,1450]",
        )
    )
    post = hierarchy(
        node("row_feed_profile_header", description="target posted a photo today"),
        node("row_feed_button_like", description="Like"),
    )
    liked = hierarchy(
        node("row_feed_profile_header", description="target posted a photo today"),
        node("row_feed_button_like", description="Liked"),
    )
    profile = profile_grid()
    device = Device(
        [
            grid,
            grid,
            grid,
            post,
            liked,
            liked,
            liked,
            liked,
            liked,
            profile,
            profile,
            profile,
        ]
    )
    navigation = ProfileNavigation()
    clock = Clock()
    provider = AndroidLikeProvider(
        navigation,
        device_factory=lambda _serial: device,
        sleeper=clock.sleep,
        clock=clock,
        choice=lambda posts: posts[0],
        natural_delay=lambda: 0,
        poll_interval=0.25,
        stability_window=0.75,
    )

    result = provider.execute(
        context(tmp_path),
        Candidate("target", "source", CandidateProviderType.FOLLOWERS),
    )

    assert result.status is AndroidLikeStatus.SUCCESS
    assert len(device.clicks) == 2
    assert device.presses == ["back"]
    assert navigation.returned == 1
    assert result.navigation.status is NavigationStatus.SUCCESS


def test_verified_like_remains_success_when_profile_restoration_fails(tmp_path):
    grid = hierarchy(
        node("image_button", description="media", bounds="[0,1000][356,1450]")
    )
    post = hierarchy(
        node("row_feed_profile_header"),
        node("row_feed_button_like", description="Like"),
    )
    liked = hierarchy(
        node("row_feed_profile_header"),
        node("row_feed_button_like", description="Liked"),
    )
    device = Device([grid, grid, grid, post, liked, liked, liked, liked])
    clock = Clock()
    provider = AndroidLikeProvider(
        ProfileNavigation(),
        device_factory=lambda _serial: device,
        sleeper=clock.sleep,
        clock=clock,
        choice=lambda posts: posts[0],
        natural_delay=lambda: 0,
        poll_interval=0.25,
        stability_window=0.75,
        load_timeout=0.5,
    )

    result = provider.execute(
        context(tmp_path),
        Candidate("target", "source", CandidateProviderType.FOLLOWERS),
    )

    assert result.status is AndroidLikeStatus.SUCCESS
    assert result.likes_completed == 1
    assert result.navigation.status is NavigationStatus.FAILED
    assert result.navigation.detail == "Profile did not return after the Like."


def test_verified_like_remains_success_when_followers_restoration_fails(tmp_path):
    grid = hierarchy(
        node("image_button", description="media", bounds="[0,1000][356,1450]")
    )
    post = hierarchy(
        node("row_feed_profile_header"),
        node("row_feed_button_like", description="Like"),
    )
    liked = hierarchy(
        node("row_feed_profile_header"),
        node("row_feed_button_like", description="Liked"),
    )
    profile = profile_grid()
    navigation = ProfileNavigation(followers_restore_succeeds=False)
    device = Device(
        [grid, grid, grid, post, liked, liked, liked, liked, profile, profile, profile]
    )
    clock = Clock()
    provider = AndroidLikeProvider(
        navigation,
        device_factory=lambda _serial: device,
        sleeper=clock.sleep,
        clock=clock,
        choice=lambda posts: posts[0],
        natural_delay=lambda: 0,
        poll_interval=0.25,
        stability_window=0.75,
    )

    result = provider.execute(
        context(tmp_path),
        Candidate("target", "source", CandidateProviderType.FOLLOWERS),
    )

    assert result.status is AndroidLikeStatus.SUCCESS
    assert result.likes_completed == 1
    assert result.navigation.status is NavigationStatus.FAILED
    assert result.navigation.detail == (
        "Followers list did not return after the Like session."
    )
    assert result.navigation.expected == "Followers list"
    assert result.navigation.actual == "Candidate profile / Unknown"


def test_navigation_failure_without_verified_like_remains_navigation_failed():
    result = AndroidLikeResult(
        AndroidLikeStatus.NAVIGATION_FAILED,
        likes_completed=0,
        navigation=NavigationResult(NavigationStatus.FAILED),
    )

    assert result.status is AndroidLikeStatus.NAVIGATION_FAILED


def test_verified_like_cannot_encode_navigation_failure_as_interaction_status():
    with pytest.raises(ValueError, match="post-interaction navigation"):
        AndroidLikeResult(
            AndroidLikeStatus.NAVIGATION_FAILED,
            likes_completed=1,
            navigation=NavigationResult(NavigationStatus.FAILED),
        )


def test_private_profile_returns_without_scrolling(tmp_path):
    candidate = Candidate("target", "source", CandidateProviderType.FOLLOWERS)
    navigation = ProfileNavigation(
        CandidateProfile(candidate, "target", is_private=True)
    )
    provider = AndroidLikeProvider(
        navigation, device_factory=lambda _serial: (_ for _ in ()).throw(AssertionError)
    )

    result = provider.execute(context(tmp_path), candidate)

    assert result.status is AndroidLikeStatus.PRIVATE_SKIPPED
    assert navigation.returned == 1


def test_zero_post_profile_returns_without_connecting_or_scrolling(tmp_path):
    candidate = Candidate("target", "source", CandidateProviderType.FOLLOWERS)
    navigation = ProfileNavigation(CandidateProfile(candidate, "target", posts=0))
    provider = AndroidLikeProvider(
        navigation, device_factory=lambda _serial: (_ for _ in ()).throw(AssertionError)
    )

    result = provider.execute(context(tmp_path), candidate)

    assert result.status is AndroidLikeStatus.NO_POSTS
    assert result.likes_completed == 0
    assert navigation.returned == 1


def test_initial_scroll_exposes_more_of_profile_grid():
    device = Device(["<hierarchy />"])
    provider = AndroidLikeProvider(ProfileNavigation())

    provider._scroll_profile(device)

    coordinates, options = device.swipes[0]
    assert coordinates == (540, 1387, 540, 843)
    assert options == {"duration": 0.4}


@pytest.mark.parametrize(
    "snapshot_name",
    ("2026-09-26_18-30-39.xml", "2026-09-26_18-31-06.xml"),
)
def test_production_suggested_profile_layouts_use_stable_resource_ids(
    snapshot_name,
):
    provider = AndroidLikeProvider(ProfileNavigation())
    xml = (SNAPSHOTS / snapshot_name).read_text(encoding="utf-8")
    nodes = provider._nodes(xml)

    assert provider._has_suggested_profile_section(nodes) is True
    assert {
        provider._suffix(item.resource_id)
        for item in nodes
        if provider._suffix(item.resource_id) in provider._SUGGESTED_PROFILE_IDS
    } == {
        "similar_accounts_container",
        "similar_accounts_carousel_header",
        "similar_accounts_carousel_title",
    }


def test_suggested_profile_section_receives_one_additional_scroll():
    suggested = hierarchy(node("similar_accounts_container"))
    grid = hierarchy(
        node("image_button", description="media-a", bounds="[0,1000][356,1450]")
    )
    device = Device([suggested, grid, grid])
    provider = AndroidLikeProvider(
        ProfileNavigation(), sleeper=lambda _seconds: None, natural_delay=lambda: 0
    )

    result = provider._settle_scroll_and_read_profile(device, initial=True)

    assert result == grid
    assert len(device.swipes) == 2
    assert device.idle_waits == [3000, 3000]


def test_suggested_profile_section_does_not_scroll_more_than_once_again():
    suggested = hierarchy(node("similar_accounts_carousel_header"))
    no_grid = hierarchy(node("profile_header_container"))
    clock = Clock()
    device = Device([suggested, no_grid, no_grid, no_grid])
    provider = AndroidLikeProvider(
        ProfileNavigation(),
        sleeper=clock.sleep,
        clock=clock,
        natural_delay=lambda: 0,
        load_timeout=0.4,
        poll_interval=0.2,
    )

    result = provider._settle_scroll_and_read_profile(device, initial=True)

    assert result is None
    assert len(device.swipes) == 2
    assert device.idle_waits == [3000, 3000]


def test_profile_settles_before_and_after_scroll_before_hierarchy_is_read():
    events = []

    class OrderedDevice(Device):
        def swipe(self, *args, **kwargs):
            events.append("scroll")
            super().swipe(*args, **kwargs)

        def dump_hierarchy(self, compressed=False):
            events.append("hierarchy")
            return super().dump_hierarchy(compressed=compressed)

        def __init__(self, hierarchies):
            super().__init__(hierarchies)
            original = self.jsonrpc.waitForIdle

            def wait_for_idle(timeout_ms):
                events.append(("idle", timeout_ms))
                original(timeout_ms)

            self.jsonrpc.waitForIdle = wait_for_idle

    delays = iter((0.31, 0.79))
    grid = hierarchy(node("image_button", bounds="[0,1000][356,1450]"))
    device = OrderedDevice([grid, grid])
    provider = AndroidLikeProvider(
        ProfileNavigation(),
        sleeper=lambda seconds: events.append(("settle", seconds)),
        natural_delay=lambda: next(delays),
    )

    result = provider._settle_scroll_and_read_profile(device, initial=True)

    assert result == grid
    assert events == [
        ("settle", 0.31),
        "scroll",
        ("idle", 3000),
        ("settle", 0.79),
        "hierarchy",
        ("settle", 0.2),
        "hierarchy",
    ]


def test_between_like_scroll_uses_the_same_settled_sequence():
    events = []

    class OrderedDevice(Device):
        def swipe(self, *args, **kwargs):
            events.append("scroll")
            super().swipe(*args, **kwargs)

        def dump_hierarchy(self, compressed=False):
            events.append("hierarchy")
            return super().dump_hierarchy(compressed=compressed)

        def __init__(self, hierarchies):
            super().__init__(hierarchies)
            original = self.jsonrpc.waitForIdle

            def wait_for_idle(timeout_ms):
                events.append(("idle", timeout_ms))
                original(timeout_ms)

            self.jsonrpc.waitForIdle = wait_for_idle

    grid = hierarchy(node("image_button", bounds="[0,1000][356,1450]"))
    device = OrderedDevice([grid, grid])
    provider = AndroidLikeProvider(
        ProfileNavigation(),
        sleeper=lambda seconds: events.append(("settle", seconds)),
        natural_delay=lambda: 0.5,
    )

    provider._settle_scroll_and_read_profile(device, initial=False)

    assert events == [
        ("settle", 0.5),
        "scroll",
        ("idle", 3000),
        ("settle", 0.5),
        "hierarchy",
        ("settle", 0.2),
        "hierarchy",
    ]
    coordinates, options = device.swipes[0]
    assert coordinates == (540, 1256, 540, 1068)
    assert options == {"duration": 0.3}


def test_profile_grid_timeout_never_returns_unverified_hierarchy():
    bounds = "[0,1000][356,1450]"
    device = Device(
        [
            hierarchy(node("image_button", description="media-a", bounds=bounds)),
            hierarchy(node("image_button", description="media-b", bounds=bounds)),
            hierarchy(node("image_button", description="media-c", bounds=bounds)),
        ]
    )
    clock = Clock()
    provider = AndroidLikeProvider(
        ProfileNavigation(),
        sleeper=clock.sleep,
        clock=clock,
        load_timeout=0.4,
        poll_interval=0.2,
    )

    assert provider._wait_for_stable_profile_grid(device) is None


def test_profile_grid_stability_includes_media_identity_and_bounds():
    bounds = "[0,1000][356,1450]"
    first = hierarchy(node("image_button", description="media-a", bounds=bounds))
    second = hierarchy(node("image_button", description="media-b", bounds=bounds))
    device = Device([first, second, second])
    clock = Clock()
    provider = AndroidLikeProvider(
        ProfileNavigation(),
        sleeper=clock.sleep,
        clock=clock,
        load_timeout=1,
        poll_interval=0.2,
    )

    assert provider._wait_for_stable_profile_grid(device) == second
    assert clock.sleeps == [0.2, 0.2]


def test_return_to_profile_requires_username_grid_and_recycler():
    title_only = hierarchy(node("action_bar_title", description="target"))
    grid_without_recycler = hierarchy(
        node("action_bar_title", description="target"),
        node("image_button", description="media"),
    )
    clock = Clock()
    provider = AndroidLikeProvider(
        ProfileNavigation(),
        sleeper=clock.sleep,
        clock=clock,
        load_timeout=0.4,
        poll_interval=0.2,
    )

    assert (
        provider._wait_for_profile(
            Device([title_only, grid_without_recycler, grid_without_recycler]), "target"
        )
        is False
    )
    assert provider._wait_for_profile(Device([profile_grid()]), "target") is True


def test_unstable_profile_preparation_abandons_before_thumbnail_selection(tmp_path):
    bounds = "[0,1000][356,1450]"
    device = Device(
        [
            hierarchy(node("image_button", description="media-a", bounds=bounds)),
            hierarchy(node("image_button", description="media-b", bounds=bounds)),
            hierarchy(node("image_button", description="media-c", bounds=bounds)),
        ]
    )
    navigation = ProfileNavigation()
    clock = Clock()
    provider = AndroidLikeProvider(
        navigation,
        device_factory=lambda _serial: device,
        sleeper=clock.sleep,
        clock=clock,
        natural_delay=lambda: 0,
        load_timeout=0.4,
        poll_interval=0.2,
    )

    result = provider.execute(
        context(tmp_path),
        Candidate("target", "source", CandidateProviderType.FOLLOWERS),
    )

    assert result.status is AndroidLikeStatus.PROFILE_UNAVAILABLE
    assert device.clicks == []
    assert navigation.returned == 1


def test_failed_thumbnail_retries_another_visible_post(tmp_path):
    first = node("image_button", bounds="[0,1000][356,1450]")
    second = node("image_button", bounds="[362,1000][718,1450]")
    grid = hierarchy(first, second)
    profile = profile_grid(first, second)
    post = hierarchy(
        node("row_feed_profile_header"),
        node("row_feed_button_like", description="Like"),
    )
    liked = hierarchy(
        node("row_feed_profile_header"),
        node("row_feed_button_like", description="Liked"),
    )
    device = Device(
        [
            grid,
            grid,
            profile,
            profile,
            profile,
            profile,
            profile,
            profile,
            profile,
            grid,
            grid,
            grid,
            post,
            liked,
            liked,
            liked,
            liked,
            liked,
            profile,
            profile,
            profile,
        ]
    )
    clock = Clock()
    provider = AndroidLikeProvider(
        ProfileNavigation(),
        device_factory=lambda _serial: device,
        sleeper=clock.sleep,
        clock=clock,
        choice=lambda posts: posts[0],
        natural_delay=lambda: 0,
        load_timeout=0.5,
        poll_interval=0.25,
        stability_window=0.75,
    )

    result = provider.execute(
        context(tmp_path),
        Candidate("target", "source", CandidateProviderType.FOLLOWERS),
    )

    assert result.status is AndroidLikeStatus.SUCCESS
    assert device.clicks[:2] == [(178, 1225), (540, 1225)]


def test_two_likes_per_profile_refreshes_grid_between_verified_likes(tmp_path):
    first = node(
        "image_button",
        description="Photo by Target at Row 1, Column 1",
        bounds="[0,1000][356,1450]",
    )
    second = node(
        "image_button",
        description="Photo by Target at Row 1, Column 2",
        bounds="[362,1000][718,1450]",
    )
    post = hierarchy(
        node("row_feed_profile_header"),
        node("row_feed_button_like", description="Like"),
    )
    liked = hierarchy(
        node("row_feed_profile_header"),
        node("row_feed_button_like", description="Liked"),
    )
    profile = profile_grid(first, second)
    device = Device(
        [
            hierarchy(first),
            hierarchy(first),
            hierarchy(first),
            post,
            liked,
            liked,
            liked,
            liked,
            liked,
            profile,
            profile,
            profile,
            hierarchy(first, second),
            hierarchy(first, second),
            hierarchy(first, second),
            post,
            liked,
            liked,
            liked,
            liked,
            liked,
            profile,
            profile,
            profile,
        ]
    )
    clock = Clock()
    navigation = ProfileNavigation()
    provider = AndroidLikeProvider(
        navigation,
        device_factory=lambda _serial: device,
        sleeper=clock.sleep,
        clock=clock,
        choice=lambda posts: posts[0],
        natural_delay=lambda: 0,
        likes_per_profile="2-2",
        poll_interval=0.25,
        stability_window=0.75,
    )

    result = provider.execute(
        context(tmp_path),
        Candidate("target", "source", CandidateProviderType.FOLLOWERS),
    )

    assert result.status is AndroidLikeStatus.SUCCESS
    assert result.likes_completed == 2
    assert device.clicks == [(178, 1225), (50, 50), (540, 1225), (50, 50)]
    assert len(device.swipes) == 2
    assert device.presses == ["back", "back"]
    assert navigation.returned == 1


@pytest.mark.parametrize(
    ("media_node", "media_type", "expected_view", "expected_after_like"),
    [
        ("carousel_media_group", LikeMediaType.CAROUSEL, 1.0, 0.0),
        ("video_container", LikeMediaType.REEL, 2.0, 2.0),
    ],
)
def test_carousel_and_reel_share_like_verification(
    tmp_path, media_node, media_type, expected_view, expected_after_like
):
    grid = hierarchy(
        node(
            "image_button",
            description="media",
            bounds="[362,1000][718,1450]",
        )
    )
    post = hierarchy(
        node("row_feed_profile_header"),
        node(media_node),
        node("row_feed_button_like", description="Like"),
    )
    liked = hierarchy(
        node("row_feed_profile_header"),
        node(media_node),
        node("row_feed_button_like", description="Liked"),
    )
    profile = profile_grid()
    device = Device(
        [grid, grid, grid, post, liked, liked, liked, liked, profile, profile, profile]
    )
    clock = Clock()
    provider = AndroidLikeProvider(
        ProfileNavigation(),
        device_factory=lambda _serial: device,
        sleeper=clock.sleep,
        clock=clock,
        choice=lambda posts: posts[0],
        natural_delay=lambda: 0,
        photo_view_time=1,
        reel_view_time=2,
        post_like_reel_delay=lambda: 2,
        poll_interval=0.25,
        stability_window=0.75,
    )

    result = provider.execute(
        context(tmp_path),
        Candidate("target", "source", CandidateProviderType.FOLLOWERS),
    )

    assert result.status is AndroidLikeStatus.SUCCESS
    assert expected_view in clock.sleeps
    assert (2 in clock.sleeps) is (expected_after_like == 2)
    assert provider._detect_media(post) is media_type


@pytest.mark.parametrize(
    ("snapshot_name", "expected"),
    (
        ("2026-09-24_15-59-36.xml", 7),
        ("2026-09-24_15-59-52.xml", 8),
        ("2026-09-26_20-46-59.xml", None),
    ),
)
def test_production_media_layouts_parse_only_explicit_numeric_like_counts(
    snapshot_name, expected
):
    provider = AndroidLikeProvider(ProfileNavigation())
    xml = (SNAPSHOTS / snapshot_name).read_text(encoding="utf-8")

    assert provider._visible_like_count(xml) == expected


@pytest.mark.parametrize(
    ("minimum", "maximum", "count", "allowed"),
    (
        (10, None, 9, False),
        (10, None, 10, True),
        (None, 20, 20, True),
        (None, 20, 21, False),
        (10, 20, 15, True),
    ),
)
def test_visible_like_count_range_boundaries(minimum, maximum, count, allowed):
    provider = AndroidLikeProvider(
        ProfileNavigation(),
        post_filters=LikePostFilterSettings(minimum, maximum),
    )

    assert provider._like_count_allowed(count) is allowed


class PostFilterFlowProvider(AndroidLikeProvider):
    def __init__(self, navigation, media, **kwargs):
        super().__init__(navigation, **kwargs)
        self.media = iter(media)
        self.selections = 0

    def _settle_scroll_and_read_profile(self, _device, *, initial):
        return hierarchy(node("image_button", description=f"media-{self.selections}"))

    def _select_revalidated_thumbnail(self, _device, _hierarchy, _attempted):
        self.selections += 1
        return (
            "selected",
            self._nodes(
                hierarchy(
                    node(
                        "image_button",
                        description=f"media-{self.selections}",
                        bounds=f"[{self.selections},1000][356,1450]",
                    )
                )
            )[0],
        )

    def _wait_for_post(self, _device):
        return ("media", next(self.media))

    def _prepare_media_controls(self, _device, loaded, _media_type):
        return loaded

    def _verify_liked(self, _device):
        return AndroidLikeStatus.SUCCESS

    def _return_to_profile(self, _device, _username):
        return True

    def _return_to_followers(self, _context, _device, _username):
        return True


def media_with_like_count(count=None):
    description = "Photo by Target"
    if count is not None:
        description += f", {count} likes"
    else:
        description += ", Liked by someone and others"
    return hierarchy(
        node("row_feed_profile_header"),
        node("carousel_image", description=description),
        node("row_feed_button_like", description="Like"),
    )


def test_out_of_range_post_returns_to_profile_and_tries_another(tmp_path):
    candidate = Candidate("target", "source", CandidateProviderType.FOLLOWERS)
    navigation = ProfileNavigation(CandidateProfile(candidate, "target", posts=5))
    device = Device(["<hierarchy />"])
    provider = PostFilterFlowProvider(
        navigation,
        [media_with_like_count(3), media_with_like_count(12)],
        device_factory=lambda _serial: device,
        post_filters=LikePostFilterSettings(10, 20),
        sleeper=lambda _seconds: None,
    )

    result = provider.execute(context(tmp_path), candidate)

    assert result.status is AndroidLikeStatus.SUCCESS
    assert result.likes_completed == 1
    assert provider.selections == 2
    assert len(device.clicks) == 3  # two thumbnails, one Like button


def test_three_hidden_counts_abandon_with_prior_verified_likes_preserved(tmp_path):
    candidate = Candidate("target", "source", CandidateProviderType.FOLLOWERS)
    navigation = ProfileNavigation(CandidateProfile(candidate, "target", posts=5))
    device = Device(["<hierarchy />"])
    provider = PostFilterFlowProvider(
        navigation,
        [
            media_with_like_count(12),
            media_with_like_count(),
            media_with_like_count(),
            media_with_like_count(),
        ],
        device_factory=lambda _serial: device,
        post_filters=LikePostFilterSettings(10, 20),
        likes_per_profile="2-2",
        sleeper=lambda _seconds: None,
    )

    result = provider.execute(context(tmp_path), candidate)

    assert result.status is AndroidLikeStatus.SUCCESS
    assert result.likes_completed == 1
    assert provider.selections == 4
    assert len(device.clicks) == 5  # four thumbnails, one Like button


def test_visible_like_count_resets_consecutive_hidden_counter(tmp_path):
    candidate = Candidate("target", "source", CandidateProviderType.FOLLOWERS)
    navigation = ProfileNavigation(CandidateProfile(candidate, "target", posts=8))
    device = Device(["<hierarchy />"])
    provider = PostFilterFlowProvider(
        navigation,
        [
            media_with_like_count(),
            media_with_like_count(3),
            media_with_like_count(),
            media_with_like_count(),
            media_with_like_count(12),
        ],
        device_factory=lambda _serial: device,
        post_filters=LikePostFilterSettings(10, 20),
        sleeper=lambda _seconds: None,
    )

    result = provider.execute(context(tmp_path), candidate)

    assert result.status is AndroidLikeStatus.SUCCESS
    assert result.likes_completed == 1
    assert provider.selections == 5


def test_liked_to_like_reversal_is_a_ghost_block():
    liked = hierarchy(node("row_feed_button_like", description="Liked"))
    reverted = hierarchy(node("row_feed_button_like", description="Like"))
    device = Device([liked, reverted])
    clock = Clock()
    provider = AndroidLikeProvider(
        ProfileNavigation(),
        sleeper=clock.sleep,
        clock=clock,
        poll_interval=0.25,
        stability_window=0.75,
    )

    assert provider._verify_liked(device) is AndroidLikeStatus.GHOST_BLOCK_DETECTED


class Candidates:
    def __init__(self, candidate):
        self.candidate = candidate
        self.evaluated = 0

    def next_candidate(self, _context):
        return CandidateResult(CandidateResultStatus.CANDIDATE_FOUND, self.candidate)

    def record_evaluated(self, _context):
        self.evaluated += 1


class SuccessfulLike:
    def execute(self, _context, _candidate, *, maximum_likes):
        return AndroidLikeResult(
            AndroidLikeStatus.SUCCESS, likes_completed=min(1, maximum_likes)
        )


def test_like_ignore_list_skips_before_android_and_persistence(tmp_path):
    runtime_context = context(tmp_path)
    runtime_context.ignore_service = IgnoreService(frozenset({"target"}))
    candidate = Candidate("target", "source", CandidateProviderType.FOLLOWERS)

    class IgnoredThenExhausted:
        def __init__(self):
            self.calls = 0

        def next_candidate(self, _context):
            self.calls += 1
            if self.calls == 1:
                return CandidateResult(CandidateResultStatus.CANDIDATE_FOUND, candidate)
            return CandidateResult(CandidateResultStatus.ALL_SOURCES_EXHAUSTED)

    class MustNotExecute:
        def execute(self, *_args, **_kwargs):
            raise AssertionError("Ignored candidate reached Android Like execution")

    module = LikeModule(
        runtime_context,
        LikeModuleSettings(True, True, 1, 10, 10),
        IgnoredThenExhausted(),
        MustNotExecute(),
    )

    result = module.execute(runtime_context, object())

    assert result.outcome is ModuleExecutionOutcome.NO_CANDIDATES
    with RuntimeDatabase(tmp_path) as database:
        assert database.users.get_by_username("target") is None


def test_like_module_persists_verified_success(tmp_path):
    runtime_context = context(tmp_path)
    candidate = Candidate("target", "source", CandidateProviderType.FOLLOWERS)
    candidates = Candidates(candidate)
    module = LikeModule(
        runtime_context,
        LikeModuleSettings(True, True, 1, 2, 3),
        candidates,
        SuccessfulLike(),
    )

    result = module.execute(runtime_context, object())

    assert result.outcome is ModuleExecutionOutcome.SUCCESS
    assert candidates.evaluated == 1
    with RuntimeDatabase(tmp_path) as database:
        user = database.users.get_by_username("target")
        assert user is not None
        interaction = database.like.get(user.id)
        assert interaction is not None
        assert interaction.likes_count == 1
        assert interaction.source == "source"
        assert interaction.username == "target"
        assert interaction.status == "SUCCESS"
        assert interaction.last_session_id == str(runtime_context.session.session_id)


class TwoVerifiedLikes:
    def execute(self, _context, _candidate, *, maximum_likes):
        return AndroidLikeResult(
            AndroidLikeStatus.SUCCESS, likes_completed=min(2, maximum_likes)
        )


class VerifiedLikeWithNavigationFailure:
    def execute(self, _context, _candidate, *, maximum_likes):
        return AndroidLikeResult(
            AndroidLikeStatus.SUCCESS,
            "Followers list did not return.",
            likes_completed=min(1, maximum_likes),
            navigation=NavigationResult(
                NavigationStatus.FAILED, "Followers list did not return."
            ),
        )


def test_like_module_persists_success_when_verified_like_navigation_fails(tmp_path):
    runtime_context = context(tmp_path)
    candidate = Candidate("target", "source", CandidateProviderType.FOLLOWERS)
    module = LikeModule(
        runtime_context,
        LikeModuleSettings(True, True, 1, 2, 3),
        Candidates(candidate),
        VerifiedLikeWithNavigationFailure(),
    )

    result = module.execute(runtime_context, object())

    assert result.outcome is ModuleExecutionOutcome.NAVIGATION_FAILED
    assert result.module_result.status is AndroidLikeStatus.SUCCESS
    assert result.module_result.navigation.status is NavigationStatus.FAILED
    assert result.module_result.likes_completed == 1
    with RuntimeDatabase(tmp_path) as database:
        user = database.users.get_by_username("target")
        interaction = database.like.get(user.id, "source")
        assert interaction.status == "SUCCESS"
        assert interaction.likes_count == 1
        assert interaction.last_like_date is not None
        assert interaction.last_session_id == str(runtime_context.session.session_id)


def test_like_module_persists_every_verified_like_from_profile(tmp_path):
    runtime_context = context(tmp_path)
    candidate = Candidate("target", "source", CandidateProviderType.FOLLOWERS)
    module = LikeModule(
        runtime_context,
        LikeModuleSettings(True, True, 1, 2, 3),
        Candidates(candidate),
        TwoVerifiedLikes(),
    )

    result = module.execute(runtime_context, object())

    assert result.outcome is ModuleExecutionOutcome.DAILY_LIMIT_REACHED
    assert result.verified_successes == 2
    with RuntimeDatabase(tmp_path) as database:
        user = database.users.get_by_username("target")
        interaction = database.like.get(user.id)
        assert interaction.likes_count == 2


class PrivateLikeOutcome:
    def __init__(self):
        self.calls = 0

    def execute(self, _context, _candidate, *, maximum_likes):
        self.calls += 1
        return AndroidLikeResult(AndroidLikeStatus.PRIVATE_SKIPPED)


def test_terminal_candidate_outcome_is_persisted_and_skipped_next_time(tmp_path):
    runtime_context = context(tmp_path)
    candidate = Candidate("private_user", "source", CandidateProviderType.FOLLOWERS)
    android = PrivateLikeOutcome()
    first = LikeModule(
        runtime_context,
        LikeModuleSettings(True, True, 1, 10, 10),
        Candidates(candidate),
        android,
    )

    first.execute(runtime_context, object())

    with RuntimeDatabase(tmp_path) as database:
        user = database.users.get_by_username("private_user")
        record = database.like.get(user.id, "source")
        assert record.status == "PRIVATE_SKIPPED"
        assert record.likes_count == 0
        assert record.last_session_id == str(runtime_context.session.session_id)

    class ExhaustAfterCandidate:
        def __init__(self):
            self.calls = 0

        def next_candidate(self, _context):
            self.calls += 1
            if self.calls == 1:
                return CandidateResult(CandidateResultStatus.CANDIDATE_FOUND, candidate)
            return CandidateResult(CandidateResultStatus.ALL_SOURCES_EXHAUSTED)

    second = LikeModule(
        runtime_context,
        LikeModuleSettings(True, True, 1, 10, 10),
        ExhaustAfterCandidate(),
        android,
    )
    result = second.execute(runtime_context, object())

    assert result.outcome is ModuleExecutionOutcome.NO_CANDIDATES
    assert android.calls == 1


def test_no_posts_is_persisted_and_candidate_loop_continues(tmp_path):
    runtime_context = context(tmp_path)
    first = Candidate("empty_profile", "source", CandidateProviderType.FOLLOWERS)

    class NoPostsThenExhausted:
        def __init__(self):
            self.calls = 0

        def next_candidate(self, _context):
            self.calls += 1
            if self.calls == 1:
                return CandidateResult(CandidateResultStatus.CANDIDATE_FOUND, first)
            return CandidateResult(CandidateResultStatus.ALL_SOURCES_EXHAUSTED)

    class NoPosts:
        def execute(self, _context, _candidate, *, maximum_likes):
            return AndroidLikeResult(AndroidLikeStatus.NO_POSTS)

    candidates = NoPostsThenExhausted()
    module = LikeModule(
        runtime_context,
        LikeModuleSettings(True, True, 1, 10, 10),
        candidates,
        NoPosts(),
    )

    result = module.execute(runtime_context, object())

    assert result.outcome is ModuleExecutionOutcome.NO_CANDIDATES
    assert candidates.calls == 2
    with RuntimeDatabase(tmp_path) as database:
        user = database.users.get_by_username("empty_profile")
        record = database.like.get(user.id, "source")
        assert record.status == "NO_POSTS"
        assert record.likes_count == 0


def test_profile_filter_rejection_is_persisted_and_candidate_loop_continues(
    tmp_path,
):
    runtime_context = context(tmp_path)
    rejected = Candidate("rejected", "source", CandidateProviderType.FOLLOWERS)

    class RejectedThenExhausted:
        def __init__(self):
            self.calls = 0

        def next_candidate(self, _context):
            self.calls += 1
            if self.calls == 1:
                return CandidateResult(CandidateResultStatus.CANDIDATE_FOUND, rejected)
            return CandidateResult(CandidateResultStatus.ALL_SOURCES_EXHAUSTED)

    class FilterRejected:
        def execute(self, _context, _candidate, *, maximum_likes):
            return AndroidLikeResult(AndroidLikeStatus.FILTER_REJECTED)

    candidates = RejectedThenExhausted()
    module = LikeModule(
        runtime_context,
        LikeModuleSettings(True, True, 1, 10, 10),
        candidates,
        FilterRejected(),
    )

    result = module.execute(runtime_context, object())

    assert result.outcome is ModuleExecutionOutcome.NO_CANDIDATES
    assert candidates.calls == 2
    with RuntimeDatabase(tmp_path) as database:
        user = database.users.get_by_username("rejected")
        record = database.like.get(user.id, "source")
        assert record.status == "FILTER_REJECTED"
        assert record.likes_count == 0


def test_source_followers_like_configuration_is_runtime_ready():
    configuration = {
        "likes-percentage": "100",
        "igbot-like-sources-followers": ["source"],
        "total-likes-limit": "10",
    }

    assert native_like_configuration_ready(configuration) is True
    assert native_account_configuration_ready(configuration) is True


def test_specific_like_synchronization_preserves_state_and_mirrors_txt(tmp_path):
    lists = tmp_path / "Lists"
    lists.mkdir()
    source = lists / "likespecific.txt"
    source.write_text("Alice\nbob\n", encoding="utf-8")
    synchronizer = SpecificLikeSynchronizer()

    synchronizer.synchronize(tmp_path)
    with RuntimeDatabase(tmp_path) as database:
        assert database.specific_like.pending_like_usernames() == ("Alice", "bob")
        database.specific_like.mark_specific_like_result(
            "Alice",
            status="SUCCESS",
            likes_count=2,
            processed_at="2026-09-26T10:00:00+00:00",
            last_session_id="session-1",
        )

    source.write_text("alice\ncharlie\n", encoding="utf-8")
    synchronizer.synchronize(tmp_path)

    with RuntimeDatabase(tmp_path) as database:
        rows = database._connection.execute(
            "SELECT username, liked, likes_count, status, last_session_id "
            "FROM specific_like ORDER BY user_id"
        ).fetchall()
        assert [tuple(row) for row in rows] == [
            ("alice", 1, 2, "SUCCESS", "session-1"),
            ("charlie", 0, 0, "PENDING", None),
        ]
        assert database.specific_like.pending_like_usernames() == ("charlie",)


def test_specific_like_synchronization_never_creates_ignored_interaction_rows(
    tmp_path,
):
    lists = tmp_path / "Lists"
    lists.mkdir()
    (lists / "likespecific.txt").write_text(
        "ignored_user\nallowed_user\n", encoding="utf-8"
    )

    SpecificLikeSynchronizer().synchronize(
        tmp_path, IgnoreService(frozenset({"ignored_user"}))
    )

    with RuntimeDatabase(tmp_path) as database:
        assert database.specific_like.pending_like_usernames() == ("allowed_user",)
        ignored = database._connection.execute(
            "SELECT 1 FROM specific_like WHERE username = 'ignored_user'"
        ).fetchone()
        assert ignored is None


def test_specific_like_uses_specific_table_without_discovery_history(tmp_path):
    runtime_context = context(tmp_path)
    lists = tmp_path / "Lists"
    lists.mkdir()
    (lists / "likespecific.txt").write_text("target\n", encoding="utf-8")
    SpecificLikeSynchronizer().synchronize(tmp_path)
    module = LikeModule(
        runtime_context,
        LikeModuleSettings(True, True, 1, 5, 5),
        SpecificLikeCandidates(tmp_path),
        SuccessfulLike(),
        persistence=SpecificLikePersistence(),
    )

    result = module.execute(runtime_context, object())

    assert result.outcome is ModuleExecutionOutcome.SUCCESS
    with RuntimeDatabase(tmp_path) as database:
        row = database._connection.execute(
            "SELECT liked, likes_count, status, like_date, last_session_id "
            "FROM specific_like WHERE username = 'target'"
        ).fetchone()
        assert tuple(row[:3]) == (1, 1, "SUCCESS")
        assert row[3] is not None
        assert row[4] == str(runtime_context.session.session_id)
        assert (
            database._connection.execute("SELECT COUNT(*) FROM like").fetchone()[0] == 0
        )


@pytest.mark.parametrize(
    "status",
    (
        AndroidLikeStatus.PROFILE_NOT_FOUND,
        AndroidLikeStatus.PROFILE_UNAVAILABLE,
        AndroidLikeStatus.NAVIGATION_FAILED,
    ),
)
def test_specific_like_persists_distinct_profile_and_navigation_failures(
    tmp_path, status
):
    runtime_context = context(tmp_path)
    lists = tmp_path / "Lists"
    lists.mkdir()
    (lists / "likespecific.txt").write_text("target\n", encoding="utf-8")
    SpecificLikeSynchronizer().synchronize(tmp_path)

    class TerminalOutcome:
        def execute(self, _context, _candidate, *, maximum_likes):
            return AndroidLikeResult(status)

    module = LikeModule(
        runtime_context,
        LikeModuleSettings(True, True, 1, 5, 5),
        SpecificLikeCandidates(tmp_path),
        TerminalOutcome(),
        persistence=SpecificLikePersistence(),
    )

    module.execute(runtime_context, object())

    with RuntimeDatabase(tmp_path) as database:
        row = database._connection.execute(
            "SELECT liked, status FROM specific_like WHERE username = 'target'"
        ).fetchone()
        assert tuple(row) == (0, status.value)


def test_specific_like_configuration_is_runtime_ready():
    configuration = {
        "likes-percentage": "100",
        "blogger": ["target"],
        "total-likes-limit": "10",
    }

    assert native_like_configuration_ready(configuration) is True
    assert native_account_configuration_ready(configuration) is True
