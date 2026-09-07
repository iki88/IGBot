"""UIAutomator2 execution provider for Follow navigation and interaction."""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass

from IGBot.runtime.candidates import Candidate
from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.follow.android_models import (
    AndroidFollowResult,
    AndroidFollowStatus,
)
from IGBot.runtime.follow.contracts import ContactScraper
from IGBot.runtime.follow.models import CandidateProfile


@dataclass(frozen=True, slots=True)
class _Node:
    text: str
    description: str
    resource_id: str
    bounds: tuple[int, int, int, int]
    scrollable: bool = False

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
    _FOLLOWER_SEARCH_IDS = ("follow_list_search", "search_edit_text")
    _FOLLOWER_LIST_IDS = ("recycler_view", "follow_list_container")
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

    def __init__(
        self,
        contact_scraper: ContactScraper,
        *,
        device_factory: Callable[[str], object] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        navigation_wait: float = 1.0,
        verification_delay: float = 2.0,
    ) -> None:
        if navigation_wait < 0:
            raise ValueError("Navigation wait cannot be negative")
        if verification_delay < 0:
            raise ValueError("Verification delay cannot be negative")
        self._contact_scraper = contact_scraper
        self._device_factory = device_factory or self._connect
        self._sleeper = sleeper
        self._navigation_wait = navigation_wait
        self._verification_delay = verification_delay

    def locate_source(
        self, context: RuntimeContext, source_username: str
    ) -> AndroidFollowResult:
        """Locate and open an exact source username through Instagram Search."""

        username = source_username.strip()
        if not username:
            return AndroidFollowResult(
                AndroidFollowStatus.SOURCE_NOT_FOUND,
                "Source username cannot be empty.",
            )
        try:
            device = self._device(context)
            search_tab = self._find_navigation(
                self._nodes(device.dump_hierarchy(compressed=False)),
                self._SEARCH_TAB_IDS,
                "search",
            )
            if search_tab is None:
                return self._source_not_found(username, "Search tab is unavailable.")
            self._tap(device, search_tab)

            search_input = self._find_by_id(
                self._fresh_nodes(device), self._SEARCH_INPUT_IDS
            )
            if search_input is None:
                return self._source_not_found(username, "Search input is unavailable.")
            self._tap(device, search_input)
            device.send_keys(username, clear=True)
            self._wait()

            exact = self._exact_username(self._fresh_nodes(device), username)
            if exact is not None:
                self._tap(device, exact)
                return AndroidFollowResult(AndroidFollowStatus.SUCCESS)

            search_action = self._find_text(self._fresh_nodes(device), "search")
            if search_action is None:
                return self._source_not_found(username, "Search action is unavailable.")
            self._tap(device, search_action)

            accounts_tab = self._find_navigation(
                self._fresh_nodes(device), self._ACCOUNTS_TAB_IDS, "accounts"
            )
            if accounts_tab is None:
                return self._source_not_found(username, "Accounts tab is unavailable.")
            self._tap(device, accounts_tab)

            exact = self._exact_username(self._fresh_nodes(device), username)
            if exact is None:
                return self._source_not_found(
                    username, "Exact source username was not found."
                )
            self._tap(device, exact)
            return AndroidFollowResult(AndroidFollowStatus.SUCCESS)
        except Exception as error:  # noqa: BLE001 - Android isolation boundary
            return self._source_not_found(username, f"Source search failed: {error}")

    def open_followers(self, context: RuntimeContext) -> AndroidFollowResult:
        """Open the source profile's Followers list."""

        try:
            device = self._device(context)
            nodes = self._nodes(device.dump_hierarchy(compressed=False))
            followers = self._find_by_id(nodes, self._FOLLOWERS_IDS)
            if followers is None:
                followers = self._find_text(nodes, "followers")
            if followers is None:
                return AndroidFollowResult(
                    AndroidFollowStatus.FOLLOW_FAILED,
                    "Followers control is unavailable.",
                )
            self._tap(device, followers)
            return AndroidFollowResult(AndroidFollowStatus.SUCCESS)
        except Exception as error:  # noqa: BLE001 - Android isolation boundary
            return AndroidFollowResult(
                AndroidFollowStatus.FOLLOW_FAILED,
                f"Opening Followers failed: {error}",
            )

    def show_more_followers(self, context: RuntimeContext) -> AndroidFollowResult:
        """Tap See More when the followers surface exposes it."""

        try:
            device = self._device(context)
            node = self._find_text(self._fresh_nodes(device), "see more")
            if node is None:
                return AndroidFollowResult(AndroidFollowStatus.SUCCESS)
            self._tap(device, node)
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

    def open_candidate_profile(
        self, context: RuntimeContext, candidate: Candidate
    ) -> AndroidFollowResult:
        """Open an exact visible follower and read profile qualification facts."""

        try:
            device = self._device(context)
            exact = self._exact_username(self._fresh_nodes(device), candidate.username)
            if exact is None:
                return AndroidFollowResult(
                    AndroidFollowStatus.FOLLOW_FAILED,
                    f"Candidate is not visible: {candidate.username}",
                )
            self._tap(device, exact)
            nodes = self._fresh_nodes(device)
            username_node = self._find_by_id(nodes, self._PROFILE_USERNAME_IDS)
            observed_username = (
                username_node.text.strip() if username_node is not None else ""
            )
            if observed_username.casefold() != candidate.username.casefold():
                return AndroidFollowResult(
                    AndroidFollowStatus.FOLLOW_FAILED,
                    "Opened profile does not match the selected candidate.",
                )
            name = self._find_by_id(nodes, self._DISPLAY_NAME_IDS)
            biography = self._find_by_id(nodes, self._BIOGRAPHY_IDS)
            profile = CandidateProfile(
                candidate=candidate,
                username=observed_username,
                display_name=name.text.strip() if name is not None else "",
                biography=biography.text.strip() if biography is not None else "",
                is_private=self._is_private(nodes),
            )
            return AndroidFollowResult(AndroidFollowStatus.SUCCESS, profile=profile)
        except Exception as error:  # noqa: BLE001 - Android isolation boundary
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
                return AndroidFollowResult(AndroidFollowStatus.CONTACT_NOT_AVAILABLE)
            self._tap(device, contact)
            try:
                hierarchy = device.dump_hierarchy(compressed=False)
                details = dict(self._contact_scraper.scrape(context, hierarchy))
            finally:
                self._navigate_back(context, device)
            if not self._is_profile_screen(self._fresh_nodes(device)):
                return AndroidFollowResult(
                    AndroidFollowStatus.FOLLOW_FAILED,
                    "Contact popup closed, but the profile screen did not return.",
                )
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
                self._sleeper(self._verification_delay)
                verified = self._button_state(
                    self._follow_button(
                        self._nodes(device.dump_hierarchy(compressed=False))
                    )
                )
                if verified == "following":
                    result = AndroidFollowResult(AndroidFollowStatus.SUCCESS)
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

        return self._navigate_back(context, self._device(context))

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
        return next(
            (
                node
                for node in nodes
                if cls._id_has_suffix(node.resource_id, cls._CONTACT_IDS)
                and cls._button_state(node) == "contact"
            ),
            None,
        ) or cls._find_text(nodes, "contact")

    @classmethod
    def _is_profile_screen(cls, nodes: tuple[_Node, ...]) -> bool:
        return cls._find_by_id(nodes, cls._PROFILE_USERNAME_IDS) is not None

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
