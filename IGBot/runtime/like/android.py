"""UIAutomator2 execution boundary for one verified photo Like."""

from __future__ import annotations

import random
import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from IGBot.runtime.candidates import Candidate, CandidateProviderType
from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.follow import (
    AndroidFollowProvider,
    AndroidFollowStatus,
    ConfiguredFollowCandidateQualifier,
    FollowFilterSettings,
    FollowModuleResultStatus,
)
from IGBot.runtime.ignore import log_ignored
from IGBot.runtime.like.models import (
    AndroidLikeResult,
    AndroidLikeStatus,
    LikeMediaType,
    LikePostFilterSettings,
)
from IGBot.runtime.navigation import NavigationResult, NavigationStatus


@dataclass(frozen=True, slots=True)
class _Node:
    resource_id: str
    description: str
    bounds: tuple[int, int, int, int]
    visible: bool = True

    @property
    def center(self) -> tuple[int, int]:
        left, top, right, bottom = self.bounds
        return ((left + right) // 2, (top + bottom) // 2)


class AndroidLikeProvider:
    """Open one profile-grid media item and verify a stable Liked state."""

    _BOUNDS = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")
    _GRID_ID = "image_button"
    _PROFILE_RECYCLER_IDS = frozenset({"swipeable_nav_view_pager_inner_recycler_view"})
    _PROFILE_TITLE_ID = "action_bar_title"
    _POST_HEADER_ID = "row_feed_profile_header"
    _LIKE_ID = "row_feed_button_like"
    _CAROUSEL_IDS = frozenset({"carousel_media_group", "carousel_viewpager"})
    _VIDEO_ID = "video_container"
    _CONTEXT_MENU_ID = "context_menu"
    _PEEK_CONTAINER_ID = "peek_container"
    _SUGGESTED_PROFILE_IDS = frozenset(
        {
            "similar_accounts_container",
            "similar_accounts_carousel_header",
            "similar_accounts_carousel_title",
        }
    )
    _TIME_VALUE = re.compile(r"(\d+(?:\.\d+)?)")
    _TIME_RANGE = re.compile(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)")
    _VISIBLE_LIKE_COUNT = re.compile(
        r"(?:^|,\s)(?P<count>\d[\d\s,.]*)\s+likes?\b", re.IGNORECASE
    )

    def __init__(
        self,
        profile_navigation: AndroidFollowProvider,
        *,
        device_factory: Callable[[str], object] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        choice: Callable[[Sequence[_Node]], _Node] = random.choice,
        natural_delay: Callable[[], float] = lambda: random.uniform(0.3, 0.8),
        likes_per_profile: object = 1,
        photo_view_time: object = 0,
        reel_view_time: object = 0,
        random_seconds: Callable[[float, float], float] = random.uniform,
        random_likes: Callable[[int, int], int] = random.randint,
        post_like_reel_delay: Callable[[], float] = lambda: random.uniform(1.0, 3.0),
        poll_interval: float = 0.2,
        load_timeout: float = 3.0,
        verification_timeout: float = 2.5,
        stability_window: float = 0.75,
        scroll_idle_timeout: float = 3.0,
        profile_filters: FollowFilterSettings | None = None,
        profile_qualifier: ConfiguredFollowCandidateQualifier | None = None,
        post_filters: LikePostFilterSettings | None = None,
    ) -> None:
        self._profiles = profile_navigation
        self._device_factory = device_factory or self._connect
        self._sleeper = sleeper
        self._clock = clock
        self._choice = choice
        self._natural_delay = natural_delay
        self._likes_per_profile_setting = likes_per_profile
        self._photo_view_time = photo_view_time
        self._reel_view_time = reel_view_time
        self._random_seconds = random_seconds
        self._random_likes = random_likes
        self._post_like_reel_delay = post_like_reel_delay
        self._poll_interval = poll_interval
        self._load_timeout = load_timeout
        self._verification_timeout = verification_timeout
        self._stability_window = stability_window
        self._scroll_idle_timeout = scroll_idle_timeout
        self._profile_filters = profile_filters or FollowFilterSettings(
            allow_private=True
        )
        self._profile_qualifier = (
            profile_qualifier or ConfiguredFollowCandidateQualifier()
        )
        self._post_filters = post_filters or LikePostFilterSettings()

    def execute(
        self,
        context: RuntimeContext,
        candidate: Candidate,
        *,
        maximum_likes: int | None = None,
    ) -> AndroidLikeResult:
        if context.cancellation_checkpoint("Like profile navigation"):
            return AndroidLikeResult(
                AndroidLikeStatus.PROFILE_UNAVAILABLE, "Like execution cancelled."
            )
        context.logger.info("[Like] Opening profile...", username=candidate.username)
        opened = self._profiles.open_candidate_profile(context, candidate)
        if context.cancellation_checkpoint("Like profile opened"):
            return AndroidLikeResult(
                AndroidLikeStatus.PROFILE_UNAVAILABLE, "Like execution cancelled."
            )
        if not opened.succeeded:
            status = AndroidLikeStatus.PROFILE_UNAVAILABLE
            if opened.status is AndroidFollowStatus.SOURCE_NOT_FOUND:
                status = AndroidLikeStatus.PROFILE_NOT_FOUND
            elif opened.navigation_failed:
                status = AndroidLikeStatus.NAVIGATION_FAILED
            return AndroidLikeResult(status, opened.detail)
        observed_username = (
            opened.profile.username if opened.profile is not None else ""
        )
        if observed_username and context.ignore_service.is_ignored(observed_username):
            log_ignored(context, observed_username)
            restored = self._profiles.return_to_followers(context)
            return AndroidLikeResult(
                (
                    AndroidLikeStatus.IGNORED
                    if restored.succeeded
                    else AndroidLikeStatus.NAVIGATION_FAILED
                ),
                None if restored.succeeded else restored.detail,
            )
        if (
            candidate.provider_type is CandidateProviderType.SPECIFIC_ACCOUNTS
            and observed_username.casefold() != candidate.username.casefold()
        ):
            context.logger.error(
                "[Like] Opened profile username mismatch. Aborting interaction.",
                expected=candidate.username,
                observed=observed_username,
            )
            restored = self._profiles.return_to_followers(context)
            return AndroidLikeResult(
                (
                    AndroidLikeStatus.PROFILE_UNAVAILABLE
                    if restored.succeeded
                    else AndroidLikeStatus.NAVIGATION_FAILED
                ),
                "Opened profile username did not match the requested username.",
            )
        if opened.profile is not None:
            qualification = self._profile_qualifier.qualify(
                context, opened.profile, self._profile_filters
            )
            if qualification.status is not FollowModuleResultStatus.READY_TO_FOLLOW:
                context.logger.info(
                    "[Like] Profile filter rejected candidate.",
                    reason=qualification.detail or qualification.status.value,
                )
                restored = self._profiles.return_to_followers(context)
                return AndroidLikeResult(
                    (
                        AndroidLikeStatus.FILTER_REJECTED
                        if restored.succeeded
                        else AndroidLikeStatus.NAVIGATION_FAILED
                    ),
                    qualification.detail if restored.succeeded else restored.detail,
                )
        if opened.profile is not None and opened.profile.is_private:
            context.logger.info("[Like] Private profile detected. Skipping.")
            restored = self._profiles.return_to_followers(context)
            return AndroidLikeResult(
                (
                    AndroidLikeStatus.PRIVATE_SKIPPED
                    if restored.succeeded
                    else AndroidLikeStatus.NAVIGATION_FAILED
                ),
                None if restored.succeeded else restored.detail,
            )
        if opened.profile is not None and opened.profile.posts == 0:
            context.logger.info("[Like] Profile contains no posts. Skipping.")
            restored = self._profiles.return_to_followers(context)
            return AndroidLikeResult(
                (
                    AndroidLikeStatus.NO_POSTS
                    if restored.succeeded
                    else AndroidLikeStatus.NAVIGATION_FAILED
                ),
                None if restored.succeeded else restored.detail,
            )

        device = self._device_factory(context.session.phone_id)
        completed = 0
        try:
            target = self._likes_per_profile()
            if maximum_likes is not None:
                target = min(target, maximum_likes)
            attempted: set[tuple[str, object]] = set()
            hidden_like_posts_checked = 0
            first_pass = True
            while completed < target:
                if context.cancellation_checkpoint("Like profile preparation"):
                    return AndroidLikeResult(
                        (
                            AndroidLikeStatus.SUCCESS
                            if completed
                            else AndroidLikeStatus.PROFILE_UNAVAILABLE
                        ),
                        "Like execution cancelled.",
                        likes_completed=completed,
                    )
                context.logger.info("[Like] Scrolling profile...")
                hierarchy = self._settle_scroll_and_read_profile(
                    device, initial=first_pass
                )
                first_pass = False
                if hierarchy is None:
                    context.logger.warning(
                        "[Like] Profile grid stability could not be verified."
                    )
                    restored = self._profiles.return_to_followers(context)
                    if not restored.succeeded:
                        return self._navigation_failure(
                            context,
                            "Profile preparation did not reach a verified stable state.",
                            completed,
                        )
                    return AndroidLikeResult(
                        (
                            AndroidLikeStatus.SUCCESS
                            if completed
                            else AndroidLikeStatus.PROFILE_UNAVAILABLE
                        ),
                        "Profile preparation did not reach a verified stable state.",
                        likes_completed=completed,
                        navigation=NavigationResult(NavigationStatus.SUCCESS),
                    )
                selection_state, selected = self._select_revalidated_thumbnail(
                    device, hierarchy, attempted
                )
                if selection_state == "overlay":
                    context.logger.warning(
                        "[Like] Thumbnail overlay detected before tap. Recovering profile."
                    )
                    if not self._dismiss_unexpected_overlay(
                        device, candidate.username, None
                    ):
                        self._profiles.return_to_followers(context)
                        return self._navigation_failure(
                            context,
                            "Profile could not be restored from the thumbnail overlay.",
                            completed,
                        )
                    continue
                if selected is None:
                    context.logger.info("[Like] No more clickable visible posts.")
                    context.logger.info("[Like] Returning to source followers...")
                    restored = self._profiles.return_to_followers(context)
                    if not restored.succeeded:
                        return self._navigation_failure(
                            context,
                            restored.detail or "Followers list did not return.",
                            completed,
                        )
                    status = (
                        AndroidLikeStatus.SUCCESS
                        if completed
                        else AndroidLikeStatus.NO_SUPPORTED_POST
                    )
                    return AndroidLikeResult(
                        status,
                        (
                            "No untried fully visible media was available."
                            if restored.succeeded
                            else restored.detail
                        ),
                        likes_completed=completed,
                        navigation=NavigationResult(NavigationStatus.SUCCESS),
                    )
                context.logger.info("[Like] Selecting visible post...")
                if context.cancellation_checkpoint("Like media opening"):
                    return AndroidLikeResult(
                        (
                            AndroidLikeStatus.SUCCESS
                            if completed
                            else AndroidLikeStatus.PROFILE_UNAVAILABLE
                        ),
                        "Like execution cancelled.",
                        likes_completed=completed,
                    )
                # UIAutomator2 Device.click delegates to UiDevice.click, an
                # immediate down/up tap with no provider-controlled hold time.
                device.click(*selected.center)
                context.logger.info("[Like] Opening media...")
                destination, loaded = self._wait_for_post(device)
                if destination == "overlay":
                    context.logger.warning(
                        "[Like] Thumbnail overlay detected. Recovering profile."
                    )
                    if not self._dismiss_unexpected_overlay(
                        device, candidate.username, loaded
                    ):
                        self._profiles.return_to_followers(context)
                        return self._navigation_failure(
                            context,
                            "Profile could not be restored from the context menu.",
                            completed,
                        )
                    continue
                if destination != "media" or loaded is None:
                    context.logger.info("[Like] Selected post failed to open.")
                    context.logger.info("[Like] Trying another visible post...")
                    if not self._restore_profile_after_failed_post(
                        device, candidate.username
                    ):
                        self._profiles.return_to_followers(context)
                        return self._navigation_failure(
                            context,
                            "Profile could not be restored after a failed post.",
                            completed,
                        )
                    continue
                media_type = self._detect_media(loaded)
                if media_type is None:
                    device.press("back")
                    if not self._wait_for_profile(device, candidate.username):
                        return self._navigation_failure(
                            context,
                            "Profile did not return after an unsupported post.",
                            completed,
                        )
                    continue
                prepared = self._prepare_media_controls(device, loaded, media_type)
                if prepared is None:
                    restored = self._return_to_followers(
                        context, device, candidate.username
                    )
                    if not restored:
                        return self._navigation_failure(
                            context,
                            "Followers list did not return after media layout recovery.",
                            completed,
                        )
                    return AndroidLikeResult(
                        (
                            AndroidLikeStatus.SUCCESS
                            if completed
                            else AndroidLikeStatus.LIKE_FAILED
                        ),
                        "Like controls were not visible after media layout recovery.",
                        likes_completed=completed,
                        navigation=NavigationResult(NavigationStatus.SUCCESS),
                    )
                loaded = prepared
                context.logger.info(f"[Like] Detected: {media_type.value}")
                if self._post_filters.enabled:
                    like_count = self._visible_like_count(loaded)
                    if like_count is None:
                        hidden_like_posts_checked += 1
                        context.logger.info("[Like] Like count hidden.")
                        context.logger.info(
                            "[Like] Hidden Like counter:",
                            progress=f"{hidden_like_posts_checked}/3",
                        )
                        if hidden_like_posts_checked >= 3:
                            context.logger.info(
                                "[Like] Abandoning candidate because Like count "
                                "remained hidden for three inspected posts."
                            )
                            restored = self._return_to_followers(
                                context, device, candidate.username
                            )
                            if not restored:
                                return self._navigation_failure(
                                    context,
                                    "Followers list did not return after hidden Like counts.",
                                    completed,
                                )
                            return AndroidLikeResult(
                                (
                                    AndroidLikeStatus.SUCCESS
                                    if completed
                                    else AndroidLikeStatus.FILTER_REJECTED
                                ),
                                likes_completed=completed,
                                navigation=NavigationResult(NavigationStatus.SUCCESS),
                            )
                        if not self._return_to_profile(device, candidate.username):
                            return self._navigation_failure(
                                context,
                                "Profile did not return after a hidden Like count.",
                                completed,
                            )
                        continue
                    hidden_like_posts_checked = 0
                    context.logger.info(
                        "[Like] Visible Like count detected.", count=like_count
                    )
                    if not self._like_count_allowed(like_count):
                        context.logger.info(
                            "[Like] Like count outside configured range.",
                            count=like_count,
                        )
                        if not self._return_to_profile(device, candidate.username):
                            return self._navigation_failure(
                                context,
                                "Profile did not return after Like-count rejection.",
                                completed,
                            )
                        continue
                context.logger.info("[Like] Watching media...")
                if not self._interruptible_wait(
                    context, self._view_time(media_type), "Like media viewing"
                ):
                    return AndroidLikeResult(
                        (
                            AndroidLikeStatus.SUCCESS
                            if completed
                            else AndroidLikeStatus.PROFILE_UNAVAILABLE
                        ),
                        "Like execution cancelled.",
                        likes_completed=completed,
                    )

                like = self._find(loaded, self._LIKE_ID)
                if like is None:
                    restored = self._return_to_followers(
                        context, device, candidate.username
                    )
                    if not restored:
                        return self._navigation_failure(
                            context,
                            "Followers list did not return after the Like button was unavailable.",
                            completed,
                        )
                    return AndroidLikeResult(
                        (
                            AndroidLikeStatus.SUCCESS
                            if completed
                            else AndroidLikeStatus.LIKE_FAILED
                        ),
                        "Like button was unavailable.",
                        likes_completed=completed,
                        navigation=NavigationResult(NavigationStatus.SUCCESS),
                    )
                if like.description.casefold() == "liked":
                    if not self._return_to_profile(device, candidate.username):
                        return self._navigation_failure(
                            context,
                            "Profile did not return after an already-liked post.",
                            completed,
                        )
                    continue
                context.logger.info("[Like] Liking post...")
                if context.cancellation_checkpoint("Like execution"):
                    return AndroidLikeResult(
                        (
                            AndroidLikeStatus.SUCCESS
                            if completed
                            else AndroidLikeStatus.PROFILE_UNAVAILABLE
                        ),
                        "Like execution cancelled.",
                        likes_completed=completed,
                    )
                device.click(*like.center)
                context.logger.info("[Like] Waiting for verification...")
                verification = self._verify_liked(device)
                if verification is not AndroidLikeStatus.SUCCESS:
                    restored = self._return_to_followers(
                        context, device, candidate.username
                    )
                    if not restored:
                        return self._navigation_failure(
                            context,
                            "Followers list did not return after Like verification failed.",
                            completed,
                        )
                    return AndroidLikeResult(
                        AndroidLikeStatus.SUCCESS if completed else verification,
                        "Like did not remain in the Liked state.",
                        likes_completed=completed,
                        navigation=NavigationResult(NavigationStatus.SUCCESS),
                    )
                context.logger.info("[Like] Like confirmed.")
                completed += 1
                if media_type is LikeMediaType.REEL and not self._interruptible_wait(
                    context,
                    max(0.0, self._post_like_reel_delay()),
                    "Like post-verification viewing",
                ):
                    return AndroidLikeResult(
                        AndroidLikeStatus.SUCCESS,
                        "Like execution cancelled.",
                        likes_completed=completed,
                    )
                if not self._return_to_profile(device, candidate.username):
                    return self._navigation_failure(
                        context,
                        "Profile did not return after the Like.",
                        completed,
                    )
            if not self._profiles.return_to_followers(context).succeeded:
                return self._navigation_failure(
                    context,
                    "Followers list did not return after the Like session.",
                    completed,
                )
            return AndroidLikeResult(
                AndroidLikeStatus.SUCCESS,
                likes_completed=completed,
                navigation=NavigationResult(NavigationStatus.SUCCESS),
            )
        except Exception as error:  # noqa: BLE001 - Android isolation boundary
            return AndroidLikeResult(
                (
                    AndroidLikeStatus.SUCCESS
                    if completed
                    else AndroidLikeStatus.LIKE_FAILED
                ),
                str(error),
                likes_completed=completed,
            )

    def _interruptible_wait(
        self, context: RuntimeContext, seconds: float, checkpoint: str
    ) -> bool:
        seconds = max(0.0, seconds)
        if context.cancellation_checkpoint(checkpoint):
            return False
        if context.cancellation_wait is not None:
            context.cancellation_wait(seconds)
        elif seconds:
            self._sleeper(seconds)
        return not context.cancellation_checkpoint(checkpoint)

    @staticmethod
    def _navigation_failure(
        context: RuntimeContext, detail: str, completed: int
    ) -> AndroidLikeResult:
        interaction_status = (
            AndroidLikeStatus.SUCCESS
            if completed
            else AndroidLikeStatus.NAVIGATION_FAILED
        )
        context.logger.info(
            "[Like] Interaction result.",
            status=interaction_status.value,
            likes_completed=completed,
        )
        context.logger.warning(
            "[Like] Navigation result.",
            status=NavigationStatus.FAILED.value,
            expected="Followers list",
            actual="Candidate profile / Unknown",
            reason=detail,
        )
        context.logger.info(
            "[Like] Returning result with interaction and navigation states preserved."
        )
        return AndroidLikeResult(
            interaction_status,
            detail,
            likes_completed=completed,
            navigation=NavigationResult(
                NavigationStatus.FAILED,
                detail,
                expected="Followers list",
                actual="Candidate profile / Unknown",
            ),
        )

    def _scroll_profile(self, device: object) -> None:
        width, height = self._window_size(device)
        x = width // 2
        device.swipe(x, int(height * 0.74), x, int(height * 0.45), duration=0.4)

    def _scroll_between_likes(self, device: object) -> None:
        width, height = self._window_size(device)
        x = width // 2
        device.swipe(x, int(height * 0.67), x, int(height * 0.57), duration=0.3)

    def _settle_scroll_and_read_profile(
        self, device: object, *, initial: bool
    ) -> str | None:
        """Sequence profile settling, scrolling, and the selection snapshot."""

        self._sleeper(max(0.0, self._natural_delay()))
        if initial:
            self._scroll_profile(device)
        else:
            self._scroll_between_likes(device)
        self._wait_for_scroll_complete(device)
        # The UI-idle gate verifies that scrolling has stopped. This short,
        # randomized interval lets Instagram finish post-scroll rendering
        # before the hierarchy used for thumbnail selection is captured.
        self._sleeper(max(0.0, self._natural_delay()))
        hierarchy = device.dump_hierarchy(compressed=False)
        if (
            initial
            and not self._fully_visible_grid_posts(hierarchy)
            and self._has_suggested_profile_section(self._nodes(hierarchy))
        ):
            # Instagram can place a full-height similar-accounts carousel
            # between the profile header and grid. One bounded extra scroll is
            # enough to move past it; a persistent missing grid remains the
            # existing profile-preparation failure.
            self._scroll_profile(device)
            self._wait_for_scroll_complete(device)
            self._sleeper(max(0.0, self._natural_delay()))
            return self._wait_for_stable_profile_grid(device)
        return self._wait_for_stable_profile_grid(device, initial_hierarchy=hierarchy)

    def _wait_for_scroll_complete(self, device: object) -> None:
        """Block until Android reports no pending accessibility UI events."""

        timeout_ms = max(0, int(self._scroll_idle_timeout * 1000))
        device.jsonrpc.waitForIdle(timeout_ms)

    def _wait_for_stable_profile_grid(
        self, device: object, *, initial_hierarchy: str | None = None
    ) -> str | None:
        """Return only after consecutive snapshots show a stationary grid."""

        deadline = self._clock() + self._load_timeout
        previous_fingerprint: (
            tuple[tuple[tuple[str, object], tuple[int, int, int, int]], ...] | None
        ) = None
        latest = (
            initial_hierarchy
            if initial_hierarchy is not None
            else device.dump_hierarchy(compressed=False)
        )
        while True:
            nodes = self._nodes(latest)
            fingerprint = (
                ()
                if self._has_unexpected_overlay(nodes)
                else tuple(
                    (self._post_identity(node), node.bounds)
                    for node in self._fully_visible_grid_posts(latest)
                )
            )
            if fingerprint and fingerprint == previous_fingerprint:
                return latest
            previous_fingerprint = fingerprint or None
            if self._clock() >= deadline:
                return None
            self._sleeper(self._poll_interval)
            latest = device.dump_hierarchy(compressed=False)

    def _has_suggested_profile_section(self, nodes: Sequence[_Node]) -> bool:
        """Detect the profile carousel without relying on localized labels."""

        return any(
            self._suffix(node.resource_id) in self._SUGGESTED_PROFILE_IDS
            for node in nodes
        )

    @staticmethod
    def _post_identity(node: _Node) -> tuple[str, object]:
        description = node.description.strip().casefold()
        return ("description", description) if description else ("bounds", node.bounds)

    def _select_revalidated_thumbnail(
        self,
        device: object,
        hierarchy: str,
        attempted: set[tuple[str, object]],
    ) -> tuple[str, _Node | None]:
        """Choose only a fresh thumbnail whose identity and bounds still match."""

        current = hierarchy
        while True:
            posts = tuple(
                node
                for node in self._fully_visible_grid_posts(current)
                if self._post_identity(node) not in attempted
            )
            if not posts:
                return ("exhausted", None)
            selected = self._choice(posts)
            identity = self._post_identity(selected)
            if identity in attempted:
                current = device.dump_hierarchy(compressed=False)
                continue
            attempted.add(identity)
            fresh = device.dump_hierarchy(compressed=False)
            fresh_nodes = self._nodes(fresh)
            if self._has_unexpected_overlay(fresh_nodes):
                return ("overlay", None)
            matching = next(
                (
                    node
                    for node in self._fully_visible_grid_posts(fresh)
                    if self._post_identity(node) == identity
                    and node.bounds == selected.bounds
                ),
                None,
            )
            if matching is not None:
                return ("selected", matching)
            current = fresh

    def _restore_profile_after_failed_post(self, device: object, username: str) -> bool:
        hierarchy = device.dump_hierarchy(compressed=False)
        if self._profile_surface_ready(hierarchy, username):
            stable = self._wait_for_stable_profile_grid(device)
            return stable is not None and self._profile_surface_ready(stable, username)
        device.press("back")
        return self._wait_for_profile_grid(device, username)

    def _fully_visible_grid_posts(self, hierarchy: str) -> tuple[_Node, ...]:
        nodes = self._nodes(hierarchy)
        posts = []
        for node in nodes:
            if self._suffix(node.resource_id) != self._GRID_ID:
                continue
            left, top, right, bottom = node.bounds
            width = right - left
            height = bottom - top
            if width <= 0 or height < width * 0.75:
                continue
            posts.append(node)
        return tuple(posts)

    def _wait_for_post(self, device: object) -> tuple[str, str | None]:
        deadline = self._clock() + self._load_timeout
        while True:
            hierarchy = device.dump_hierarchy(compressed=False)
            nodes = self._nodes(hierarchy)
            if self._has_unexpected_overlay(nodes):
                return ("overlay", hierarchy)
            if (
                self._find(nodes, self._POST_HEADER_ID)
                and self._detect_media(hierarchy) is not None
            ):
                return ("media", hierarchy)
            if self._clock() >= deadline:
                return ("timeout", None)
            self._sleeper(self._poll_interval)

    def _prepare_media_controls(
        self, device: object, hierarchy: str, media_type: LikeMediaType
    ) -> str | None:
        """Expose hidden media actions once, then verify a stable media layout."""

        if self._like_controls_visible(device, hierarchy):
            return hierarchy
        nodes = self._nodes(hierarchy)
        container = self._media_container(nodes, media_type)
        if container is None:
            return None
        left, top, right, bottom = container.bounds
        visible_height = bottom - top
        if visible_height <= 0:
            return None
        distance = max(1, round(visible_height * 0.175))
        x = (left + right) // 2
        start_y = bottom - 1
        end_y = max(top + 1, start_y - distance)
        device.swipe(x, start_y, x, end_y, duration=0.3)
        self._wait_for_scroll_complete(device)
        return self._wait_for_stable_media_controls(device, media_type)

    def _wait_for_stable_media_controls(
        self, device: object, media_type: LikeMediaType
    ) -> str | None:
        deadline = self._clock() + self._load_timeout
        previous: tuple[tuple[int, int, int, int], ...] | None = None
        while True:
            hierarchy = device.dump_hierarchy(compressed=False)
            detected = self._detect_media(hierarchy)
            like = self._find(hierarchy, self._LIKE_ID)
            current = (like.bounds,) if like is not None else None
            if (
                detected is media_type
                and self._like_controls_visible(device, hierarchy)
                and current == previous
            ):
                return hierarchy
            previous = current
            if self._clock() >= deadline:
                return None
            self._sleeper(self._poll_interval)

    def _like_controls_visible(self, device: object, hierarchy: str) -> bool:
        like = self._find(hierarchy, self._LIKE_ID)
        if like is None or not like.visible:
            return False
        width, height = self._window_size(device)
        left, top, right, bottom = like.bounds
        return left >= 0 and top >= 0 and right <= width and bottom <= height

    def _media_container(
        self, nodes: tuple[_Node, ...], media_type: LikeMediaType
    ) -> _Node | None:
        identifiers = (
            self._CAROUSEL_IDS
            if media_type is LikeMediaType.CAROUSEL
            else frozenset({self._VIDEO_ID})
        )
        return next(
            (
                node
                for node in nodes
                if self._suffix(node.resource_id) in identifiers and node.visible
            ),
            None,
        )

    def _dismiss_unexpected_overlay(
        self, device: object, username: str, hierarchy: str | None
    ) -> bool:
        """Dismiss Peek Preview/context menu and verify a stable profile grid."""

        nodes = self._nodes(hierarchy or device.dump_hierarchy(compressed=False))
        menu = self._find(nodes, self._CONTEXT_MENU_ID)
        peek = self._find(nodes, self._PEEK_CONTAINER_ID)
        overlay = menu or peek
        if overlay is None:
            return self._wait_for_profile_grid(device, username)
        left, top, right, bottom = overlay.bounds
        width, height = self._window_size(device)
        x = (left + right) // 2
        start_y = min(bottom - 1, top + max(1, (bottom - top) // 3))
        device.swipe(x, start_y, x, height - 1, duration=0.3)
        if self._wait_for_profile_grid(device, username):
            return True
        device.click(max(1, width - 24), max(1, height - 24))
        return self._wait_for_profile_grid(device, username)

    def _wait_for_profile_grid(self, device: object, username: str) -> bool:
        deadline = self._clock() + self._load_timeout
        while True:
            hierarchy = device.dump_hierarchy(compressed=False)
            if self._profile_surface_ready(hierarchy, username):
                stable = self._wait_for_stable_profile_grid(device)
                return stable is not None and self._profile_surface_ready(
                    stable, username
                )
            if self._clock() >= deadline:
                return False
            self._sleeper(self._poll_interval)

    def _profile_surface_ready(self, hierarchy: str, username: str) -> bool:
        nodes = self._nodes(hierarchy)
        if self._has_unexpected_overlay(nodes):
            return False
        title = self._find(nodes, self._PROFILE_TITLE_ID)
        recycler = next(
            (
                node
                for node in nodes
                if self._suffix(node.resource_id) in self._PROFILE_RECYCLER_IDS
            ),
            None,
        )
        return bool(
            title is not None
            and title.description.casefold() == username.casefold()
            and recycler is not None
            and self._fully_visible_grid_posts(hierarchy)
        )

    def _has_unexpected_overlay(self, nodes: tuple[_Node, ...]) -> bool:
        return bool(
            self._find(nodes, self._CONTEXT_MENU_ID)
            or self._find(nodes, self._PEEK_CONTAINER_ID)
        )

    def _detect_media(self, hierarchy: str) -> LikeMediaType | None:
        """Classify opened media using inspected production resource IDs."""

        nodes = self._nodes(hierarchy)
        identifiers = {self._suffix(node.resource_id) for node in nodes}
        if identifiers & self._CAROUSEL_IDS:
            return LikeMediaType.CAROUSEL
        if self._VIDEO_ID in identifiers:
            return LikeMediaType.REEL
        if self._find(nodes, self._POST_HEADER_ID) and self._find(nodes, self._LIKE_ID):
            return LikeMediaType.PHOTO
        return None

    def _view_time(self, media_type: LikeMediaType) -> float:
        configured = (
            self._reel_view_time
            if media_type is LikeMediaType.REEL
            else self._photo_view_time
        )
        text = str(configured or "0").strip()
        fixed = self._TIME_VALUE.fullmatch(text)
        if fixed is not None:
            return float(fixed.group(1))
        ranged = self._TIME_RANGE.fullmatch(text)
        if ranged is None:
            return 0.0
        minimum, maximum = (float(value) for value in ranged.groups())
        if minimum > maximum:
            return 0.0
        return max(0.0, self._random_seconds(minimum, maximum))

    def _visible_like_count(self, hierarchy: str) -> int | None:
        """Return only Instagram's explicit numeric media Like count."""

        root = ET.fromstring(hierarchy)
        for parent in root.iter():
            children = list(parent)
            for index, child in enumerate(children[:-1]):
                contains_like_button = any(
                    self._suffix(descendant.get("resource-id", "")) == self._LIKE_ID
                    for descendant in child.iter("node")
                )
                if not contains_like_button:
                    continue
                count_node = children[index + 1]
                count_text = count_node.get("text", "").strip()
                if count_node.get("class") == "android.widget.Button" and re.fullmatch(
                    r"\d[\d\s,.]*", count_text
                ):
                    return int(re.sub(r"[^0-9]", "", count_text))

        # The media accessibility description is the production fallback for
        # layouts where the action row has no dedicated numeric sibling. A
        # "Liked by ... and others" description intentionally does not match.
        for node in self._nodes(hierarchy):
            match = self._VISIBLE_LIKE_COUNT.search(node.description)
            if match is None:
                continue
            digits = re.sub(r"[^0-9]", "", match.group("count"))
            if digits:
                return int(digits)
        return None

    def _like_count_allowed(self, like_count: int) -> bool:
        minimum = self._post_filters.minimum_likes
        maximum = self._post_filters.maximum_likes
        return not (
            (minimum is not None and like_count < minimum)
            or (maximum is not None and like_count > maximum)
        )

    def _likes_per_profile(self) -> int:
        text = str(self._likes_per_profile_setting or "1").strip()
        fixed = self._TIME_VALUE.fullmatch(text)
        if fixed is not None:
            return max(1, int(float(fixed.group(1))))
        ranged = self._TIME_RANGE.fullmatch(text)
        if ranged is None:
            return 1
        minimum, maximum = (int(float(value)) for value in ranged.groups())
        if minimum <= 0 or minimum > maximum:
            return 1
        return self._random_likes(minimum, maximum)

    def _verify_liked(self, device: object) -> AndroidLikeStatus:
        deadline = self._clock() + self._verification_timeout
        stable_since: float | None = None
        while True:
            now = self._clock()
            button = self._find(
                self._nodes(device.dump_hierarchy(compressed=False)), self._LIKE_ID
            )
            state = button.description.casefold() if button is not None else ""
            if state == "liked":
                stable_since = stable_since or now
                if now - stable_since >= self._stability_window:
                    return AndroidLikeStatus.SUCCESS
            else:
                if stable_since is not None:
                    return AndroidLikeStatus.GHOST_BLOCK_DETECTED
            if now >= deadline:
                return AndroidLikeStatus.LIKE_FAILED
            self._sleeper(self._poll_interval)

    def _return_to_followers(
        self, context: RuntimeContext, device: object, username: str
    ) -> bool:
        if not self._return_to_profile(device, username):
            return False
        return self._profiles.return_to_followers(context).succeeded

    def _return_to_profile(self, device: object, username: str) -> bool:
        device.press("back")
        return self._wait_for_profile_grid(device, username)

    def _wait_for_profile(self, device: object, username: str) -> bool:
        deadline = self._clock() + self._load_timeout
        while True:
            hierarchy = device.dump_hierarchy(compressed=False)
            if self._profile_surface_ready(hierarchy, username):
                return True
            if self._clock() >= deadline:
                return False
            self._sleeper(self._poll_interval)

    @classmethod
    def _nodes(cls, hierarchy: str) -> tuple[_Node, ...]:
        result = []
        for element in ET.fromstring(hierarchy).iter("node"):
            bounds = cls._BOUNDS.fullmatch(element.get("bounds", ""))
            if bounds is None:
                continue
            result.append(
                _Node(
                    element.get("resource-id", ""),
                    element.get("content-desc", ""),
                    tuple(int(value) for value in bounds.groups()),
                    element.get("visible-to-user", "true").casefold() == "true",
                )
            )
        return tuple(result)

    @classmethod
    def _find(cls, hierarchy_or_nodes, identifier: str) -> _Node | None:
        nodes = (
            cls._nodes(hierarchy_or_nodes)
            if isinstance(hierarchy_or_nodes, str)
            else hierarchy_or_nodes
        )
        return next(
            (node for node in nodes if cls._suffix(node.resource_id) == identifier),
            None,
        )

    @staticmethod
    def _suffix(resource_id: str) -> str:
        return resource_id.rsplit("/", 1)[-1].casefold()

    @staticmethod
    def _window_size(device: object) -> tuple[int, int]:
        size = device.window_size()
        if isinstance(size, tuple):
            return (int(size[0]), int(size[1]))
        return (int(size["width"]), int(size["height"]))

    @staticmethod
    def _connect(serial: str) -> object:
        import uiautomator2 as u2

        return u2.connect(serial)
