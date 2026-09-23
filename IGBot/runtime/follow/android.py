"""UIAutomator2 execution provider for Follow navigation and interaction."""

from __future__ import annotations

import random
import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from math import ceil

from IGBot.runtime.candidates import (
    Candidate,
    CandidateObservation,
    CandidateProviderType,
)
from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.follow.android_models import (
    AndroidFollowResult,
    AndroidFollowStatus,
)
from IGBot.runtime.follow.contracts import ContactScraper
from IGBot.runtime.follow.models import CandidateProfile
from IGBot.runtime.profile_ready import wait_for_profile_ready


@dataclass(frozen=True, slots=True)
class _Node:
    text: str
    description: str
    resource_id: str
    bounds: tuple[int, int, int, int]
    scrollable: bool = False
    class_name: str = ""
    checkable: bool = False
    checked: bool = False

    @property
    def center(self) -> tuple[int, int]:
        left, top, right, bottom = self.bounds
        return ((left + right) // 2, (top + bottom) // 2)


class _SearchState(StrEnum):
    RESULTS = "results"
    SEARCH_RESULTS = "search_results"
    ACCOUNTS_RESULTS = "accounts_results"
    PROFILE = "profile"


@dataclass(frozen=True, slots=True)
class _MuteSwitch:
    """One dynamically discovered switch on Instagram's Mute sheet."""

    identity: tuple[str, ...]
    bounds: tuple[int, int, int, int]
    checked: bool

    @property
    def center(self) -> tuple[int, int]:
        left, top, right, bottom = self.bounds
        return ((left + right) // 2, (top + bottom) // 2)


class AndroidFollowProvider:
    """Perform Follow-related Android UI actions without runtime decisions."""

    _BOUNDS_PATTERN = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")
    _SEARCH_TAB_IDS = ("search_tab", "search_button", "tab_search")
    _SEARCH_INPUT_IDS = (
        "action_bar_search_edit_text",
        "search_edit_text",
        "search_field",
    )
    _USERNAME_IDS = (
        "row_search_user_username",
        "row_user_primary_name",
        "search_result_username",
        "follow_list_username",
    )
    _ACCOUNTS_TAB_IDS = ("accounts_tab", "search_accounts_tab", "tab_accounts")
    _FOLLOWERS_IDS = (
        "row_profile_header_followers_container",
        "row_profile_header_container_followers",
        "profile_header_followers_stacked_familiar",
    )
    _FOLLOWING_IDS = (
        "row_profile_header_following_container",
        "row_profile_header_container_following",
        "profile_header_following_stacked_familiar",
    )
    _FOLLOWER_SEARCH_IDS = ("row_search_edit_text", "follow_list_search")
    _FOLLOWER_LIST_IDS = ("recycler_view", "follow_list_container")
    _SEE_MORE_IDS = ("see_more_button",)
    _PROFILE_USERNAME_IDS = (
        "action_bar_title",
        "profile_header_username",
        "profile_header_user_name",
        "profile_username",
    )
    _DISPLAY_NAME_IDS = (
        "profile_header_full_name_above_vanity",
        "profile_header_full_name",
        "profile_name",
    )
    _BIOGRAPHY_IDS = ("profile_header_bio_text", "profile_bio")
    _BIOGRAPHY_CONTAINER_IDS = ("profile_user_info_compose_view",)
    _CATEGORY_IDS = ("profile_header_business_category",)
    _WEBSITE_IDS = ("text_view",)
    _PROFILE_LINKS_IDS = ("profile_links_view",)
    _ADDRESS_IDS = ("address_text",)
    _POST_COUNT_IDS = ("profile_header_familiar_post_count_value",)
    _FOLLOWER_COUNT_IDS = ("profile_header_familiar_followers_value",)
    _FOLLOWING_COUNT_IDS = ("profile_header_familiar_following_value",)
    _VERIFIED_IDS = ("action_bar_title_verified_badge",)
    _CONTACT_DIALOG_IDS = ("contact_options_rv",)
    _CONTACT_IDS = (
        "button_container",
        "profile_header_contact_button",
        "contact_button",
    )
    _FOLLOW_BUTTON_IDS = (
        "profile_header_follow_button",
        "profile_header_user_action_follow_button",
        "profile_action_follow_button",
        "follow_button",
    )
    _PRIVATE_IDS = (
        "row_profile_header_empty_profile_notice_title",
        "private_profile_empty_state",
        "private_account",
    )
    _FOLLOWING_MUTE_ROW_IDS = ("follow_sheet_mute_row",)
    _MUTE_TITLE_IDS = ("title_text_view",)
    _BOTTOM_SHEET_IDS = ("bottom_sheet_container_view",)

    def __init__(
        self,
        contact_scraper: ContactScraper,
        *,
        device_factory: Callable[[str], object] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        navigation_wait: float = 1.0,
        verification_delay: float = 2.0,
        search_timeout: float = 15.0,
        search_poll_interval: float = 0.5,
        search_settle_delay: Callable[[], float] = lambda: random.uniform(2.0, 3.0),
        profile_observer: (
            Callable[[RuntimeContext, CandidateProfile], None] | None
        ) = None,
        mute_after_follow: bool = False,
    ) -> None:
        if navigation_wait < 0:
            raise ValueError("Navigation wait cannot be negative")
        if verification_delay < 0:
            raise ValueError("Verification delay cannot be negative")
        if search_timeout < 0:
            raise ValueError("Search timeout cannot be negative")
        if search_poll_interval <= 0:
            raise ValueError("Search poll interval must be positive")
        self._contact_scraper = contact_scraper
        self._device_factory = device_factory or self._connect
        self._sleeper = sleeper
        self._clock = clock
        self._navigation_wait = navigation_wait
        self._verification_delay = verification_delay
        self._search_timeout = search_timeout
        self._search_poll_interval = search_poll_interval
        self._search_settle_delay = search_settle_delay
        self._profile_observer = profile_observer
        self._mute_after_follow = mute_after_follow
        self.profile_loading_timed_out = False

    def locate_source(
        self, context: RuntimeContext, source_username: str
    ) -> AndroidFollowResult:
        """Locate and open an exact source username through Instagram Search."""

        username = source_username.strip()
        context.logger.info("[Search] Starting source search", source=username)
        if not username:
            context.logger.error("[Search] Action failed", reason="empty source")
            return AndroidFollowResult(
                AndroidFollowStatus.SOURCE_NOT_FOUND,
                "Source username cannot be empty.",
            )
        try:
            device = self._device(context)
            search_nodes = self._nodes(device.dump_hierarchy(compressed=False))
            if self._find_by_id(search_nodes, self._SEARCH_INPUT_IDS) is not None:
                context.logger.info("[Search] Resetting existing Search field")
            else:
                context.logger.info("[Search] Opening Search tab")
                context.logger.debug("[Search] Waiting for Search tab UI hierarchy")
                search_tab = self._find_navigation(
                    search_nodes, self._SEARCH_TAB_IDS, "search"
                )
                if search_tab is None:
                    context.logger.info("[Search] Returning to Search navigation")
                    device.press("back")
                    search_nodes = self._nodes(device.dump_hierarchy(compressed=False))
                    search_tab = self._find_navigation(
                        search_nodes, self._SEARCH_TAB_IDS, "search"
                    )
                if search_tab is None:
                    context.logger.error(
                        "[Search] Action failed", reason="Search tab unavailable"
                    )
                    return self._source_not_found(
                        username, "Search tab is unavailable."
                    )
                context.logger.info(
                    "[Search] Search tab detected", resource_id=search_tab.resource_id
                )
                self._tap(device, search_tab)
                context.logger.info("[Search] Search tab opened")
                search_nodes = self._search_nodes(
                    context, device, "Search field", retry=False
                )
            search_input = self._find_by_id(search_nodes, self._SEARCH_INPUT_IDS)
            if search_input is None:
                context.logger.error(
                    "[Search] Action failed", reason="Search field unavailable"
                )
                return self._source_not_found(username, "Search input is unavailable.")
            context.logger.info(
                "[Search] Search field detected", resource_id=search_input.resource_id
            )
            self._tap(device, search_input)
            context.logger.info("[Search] Searching source", source=username)
            device.send_keys(username, clear=True)
            context.logger.info("[Search] Source username entered", source=username)
            self._sleeper(self._search_settle_delay())
            return self._poll_source_search(context, device, username)
        except Exception as error:  # noqa: BLE001 - Android isolation boundary
            context.logger.error("[Search] Action failed", reason=str(error))
            return self._source_not_found(username, f"Source search failed: {error}")

    def open_account(
        self, context: RuntimeContext, username: str
    ) -> CandidateObservation | None:
        """Open one exact account through the existing Instagram search flow."""

        result = self.locate_source(context, username)
        if result.status is not AndroidFollowStatus.SUCCESS:
            return None
        return CandidateObservation(username=username)

    def _poll_source_search(
        self, context: RuntimeContext, device: object, username: str
    ) -> AndroidFollowResult:
        state = _SearchState.RESULTS
        deadline = self._clock() + self._search_timeout
        attempt = 0
        while True:
            attempt += 1
            context.logger.debug(
                "[Search] Waiting for UI element",
                state=state.value,
                attempt=attempt,
                timeout_seconds=self._search_timeout,
            )
            hierarchy = device.dump_hierarchy(compressed=False)
            nodes = self._nodes(hierarchy)
            context.logger.debug(
                "[Search] UI hierarchy received",
                state=state.value,
                attempt=attempt,
                visible_nodes=len(nodes),
            )

            if state is _SearchState.PROFILE:
                profile_username = self._profile_username(nodes)
                if profile_username.casefold() == username.casefold():
                    context.logger.info(
                        "[Search] Source profile opened", source=username
                    )
                    return AndroidFollowResult(AndroidFollowStatus.SUCCESS)
            else:
                if any(
                    self._id_has_suffix(node.resource_id, ("row_search_keyword_title",))
                    for node in nodes
                ):
                    context.logger.debug("[Search] Keyword suggestion ignored")
                exact = self._exact_search_user_row(hierarchy, username)
                if exact is not None:
                    if state is _SearchState.RESULTS:
                        context.logger.info("[Search] Exact account already visible")
                    elif state is _SearchState.ACCOUNTS_RESULTS:
                        context.logger.info(
                            "[Search] Exact account detected after Accounts"
                        )
                    context.logger.info(
                        "[Search] Exact source username detected",
                        resource_id=exact.resource_id,
                        attempt=attempt,
                    )
                    context.logger.info("[Search] Opening source profile")
                    device.click(*exact.center)
                    context.logger.info("[Search] Source profile click performed")
                    state = _SearchState.PROFILE
                elif state is _SearchState.RESULTS:
                    search_action = self._find_text(nodes, "search")
                    keyword_visible = (
                        self._find_by_id(nodes, ("row_search_keyword_title",))
                        is not None
                    )
                    if keyword_visible or search_action is not None or attempt >= 2:
                        context.logger.info("[Search] Executing search")
                        if search_action is not None:
                            device.click(*search_action.center)
                        else:
                            device.press("enter")
                        context.logger.info(
                            "[Search] Waiting for refreshed search results"
                        )
                        state = _SearchState.SEARCH_RESULTS
                elif state is _SearchState.SEARCH_RESULTS:
                    accounts_tab = self._find_navigation(
                        nodes, self._ACCOUNTS_TAB_IDS, "accounts"
                    )
                    if accounts_tab is None:
                        accounts_tab = next(
                            (
                                node
                                for node in nodes
                                if self._id_has_suffix(
                                    node.resource_id, ("tab_button_name_text",)
                                )
                                and node.text.strip().casefold() == "accounts"
                            ),
                            None,
                        )
                    if accounts_tab is not None:
                        context.logger.info(
                            "[Search] Accounts tab detected",
                            resource_id=accounts_tab.resource_id,
                        )
                        context.logger.info("[Search] Opening Accounts tab")
                        device.click(*accounts_tab.center)
                        context.logger.info("[Search] Accounts tab switch performed")
                        state = _SearchState.ACCOUNTS_RESULTS

            if self._clock() >= deadline:
                context.logger.error(
                    "[Search] Source failed after all search strategies",
                    state=state.value,
                    attempts=attempt,
                    source=username,
                )
                detail = (
                    "Source profile did not open before timeout."
                    if state is _SearchState.PROFILE
                    else "Exact source username was not found before timeout."
                )
                return self._source_not_found(username, detail)

            context.logger.debug(
                "[Search] Retry scheduled",
                state=state.value,
                next_attempt=attempt + 1,
                wait_seconds=self._search_poll_interval,
            )
            self._sleeper(self._search_poll_interval)

    @classmethod
    def _profile_username(cls, nodes: tuple[_Node, ...]) -> str:
        node = cls._find_by_id(nodes, cls._PROFILE_USERNAME_IDS)
        return (node.text or node.description).strip() if node is not None else ""

    def _search_nodes(
        self,
        context: RuntimeContext,
        device: object,
        element: str,
        *,
        retry: bool,
    ) -> tuple[_Node, ...]:
        context.logger.debug(
            "[Search] Waiting for UI element",
            element=element,
            wait_seconds=self._navigation_wait,
        )
        nodes = self._fresh_nodes(device)
        context.logger.debug(
            "[Search] UI hierarchy received",
            element=element,
            visible_nodes=len(nodes),
        )
        if not retry:
            context.logger.debug(
                "[Search] Retry not configured for this UI step", element=element
            )
        return nodes

    def open_followers(self, context: RuntimeContext) -> AndroidFollowResult:
        """Open the source profile's Followers list."""

        return self._open_relationship_list(context, "Followers", self._FOLLOWERS_IDS)

    def open_following(self, context: RuntimeContext) -> AndroidFollowResult:
        """Open the source profile's Following list."""

        return self._open_relationship_list(context, "Following", self._FOLLOWING_IDS)

    def _open_relationship_list(
        self,
        context: RuntimeContext,
        label: str,
        resource_ids: tuple[str, ...],
    ) -> AndroidFollowResult:
        """Open one profile relationship list through its inspected control."""

        try:
            context.logger.info(f"[{label}] Locating {label} control")
            device = self._device(context)
            context.logger.debug(f"[{label}] Reading source profile hierarchy")
            nodes = self._nodes(device.dump_hierarchy(compressed=False))
            control = self._find_by_id(nodes, resource_ids)
            if control is None:
                control = self._find_text(nodes, label.casefold())
            if control is None:
                context.logger.error(
                    f"[{label}] Action failed",
                    reason=f"{label} control unavailable",
                )
                return AndroidFollowResult(
                    AndroidFollowStatus.FOLLOW_FAILED,
                    f"{label} control is unavailable.",
                )
            context.logger.info(
                f"[{label}] {label} control found",
                resource_id=control.resource_id,
            )
            self._tap(device, control)
            context.logger.info(f"[{label}] {label} list opened")
            return AndroidFollowResult(AndroidFollowStatus.SUCCESS)
        except Exception as error:  # noqa: BLE001 - Android isolation boundary
            context.logger.error(f"[{label}] Action failed", reason=str(error))
            return AndroidFollowResult(
                AndroidFollowStatus.FOLLOW_FAILED,
                f"Opening {label} failed: {error}",
            )

    def show_more_followers(self, context: RuntimeContext) -> AndroidFollowResult:
        """Tap See More when the followers surface exposes it."""

        try:
            device = self._device(context)
            nodes = self._fresh_nodes(device)
            node = self._find_by_id(nodes, self._SEE_MORE_IDS)
            if node is None:
                node = self._find_text(nodes, "see more")
            if node is None:
                return AndroidFollowResult(AndroidFollowStatus.SUCCESS)
            self._tap(device, node)
            self._wait()
            return AndroidFollowResult(AndroidFollowStatus.SUCCESS)
        except Exception as error:  # noqa: BLE001 - Android isolation boundary
            return AndroidFollowResult(
                AndroidFollowStatus.FOLLOW_FAILED,
                f"See More failed: {error}",
            )

    def search_followers(
        self, context: RuntimeContext, prefix: str
    ) -> AndroidFollowResult:
        """Enter a provider-selected Random Search Letters prefix."""

        try:
            device = self._device(context)
            search = self._find_by_id(
                self._fresh_nodes(device), self._FOLLOWER_SEARCH_IDS
            )
            if search is None:
                return AndroidFollowResult(
                    AndroidFollowStatus.FOLLOW_FAILED,
                    "Followers search input is unavailable.",
                )
            self._tap(device, search)
            device.send_keys(prefix, clear=True)
            self._wait()
            return AndroidFollowResult(AndroidFollowStatus.SUCCESS)
        except Exception as error:  # noqa: BLE001 - Android isolation boundary
            return AndroidFollowResult(
                AndroidFollowStatus.FOLLOW_FAILED,
                f"Followers search failed: {error}",
            )

    def scroll_followers(self, context: RuntimeContext) -> AndroidFollowResult:
        """Perform one bounded followers-list scroll action."""

        try:
            device = self._device(context)
            nodes = self._fresh_nodes(device)
            container = self._find_scrollable(nodes)
            if container is None:
                return AndroidFollowResult(
                    AndroidFollowStatus.FOLLOW_FAILED,
                    "Followers list is not scrollable.",
                )
            left, top, right, bottom = container.bounds
            x = (left + right) // 2
            device.swipe(x, bottom - 1, x, top + 1, duration=0.4)
            self._wait()
            return AndroidFollowResult(AndroidFollowStatus.SUCCESS)
        except Exception as error:  # noqa: BLE001 - Android isolation boundary
            return AndroidFollowResult(
                AndroidFollowStatus.FOLLOW_FAILED,
                f"Followers scrolling failed: {error}",
            )

    def scroll_following_list(self, context: RuntimeContext) -> AndroidFollowResult:
        """Scroll a Following list with intentional viewport overlap."""

        try:
            device = self._device(context)
            nodes = self._fresh_nodes(device)
            container = self._find_by_id(nodes, ("list",))
            if container is None:
                container = self._find_by_id(nodes, ("unified_follow_list_view_pager",))
            if container is None:
                container = self._find_scrollable(nodes)
            if container is None:
                return AndroidFollowResult(
                    AndroidFollowStatus.FOLLOW_FAILED,
                    "Following list is not scrollable.",
                )
            left, top, right, bottom = container.bounds
            x = (left + right) // 2
            visible_height = bottom - top
            distance = max(1, round(visible_height * 0.65))
            start_y = bottom - 1
            end_y = max(top + 1, start_y - distance)
            device.swipe(x, start_y, x, end_y, duration=0.4)
            self._wait()
            return AndroidFollowResult(AndroidFollowStatus.SUCCESS)
        except Exception as error:  # noqa: BLE001 - Android isolation boundary
            return AndroidFollowResult(
                AndroidFollowStatus.FOLLOW_FAILED,
                f"Following-list scrolling failed: {error}",
            )

    def open_candidate_profile(
        self, context: RuntimeContext, candidate: Candidate
    ) -> AndroidFollowResult:
        """Open an exact visible follower and read profile qualification facts."""

        self.profile_loading_timed_out = False
        try:
            context.logger.info(
                "[Candidate] Locating exact candidate", username=candidate.username
            )
            device = self._device(context)
            nodes = self._fresh_nodes(device)
            visible_username = self._profile_username(nodes)
            if visible_username.casefold() == candidate.username.casefold():
                context.logger.info(
                    "[Candidate] Candidate profile already open",
                    username=candidate.username,
                )
                hierarchy = device.dump_hierarchy(compressed=False)
                nodes = self._nodes(hierarchy)
            else:
                exact = self._exact_username(nodes, candidate.username)
                if exact is None:
                    context.logger.error(
                        "[Candidate] Action failed",
                        reason="candidate not visible",
                        username=candidate.username,
                    )
                    return AndroidFollowResult(
                        AndroidFollowStatus.FOLLOW_FAILED,
                        f"Candidate is not visible: {candidate.username}",
                    )
                context.logger.info(
                    "[Candidate] Exact candidate found", resource_id=exact.resource_id
                )
                context.logger.info("[Candidate] Opening candidate profile")
                self._tap(device, exact)
                context.logger.debug("[Candidate] Verifying opened profile")
                self._wait()
                hierarchy = device.dump_hierarchy(compressed=False)
                nodes = self._nodes(hierarchy)
            username_node = self._find_by_id(nodes, self._PROFILE_USERNAME_IDS)
            observed_username = (
                username_node.text.strip() if username_node is not None else ""
            )
            if observed_username.casefold() != candidate.username.casefold():
                context.logger.error(
                    "[Candidate] Profile verification failed",
                    expected=candidate.username,
                    observed=observed_username,
                )
                return AndroidFollowResult(
                    AndroidFollowStatus.FOLLOW_FAILED,
                    "Opened profile does not match the selected candidate.",
                )
            context.logger.info("[Profile] Waiting for profile metrics...")
            ready_hierarchy = wait_for_profile_ready(
                device,
                hierarchy,
                username_ids=self._PROFILE_USERNAME_IDS,
                metric_ids=(
                    *self._FOLLOWER_COUNT_IDS,
                    *self._FOLLOWING_COUNT_IDS,
                    *self._POST_COUNT_IDS,
                ),
                clock=self._clock,
                sleeper=self._sleeper,
            )
            if ready_hierarchy is None:
                self.profile_loading_timed_out = True
                context.logger.warning("[Profile] Profile loading timeout.")
                self._recover_after_profile_failure(context, candidate)
                return AndroidFollowResult(
                    AndroidFollowStatus.FOLLOW_FAILED, "Profile loading timeout."
                )
            context.logger.info("[Profile] Profile ready.")
            hierarchy = ready_hierarchy
            nodes = self._nodes(hierarchy)
            name = self._find_by_id(nodes, self._DISPLAY_NAME_IDS)
            biography = self._profile_biography(hierarchy, nodes)
            expansion = self._biography_expansion(hierarchy, biography)
            if expansion is not None:
                context.logger.info("[Candidate] Expanding biography")
                device.click(*expansion.center)
                for _attempt in range(3):
                    self._wait()
                    hierarchy = device.dump_hierarchy(compressed=False)
                    nodes = self._nodes(hierarchy)
                    expanded = self._profile_biography(hierarchy, nodes)
                    if (
                        expanded != biography
                        and self._biography_expansion(hierarchy, expanded) is None
                    ):
                        biography = expanded
                        context.logger.info("[Candidate] Biography expanded")
                        break
                else:
                    raise RuntimeError("Biography did not expand after one tap")
                ready_hierarchy = wait_for_profile_ready(
                    device,
                    hierarchy,
                    username_ids=self._PROFILE_USERNAME_IDS,
                    metric_ids=(
                        *self._FOLLOWER_COUNT_IDS,
                        *self._FOLLOWING_COUNT_IDS,
                        *self._POST_COUNT_IDS,
                    ),
                    clock=self._clock,
                    sleeper=self._sleeper,
                )
                if ready_hierarchy is None:
                    self.profile_loading_timed_out = True
                    context.logger.warning("[Profile] Profile loading timeout.")
                    self._recover_after_profile_failure(context, candidate)
                    return AndroidFollowResult(
                        AndroidFollowStatus.FOLLOW_FAILED, "Profile loading timeout."
                    )
                hierarchy = ready_hierarchy
                nodes = self._nodes(hierarchy)
            category = self._find_by_id(nodes, self._CATEGORY_IDS)
            website = self._find_by_id(nodes, self._WEBSITE_IDS)
            address = self._find_by_id(nodes, self._ADDRESS_IDS)
            follow_button = self._follow_button(nodes)
            website_value = website.text.strip() if website is not None else ""
            profile = CandidateProfile(
                candidate=candidate,
                username=observed_username,
                display_name=name.text.strip() if name is not None else "",
                biography=biography,
                is_private=self._is_private(nodes),
                category=category.text.strip() if category is not None else "",
                website=website_value,
                address=address.text.strip() if address is not None else "",
                followers=self._profile_count(nodes, self._FOLLOWER_COUNT_IDS),
                following=self._profile_count(nodes, self._FOLLOWING_COUNT_IDS),
                posts=self._profile_count(nodes, self._POST_COUNT_IDS),
                is_business=category is not None,
                is_verified=self._find_by_id(nodes, self._VERIFIED_IDS) is not None,
                follow_status=self._button_state(follow_button),
                has_external_links=(
                    self._find_by_id(nodes, self._PROFILE_LINKS_IDS) is not None
                    or bool(website_value)
                ),
            )
            context.logger.info(
                "[Candidate] Profile verified", username=observed_username
            )
            if self._profile_observer is not None:
                self._profile_observer(context, profile)
            return AndroidFollowResult(AndroidFollowStatus.SUCCESS, profile=profile)
        except Exception as error:  # noqa: BLE001 - Android isolation boundary
            context.logger.error("[Candidate] Action failed", reason=str(error))
            return AndroidFollowResult(
                AndroidFollowStatus.FOLLOW_FAILED,
                f"Opening candidate profile failed: {error}",
            )

    def open_profile(
        self, context: RuntimeContext, candidate: Candidate
    ) -> CandidateProfile | None:
        """Implement the Follow Module CandidateProfileProvider contract."""

        return self.open_candidate_profile(context, candidate).profile

    def scrape_contact(self, context: RuntimeContext) -> AndroidFollowResult:
        """Open Contact, delegate parsing, and always return to the profile."""

        try:
            device = self._device(context)
            contact = self._find_contact(self._fresh_nodes(device))
            if contact is None:
                context.logger.info(
                    "[Contact] No Contact button found. Profile metadata saved."
                )
                return AndroidFollowResult(AndroidFollowStatus.CONTACT_NOT_AVAILABLE)
            self._tap(device, contact)
            try:
                hierarchy = device.dump_hierarchy(compressed=False)
                if (
                    self._find_by_id(self._nodes(hierarchy), self._CONTACT_DIALOG_IDS)
                    is None
                ):
                    raise RuntimeError("Contact dialog did not open")
                details = dict(self._contact_scraper.scrape(context, hierarchy))
            finally:
                self._navigate_back(context, device)
            if not self._is_profile_screen(self._fresh_nodes(device)):
                return AndroidFollowResult(
                    AndroidFollowStatus.FOLLOW_FAILED,
                    "Contact popup closed, but the profile screen did not return.",
                )
            context.logger.info("[Contact] Contact scraping complete.")
            return AndroidFollowResult(
                AndroidFollowStatus.CONTACT_SCRAPED,
                contact_details=details,
            )
        except Exception as error:  # noqa: BLE001 - Android isolation boundary
            return AndroidFollowResult(
                AndroidFollowStatus.FOLLOW_FAILED,
                f"Contact scraping failed: {error}",
            )

    def execute_follow(self, context: RuntimeContext) -> AndroidFollowResult:
        """Tap Follow once, verify it, and return to the followers list."""

        try:
            device = self._device(context)
            button = self._follow_button(self._fresh_nodes(device))
            state = self._button_state(button)
            if state == "following":
                result = AndroidFollowResult(AndroidFollowStatus.ALREADY_FOLLOWING)
            elif state == "requested":
                result = AndroidFollowResult(AndroidFollowStatus.REQUESTED)
            elif state == "follow back":
                result = AndroidFollowResult(AndroidFollowStatus.FOLLOW_BACK)
            elif state != "follow" or button is None:
                result = AndroidFollowResult(
                    AndroidFollowStatus.FOLLOW_FAILED,
                    "Follow button is unavailable.",
                )
            else:
                device.click(*button.center)
                verified = self._poll_follow_state(context, device)
                if verified == "following":
                    result = AndroidFollowResult(AndroidFollowStatus.SUCCESS)
                    return self._mute_and_return(context, device, result)
                elif verified == "requested":
                    result = AndroidFollowResult(AndroidFollowStatus.REQUESTED)
                elif verified == "follow":
                    result = AndroidFollowResult(
                        AndroidFollowStatus.GHOST_BLOCK_DETECTED
                    )
                else:
                    result = AndroidFollowResult(
                        AndroidFollowStatus.FOLLOW_FAILED,
                        "Follow state could not be verified.",
                    )
            return self._navigate_back(context, device, result)
        except Exception as error:  # noqa: BLE001 - Android isolation boundary
            return AndroidFollowResult(
                AndroidFollowStatus.FOLLOW_FAILED,
                f"Follow execution failed: {error}",
            )

    def _mute_and_return(
        self,
        context: RuntimeContext,
        device: object,
        result: AndroidFollowResult,
    ) -> AndroidFollowResult:
        """Apply the optional post-follow mute action and restore Followers."""

        if not self._mute_after_follow:
            context.logger.info("[Mute] Mute users after following disabled. Skipping.")
            return self._navigate_back(context, device, result)

        warning = ""
        mute_completed = False
        try:
            following = self._follow_button(self._fresh_nodes(device))
            if self._button_state(following) != "following" or following is None:
                raise RuntimeError("verified Following control is unavailable")
            self._tap(device, following)
            menu_nodes = self._fresh_nodes(device)
            mute_row = self._find_by_id(menu_nodes, self._FOLLOWING_MUTE_ROW_IDS)
            if mute_row is None:
                raise RuntimeError("Following menu did not expose Mute")
            self._tap(device, mute_row)
            hierarchy = device.dump_hierarchy(compressed=False)
            if not self._is_mute_page(hierarchy):
                raise RuntimeError("Mute page did not open")
            context.logger.info("[Mute] Mute settings opened.")
            enabled, unchanged, hierarchy = self._enable_all_mute_switches(
                context, device, hierarchy
            )
            context.logger.info(
                "[Mute] Mute switches ready.",
                enabled=enabled,
                unchanged=unchanged,
            )
            self._dismiss_mute_page(device, hierarchy)
            if not self._wait_for_mute_closed(device):
                device.press("back")
            if not self._wait_for_mute_closed(device):
                raise RuntimeError("Mute page did not close")
            mute_completed = True
        except Exception as error:  # noqa: BLE001 - optional Android UI boundary
            warning = f"Mute could not be completed: {error}"
            context.logger.warning("[Mute] Action failed.", reason=str(error))

        returned = self._navigate_back(context, device, result)
        if warning:
            detail = " ".join(value for value in (returned.detail, warning) if value)
            returned = AndroidFollowResult(
                returned.status,
                detail,
                profile=returned.profile,
                contact_details=returned.contact_details,
            )
        followers_restored = self._is_followers_screen(self._fresh_nodes(device))
        if mute_completed and followers_restored:
            context.logger.info("[Mute] Mute completed.")
        elif not followers_restored:
            context.logger.warning("[Mute] Followers list was not detected after mute.")
        if (
            mute_completed
            and followers_restored
            and returned.status is AndroidFollowStatus.SUCCESS
        ):
            returned = AndroidFollowResult(
                returned.status,
                returned.detail,
                profile=returned.profile,
                contact_details=returned.contact_details,
                muted=True,
            )
        return returned

    def _enable_all_mute_switches(
        self, context: RuntimeContext, device: object, hierarchy: str
    ) -> tuple[int, int, str]:
        seen: set[tuple[int, ...]] = set()
        enabled = 0
        unchanged = 0
        for _attempt in range(10):
            switches = self._mute_switches(hierarchy)
            new_switches = [
                switch for switch in switches if switch.identity not in seen
            ]
            for switch in new_switches:
                seen.add(switch.identity)
                current = next(
                    (
                        item
                        for item in self._mute_switches(hierarchy)
                        if item.identity == switch.identity
                    ),
                    switch,
                )
                if current.checked:
                    unchanged += 1
                    continue
                device.click(*current.center)
                hierarchy = self._wait_for_mute_switch(
                    device, current.identity, hierarchy
                )
                enabled += 1

            sheet = self._find_by_id(self._nodes(hierarchy), self._BOTTOM_SHEET_IDS)
            switches = self._mute_switches(hierarchy)
            if sheet is None or not self._mute_content_may_continue(switches, sheet):
                break
            context.logger.info("[Mute] Checking additional mute switches.")
            left, top, right, bottom = sheet.bounds
            x = (left + right) // 2
            device.swipe(x, bottom - 1, x, top + 1, duration=0.4)
            next_hierarchy = self._wait_for_hierarchy_change(device, hierarchy)
            next_switches = self._mute_switches(next_hierarchy)
            if not any(switch.identity not in seen for switch in next_switches):
                break
            hierarchy = next_hierarchy
        return enabled, unchanged, hierarchy

    def _wait_for_mute_switch(
        self,
        device: object,
        identity: tuple[str, ...],
        hierarchy: str,
    ) -> str:
        for attempt in range(10):
            hierarchy = device.dump_hierarchy(compressed=False)
            switch = next(
                (
                    item
                    for item in self._mute_switches(hierarchy)
                    if item.identity == identity
                ),
                None,
            )
            if switch is not None and switch.checked:
                return hierarchy
            if attempt < 9:
                self._sleeper(0.1)
        raise RuntimeError("Mute switch did not become enabled")

    def _wait_for_hierarchy_change(self, device: object, previous: str) -> str:
        hierarchy = previous
        for attempt in range(10):
            hierarchy = device.dump_hierarchy(compressed=False)
            if hierarchy != previous:
                return hierarchy
            if attempt < 9:
                self._sleeper(0.1)
        return hierarchy

    def _wait_for_mute_closed(self, device: object) -> bool:
        for attempt in range(10):
            if not self._is_mute_page(device.dump_hierarchy(compressed=False)):
                return True
            if attempt < 9:
                self._sleeper(0.1)
        return False

    @staticmethod
    def _mute_content_may_continue(
        switches: tuple[_MuteSwitch, ...], sheet: _Node
    ) -> bool:
        if not switches:
            return False
        row_height = max(
            bottom - top for _left, top, _right, bottom in (s.bounds for s in switches)
        )
        return (
            max(switch.bounds[3] for switch in switches) >= sheet.bounds[3] - row_height
        )

    def _dismiss_mute_page(self, device: object, hierarchy: str) -> None:
        sheet = self._find_by_id(self._nodes(hierarchy), self._BOTTOM_SHEET_IDS)
        if sheet is None:
            raise RuntimeError("Mute bottom sheet is unavailable")
        left, top, right, _bottom = sheet.bounds
        device.click((left + right) // 2, max(1, top // 2))

    @classmethod
    def _is_mute_page(cls, hierarchy: str) -> bool:
        nodes = cls._nodes(hierarchy)
        title = cls._find_by_id(nodes, cls._MUTE_TITLE_IDS)
        return (
            title is not None
            and cls._button_state(title) == "mute"
            and cls._find_by_id(nodes, cls._BOTTOM_SHEET_IDS) is not None
        )

    @classmethod
    def _mute_switches(cls, hierarchy: str) -> tuple[_MuteSwitch, ...]:
        root = ET.fromstring(hierarchy)
        switches: list[_MuteSwitch] = []

        def visit(
            element: ET.Element,
            path: tuple[int, ...],
            descriptors: tuple[str, ...],
        ) -> None:
            resource_id = element.get("resource-id", "").rsplit("/", 1)[-1]
            label = (element.get("text", "") or element.get("content-desc", "")).strip()
            descriptor = "|".join(value for value in (resource_id, label) if value)
            trail = (*descriptors, descriptor) if descriptor else descriptors
            if (
                element.tag == "node"
                and element.get("class") == "android.widget.ToggleButton"
                and element.get("checkable") == "true"
                and element.get("visible-to-user", "true") == "true"
            ):
                match = cls._BOUNDS_PATTERN.fullmatch(element.get("bounds", ""))
                if match is not None:
                    switches.append(
                        _MuteSwitch(
                            identity=trail or tuple(str(index) for index in path),
                            bounds=tuple(int(value) for value in match.groups()),
                            checked=element.get("checked") == "true",
                        )
                    )
            for index, child in enumerate(element):
                visit(child, (*path, index), trail)

        visit(root, (), ())
        return tuple(switches)

    def _poll_follow_state(self, context: RuntimeContext, device: object) -> str:
        """Observe the Follow button throughout the configured verification window."""
        interval = min(0.5, self._verification_delay or 0)
        polls = max(1, ceil(self._verification_delay / interval)) if interval else 1
        state = ""
        for attempt in range(polls + 1):
            state = self._button_state(
                self._follow_button(
                    self._nodes(device.dump_hierarchy(compressed=False))
                )
            )
            context.logger.debug(
                "[Follow] Verification poll",
                attempt=attempt + 1,
                state=state or "unavailable",
            )
            if attempt < polls:
                self._sleeper(interval)
        return state

    def _navigate_back(
        self,
        context: RuntimeContext,
        device: object,
        result: AndroidFollowResult | None = None,
    ) -> AndroidFollowResult:
        outcome = result or AndroidFollowResult(AndroidFollowStatus.SUCCESS)
        try:
            device.press("back")
            self._wait()
            return outcome
        except Exception as error:  # noqa: BLE001 - Android isolation boundary
            context.logger.warning("Returning to Followers failed", reason=str(error))
            detail = outcome.detail or "Navigation outcome recorded."
            return AndroidFollowResult(
                outcome.status,
                f"{detail} Returning to Followers failed: {error}",
                profile=outcome.profile,
                contact_details=outcome.contact_details,
            )

    def return_to_followers(self, context: RuntimeContext) -> AndroidFollowResult:
        """Return one level to the existing followers list without reopening it."""
        context.logger.info("[Candidate] Returning to Followers list...")
        device = self._device(context)
        result = self._navigate_back(context, device)
        if result.status is not AndroidFollowStatus.SUCCESS:
            return result
        if not self._is_followers_screen(self._fresh_nodes(device)):
            context.logger.error(
                "[Candidate] Followers list recovery failed",
                reason="followers list not detected",
            )
            return AndroidFollowResult(
                AndroidFollowStatus.FOLLOW_FAILED,
                "Followers list did not return after candidate rejection.",
            )
        context.logger.info("[Candidate] Followers list restored.")
        return result

    def _recover_after_profile_failure(
        self, context: RuntimeContext, candidate: Candidate
    ) -> AndroidFollowResult:
        if candidate.provider_type is CandidateProviderType.SPECIFIC_ACCOUNTS:
            return self._return_to_search(context)
        return self.return_to_followers(context)

    def _return_to_search(self, context: RuntimeContext) -> AndroidFollowResult:
        """Return one level from a Specific Users profile to Instagram Search."""

        context.logger.info("[Specific] Returning to Instagram Search...")
        device = self._device(context)
        result = self._navigate_back(context, device)
        if result.status is not AndroidFollowStatus.SUCCESS:
            return result
        if self._find_by_id(self._fresh_nodes(device), self._SEARCH_INPUT_IDS) is None:
            context.logger.error(
                "[Specific] Search recovery failed",
                reason="Search screen not detected",
            )
            return AndroidFollowResult(
                AndroidFollowStatus.FOLLOW_FAILED,
                "Instagram Search did not return after profile loading timeout.",
            )
        context.logger.info("[Specific] Instagram Search restored.")
        return result

    def _device(self, context: RuntimeContext) -> object:
        return self._device_factory(context.session.phone_id)

    def _fresh_nodes(self, device: object) -> tuple[_Node, ...]:
        self._wait()
        return self._nodes(device.dump_hierarchy(compressed=False))

    def _wait(self) -> None:
        self._sleeper(self._navigation_wait)

    def _tap(self, device: object, node: _Node) -> None:
        device.click(*node.center)
        self._wait()

    @classmethod
    def _nodes(cls, hierarchy: str) -> tuple[_Node, ...]:
        root = ET.fromstring(hierarchy)
        nodes = []
        for element in root.iter("node"):
            bounds = cls._BOUNDS_PATTERN.fullmatch(element.get("bounds", ""))
            if bounds is None:
                continue
            nodes.append(
                _Node(
                    text=element.get("text", ""),
                    description=element.get("content-desc", ""),
                    resource_id=element.get("resource-id", ""),
                    bounds=tuple(int(value) for value in bounds.groups()),
                    scrollable=element.get("scrollable", "false") == "true",
                    class_name=element.get("class", ""),
                    checkable=element.get("checkable", "false") == "true",
                    checked=element.get("checked", "false") == "true",
                )
            )
        return tuple(nodes)

    @classmethod
    def _find_by_id(
        cls, nodes: tuple[_Node, ...], identifiers: tuple[str, ...]
    ) -> _Node | None:
        return next(
            (
                node
                for node in nodes
                if cls._id_has_suffix(node.resource_id, identifiers)
            ),
            None,
        )

    @classmethod
    def _find_navigation(
        cls,
        nodes: tuple[_Node, ...],
        identifiers: tuple[str, ...],
        label: str,
    ) -> _Node | None:
        return cls._find_by_id(nodes, identifiers) or next(
            (
                node
                for node in nodes
                if node.description.strip().casefold() == label.casefold()
            ),
            None,
        )

    @staticmethod
    def _find_text(nodes: tuple[_Node, ...], text: str) -> _Node | None:
        expected = text.casefold()
        return next(
            (
                node
                for node in nodes
                if node.text.strip().casefold() == expected
                or node.description.strip().casefold() == expected
            ),
            None,
        )

    @classmethod
    def _exact_username(cls, nodes: tuple[_Node, ...], username: str) -> _Node | None:
        expected = username.casefold()
        return next(
            (
                node
                for node in nodes
                if cls._id_has_suffix(node.resource_id, cls._USERNAME_IDS)
                and node.text.strip().casefold() == expected
            ),
            None,
        )

    @classmethod
    def _exact_search_user_row(cls, hierarchy: str, username: str) -> _Node | None:
        """Match only usernames nested inside clickable account-result rows."""

        root = ET.fromstring(hierarchy)
        for row in root.iter("node"):
            if not cls._id_has_suffix(
                row.get("resource-id", ""), ("row_search_user_container",)
            ):
                continue
            if any(
                cls._id_has_suffix(
                    child.get("resource-id", ""), ("row_search_user_username",)
                )
                and child.get("text", "").strip().casefold() == username.casefold()
                for child in row.iter("node")
            ):
                return cls._find_by_id(
                    cls._nodes(ET.tostring(row, encoding="unicode")),
                    ("row_search_user_container",),
                )
        return None

    @classmethod
    def _find_scrollable(cls, nodes: tuple[_Node, ...]) -> _Node | None:
        return next(
            (
                node
                for node in nodes
                if node.scrollable
                or cls._id_has_suffix(node.resource_id, cls._FOLLOWER_LIST_IDS)
            ),
            None,
        )

    @classmethod
    def _find_contact(cls, nodes: tuple[_Node, ...]) -> _Node | None:
        labelled = cls._find_text(nodes, "contact")
        container = next(
            (
                node
                for node in nodes
                if cls._id_has_suffix(node.resource_id, cls._CONTACT_IDS)
                and (
                    cls._button_state(node) == "contact"
                    or (labelled is not None and cls._contains(node, labelled))
                )
            ),
            None,
        )
        return container or labelled

    @staticmethod
    def _contains(container: _Node, child: _Node) -> bool:
        left, top, right, bottom = container.bounds
        child_left, child_top, child_right, child_bottom = child.bounds
        return (
            left <= child_left
            and top <= child_top
            and right >= child_right
            and bottom >= child_bottom
        )

    @classmethod
    def _profile_count(
        cls, nodes: tuple[_Node, ...], identifiers: tuple[str, ...]
    ) -> int | None:
        node = cls._find_by_id(nodes, identifiers)
        if node is None:
            return None
        value = node.text.strip().casefold().replace(",", "")
        multiplier = 1
        if value.endswith("k"):
            value, multiplier = value[:-1], 1_000
        elif value.endswith("m"):
            value, multiplier = value[:-1], 1_000_000
        try:
            return int(float(value) * multiplier)
        except ValueError:
            return None

    @classmethod
    def _profile_biography(cls, hierarchy: str, nodes: tuple[_Node, ...]) -> str:
        explicit = cls._find_by_id(nodes, cls._BIOGRAPHY_IDS)
        if explicit is not None:
            return explicit.text.strip()
        root = ET.fromstring(hierarchy)
        container = next(
            (
                element
                for element in root.iter("node")
                if cls._id_has_suffix(
                    element.get("resource-id", ""), cls._BIOGRAPHY_CONTAINER_IDS
                )
            ),
            None,
        )
        if container is None:
            return ""
        return next(
            (
                element.get("text", "").strip()
                for element in container.iter("node")
                if element.get("class") == "android.widget.TextView"
                and not element.get("resource-id")
                and element.get("text", "").strip()
            ),
            "",
        )

    @classmethod
    def _biography_expansion(cls, hierarchy: str, biography: str) -> _Node | None:
        """Find the clickable ancestor of a visibly truncated Compose biography."""

        if not re.search(r"(?:…|\.{3})\s*(?:\S+\s*){1,3}$", biography):
            return None
        root = ET.fromstring(hierarchy)
        container = next(
            (
                element
                for element in root.iter("node")
                if cls._id_has_suffix(
                    element.get("resource-id", ""), cls._BIOGRAPHY_CONTAINER_IDS
                )
            ),
            None,
        )
        if container is None:
            return None
        for parent in container.iter("node"):
            if parent.get("clickable") != "true":
                continue
            if any(
                child.get("class") == "android.widget.TextView"
                and child.get("text", "").strip() == biography
                for child in parent.iter("node")
            ):
                return cls._nodes(ET.tostring(parent, encoding="unicode"))[0]
        return None

    @classmethod
    def _is_profile_screen(cls, nodes: tuple[_Node, ...]) -> bool:
        return cls._find_by_id(nodes, cls._PROFILE_USERNAME_IDS) is not None

    @classmethod
    def _is_followers_screen(cls, nodes: tuple[_Node, ...]) -> bool:
        return (
            cls._find_by_id(nodes, cls._FOLLOWER_LIST_IDS) is not None
            or cls._find_by_id(nodes, cls._USERNAME_IDS) is not None
        )

    @classmethod
    def _follow_button(cls, nodes: tuple[_Node, ...]) -> _Node | None:
        states = {"follow", "following", "requested", "follow back"}
        return next(
            (
                node
                for node in nodes
                if cls._id_has_suffix(node.resource_id, cls._FOLLOW_BUTTON_IDS)
                and cls._button_state(node) in states
            ),
            None,
        ) or next(
            (
                node
                for node in nodes
                if node.text.strip().casefold() in states
                or node.description.strip().casefold() in states
            ),
            None,
        )

    @staticmethod
    def _button_state(node: _Node | None) -> str:
        if node is None:
            return ""
        return (node.text or node.description).strip().casefold()

    @classmethod
    def _is_private(cls, nodes: tuple[_Node, ...]) -> bool:
        return cls._find_by_id(nodes, cls._PRIVATE_IDS) is not None or any(
            "account is private" in (node.text or node.description).casefold()
            for node in nodes
        )

    @staticmethod
    def _source_not_found(username: str, detail: str) -> AndroidFollowResult:
        return AndroidFollowResult(
            AndroidFollowStatus.SOURCE_NOT_FOUND,
            f"{detail} ({username})",
        )

    @staticmethod
    def _id_has_suffix(resource_id: str, suffixes: tuple[str, ...]) -> bool:
        return resource_id.rsplit("/", 1)[-1].casefold() in suffixes

    @staticmethod
    def _connect(serial: str) -> object:
        import uiautomator2 as u2

        return u2.connect(serial)
