"""Android execution for sequential Unfollow All Followings."""

from __future__ import annotations

import random
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass

from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.follow import AndroidFollowProvider, AndroidFollowStatus
from IGBot.runtime.unfollow.models import AndroidUnfollowResult, AndroidUnfollowStatus
from IGBot.runtime.unfollow.profile_navigation import FollowingListProfileRestorer


@dataclass(frozen=True, slots=True)
class _FollowingRow:
    username: str
    menu: object | None
    action_state: str


class AndroidFollowingListUnfollowProvider:
    """Walk the account's own Following list and execute verified unfollows."""

    _WAIT_FOR_POPULATED_LIST = True
    _PROFILE_IDS = ("tab_avatar", "profile_tab", "profile_button")
    _LIST_IDS = ("unified_follow_list_view_pager", "list")
    _EMPTY_LIST_IDS = ("empty_state_view_root",)
    _ROW_ID = "follow_list_container"
    _USERNAME_ID = "follow_list_username"
    _MENU_ID = "media_option_button"
    _ACTION_ID = "follow_list_row_large_follow_button"
    _FOLLOWED_STATES = frozenset(("following", "message"))
    _COMPLETED_STATE = "follow"
    _CONTEXT_MENU_IDS = ("context_menu", "context_menu_options_list")
    _CONTEXT_ITEM_ID = "context_menu_item"
    _CONTEXT_LABEL_ID = "context_menu_item_label"
    _DIALOG_IDS = ("dialog_container",)
    _CONFIRM_IDS = ("igds_alert_dialog_primary_button", "primary_button")
    _SORT_BUTTON_IDS = ("sorting_entry_row_icon",)
    _SORT_DIALOG_IDS = (
        "follow_list_sorting_options_fragment_title",
        "follow_list_sorting_options_recycler_view",
    )
    _SORT_OPTION_ID = "follow_list_sorting_option"

    def __init__(
        self,
        android: AndroidFollowProvider,
        *,
        sorting: str = "default",
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        timeout: float = 3.0,
        poll_interval: float = 0.25,
        search_settle_delay: Callable[[], float] = lambda: random.uniform(2.0, 3.0),
        profile_restorer: FollowingListProfileRestorer | None = None,
    ) -> None:
        self._android = android
        self._sorting = sorting
        self._clock = clock
        self._sleeper = sleeper
        self._timeout = timeout
        self._poll_interval = poll_interval
        self._search_settle_delay = search_settle_delay
        self._profile_restorer = profile_restorer or FollowingListProfileRestorer(
            android,
            clock=clock,
            sleeper=sleeper,
            timeout=timeout,
            poll_interval=poll_interval,
        )
        self._opened = False
        self._seen: set[str] = set()
        self._last_visible: tuple[str, ...] = ()
        self._stalled_scrolls = 0

    def execute_next(
        self, context: RuntimeContext, processed: frozenset[str]
    ) -> AndroidUnfollowResult:
        device = self._android._device(context)
        if not self._opened:
            opened = self._open_following_list(context, device)
            if opened is not None:
                return opened
            self._opened = True

        while True:
            hierarchy = device.dump_hierarchy(compressed=False)
            rows = self._rows(hierarchy)
            visible = tuple(row.username.casefold() for row in rows)
            for row in rows:
                key = row.username.casefold()
                if key in processed or key in self._seen:
                    continue
                if row.action_state == self._COMPLETED_STATE:
                    self._seen.add(key)
                    continue
                if row.action_state not in self._FOLLOWED_STATES or row.menu is None:
                    self._seen.add(key)
                    continue
                context.logger.info(
                    "[Following List] Processing username...", username=row.username
                )
                result = self._unfollow_row(context, device, row)
                if result.status is AndroidUnfollowStatus.SUCCESS:
                    self._seen.add(key)
                    refreshed = device.dump_hierarchy(compressed=False)
                    self._last_visible = tuple(
                        candidate.username.casefold()
                        for candidate in self._rows(refreshed)
                    )
                return result

            if visible and visible != self._last_visible:
                self._stalled_scrolls = 0
            else:
                self._stalled_scrolls += 1
            self._last_visible = visible
            if self._stalled_scrolls >= 2:
                return AndroidUnfollowResult(
                    AndroidUnfollowStatus.NO_CANDIDATES,
                    "End of Following list reached.",
                )
            context.logger.info("[Following List] Scrolling...")
            scrolled = self._android.scroll_following_list(context)
            if scrolled.status is not AndroidFollowStatus.SUCCESS:
                return AndroidUnfollowResult(
                    AndroidUnfollowStatus.NO_CANDIDATES,
                    "End of Following list reached.",
                )

    def _open_following_list(
        self, context: RuntimeContext, device: object
    ) -> AndroidUnfollowResult | None:
        context.logger.info("[Following List] Opening Following list...")
        if not self._profile_restorer.ensure_profile_page(context, device):
            return AndroidUnfollowResult(
                AndroidUnfollowStatus.NAVIGATION_FAILED,
                "Account profile could not be restored before opening Following.",
            )
        following = self._wait_for_node(
            device,
            lambda current: self._android._find_by_id(
                current, self._android._FOLLOWING_IDS
            )
            or self._android._find_text(current, "following"),
        )
        if following is None:
            return AndroidUnfollowResult(
                AndroidUnfollowStatus.NAVIGATION_FAILED,
                "Own profile Following control is unavailable.",
            )
        self._android._tap(device, following)
        if self._wait_for_node(device, self._following_list) is None:
            return AndroidUnfollowResult(
                AndroidUnfollowStatus.NAVIGATION_FAILED,
                "Following list did not open.",
            )
        if self._sorting != "default":
            self._apply_sorting(context, device)
        if self._WAIT_FOR_POPULATED_LIST:
            context.logger.info("[Following List] Waiting for Following list...")
            ready = None
            for _attempt in range(2):
                ready = self._wait_for_node(device, self._following_list_ready)
                if ready is not None:
                    break
            if ready is None:
                return AndroidUnfollowResult(
                    AndroidUnfollowStatus.NAVIGATION_FAILED,
                    "Following list did not finish loading.",
                )
            context.logger.info("[Following List] Following list loaded.")
        if self._sorting == "default":
            self._apply_sorting(context, device)
        if self._WAIT_FOR_POPULATED_LIST:
            context.logger.info("[Following List] Beginning processing...")
        return None

    def _apply_sorting(self, context: RuntimeContext, device: object) -> None:
        if self._sorting == "default":
            context.logger.info("[Following List] Using default sorting.")
            return
        label = (
            "Date followed: Latest"
            if self._sorting == "latest"
            else "Date followed: Earliest"
        )
        context.logger.info(f"[Following List] Applying sorting: {label}")
        for attempt in range(2):
            button = self._wait_for_node(
                device,
                lambda nodes: self._android._find_by_id(nodes, self._SORT_BUTTON_IDS),
            )
            if button is not None:
                self._android._tap(device, button)
            dialog = self._wait_for_node(
                device,
                lambda nodes: self._android._find_by_id(nodes, self._SORT_DIALOG_IDS),
            )
            if dialog is not None:
                break
            if attempt == 1:
                context.logger.warning(
                    "[Following List] Sort dialog unavailable. Using current "
                    "Instagram sorting."
                )
                return
        option = self._wait_for_node(
            device, lambda nodes: self._sort_option(nodes, label)
        )
        if option is None:
            context.logger.warning(
                "[Following List] Unable to verify sorting. Continuing with current "
                "sorting."
            )
            return
        self._android._tap(device, option)
        if (
            self._wait_for_node(
                device, lambda nodes: self._sorting_indicator(nodes, label)
            )
            is None
        ):
            context.logger.warning(
                "[Following List] Unable to verify sorting. Continuing with current "
                "sorting."
            )

    def _unfollow_row(
        self, context: RuntimeContext, device: object, row: _FollowingRow
    ) -> AndroidUnfollowResult:
        context.logger.info("[Unfollow] Opening menu...")
        menu_open = False
        for attempt in range(2):
            self._android._tap(device, row.menu)
            menu_open = (
                self._wait_for_node(
                    device,
                    lambda nodes: self._android._find_by_id(
                        nodes, self._CONTEXT_MENU_IDS
                    ),
                )
                is not None
            )
            if menu_open:
                break
            if attempt == 0:
                context.logger.info("[Unfollow] Menu not detected. Retrying...")
        if not menu_open:
            context.logger.warning("[Unfollow] Menu unavailable. Starting recovery.")
            return AndroidUnfollowResult(
                AndroidUnfollowStatus.VERIFICATION_FAILED,
                "Following-list context menu did not open.",
                row.username,
            )
        unfollow = self._wait_for_node(device, self._unfollow_menu_item)
        if unfollow is None:
            return AndroidUnfollowResult(
                AndroidUnfollowStatus.VERIFICATION_FAILED,
                "Unfollow menu item is unavailable.",
                row.username,
            )
        self._android._tap(device, unfollow)
        context.logger.info("[Unfollow] Waiting for verification...")
        confirmation_tapped = False
        deadline = self._clock() + self._timeout
        while self._clock() < deadline:
            hierarchy = device.dump_hierarchy(compressed=False)
            nodes = self._android._nodes(hierarchy)
            if not confirmation_tapped and self._android._find_by_id(
                nodes, self._DIALOG_IDS
            ):
                confirm = self._android._find_by_id(nodes, self._CONFIRM_IDS)
                if (
                    confirm is not None
                    and confirm.text.strip().casefold() == "unfollow"
                ):
                    context.logger.info("[Unfollow] Confirmation dialog detected.")
                    self._android._tap(device, confirm)
                    confirmation_tapped = True
                    continue
            if self._row_action_state(hierarchy, row.username) == self._COMPLETED_STATE:
                context.logger.info("[Unfollow] Unfollow confirmed.")
                return AndroidUnfollowResult(
                    AndroidUnfollowStatus.SUCCESS, username=row.username
                )
            self._sleeper(self._poll_interval)
        return AndroidUnfollowResult(
            AndroidUnfollowStatus.VERIFICATION_FAILED,
            "Following-list row did not transition to Follow before timeout.",
            row.username,
        )

    def _wait_for_node(self, device: object, finder):
        deadline = self._clock() + self._timeout
        while self._clock() < deadline:
            node = finder(self._snapshot(device))
            if node is not None:
                return node
            self._sleeper(self._poll_interval)
        return None

    def _snapshot(self, device: object):
        return self._android._nodes(device.dump_hierarchy(compressed=False))

    def _following_list(self, nodes):
        list_node = self._android._find_by_id(nodes, self._LIST_IDS)
        following = next(
            (
                node
                for node in nodes
                if self._android._id_has_suffix(node.resource_id, ("title",))
                and "following" in node.text.casefold()
            ),
            None,
        )
        return list_node if list_node is not None and following is not None else None

    def _following_list_ready(self, nodes):
        list_node = self._following_list(nodes)
        if list_node is None:
            return None
        has_row = self._android._find_by_id(nodes, (self._ROW_ID,)) is not None
        has_username = (
            self._android._find_by_id(nodes, (self._USERNAME_ID,)) is not None
        )
        empty_state = self._android._find_by_id(nodes, self._EMPTY_LIST_IDS)
        if (has_row and has_username) or empty_state is not None:
            return list_node
        return None

    def _sort_option(self, nodes, label: str):
        return next(
            (
                node
                for node in nodes
                if self._android._id_has_suffix(
                    node.resource_id, (self._SORT_OPTION_ID,)
                )
                and node.text.strip().casefold() == label.casefold()
            ),
            None,
        )

    def _sorting_indicator(self, nodes, label: str):
        expected = label.casefold()
        header = next(
            (
                node
                for node in nodes
                if self._android._id_has_suffix(
                    node.resource_id, ("sorting_entry_row_option",)
                )
                and expected in node.text.casefold()
            ),
            None,
        )
        if header is not None:
            return header
        for index, node in enumerate(nodes):
            if not (
                self._android._id_has_suffix(node.resource_id, (self._SORT_OPTION_ID,))
                and node.text.strip().casefold() == expected
            ):
                continue
            return next(
                (
                    candidate
                    for candidate in nodes[index + 1 :]
                    if self._android._id_has_suffix(
                        candidate.resource_id,
                        ("follow_list_sorting_option_radio_button",),
                    )
                    and candidate.checked
                ),
                None,
            )
        return None

    def _unfollow_menu_item(self, nodes):
        labelled = next(
            (
                node
                for node in nodes
                if self._android._id_has_suffix(
                    node.resource_id, (self._CONTEXT_LABEL_ID,)
                )
                and node.text.strip().casefold() == "unfollow"
            ),
            None,
        )
        if labelled is None:
            return None
        return next(
            (
                node
                for node in nodes
                if self._android._id_has_suffix(
                    node.resource_id, (self._CONTEXT_ITEM_ID,)
                )
                and (
                    node.description.strip().casefold() == "unfollow"
                    or self._android._contains(node, labelled)
                )
            ),
            labelled,
        )

    @classmethod
    def _rows(cls, hierarchy: str) -> tuple[_FollowingRow, ...]:
        root = ET.fromstring(hierarchy)
        rows = []
        for element in root.iter("node"):
            if cls._suffix(element) != cls._ROW_ID:
                continue
            username = next(
                (
                    child.get("text", "").strip()
                    for child in element.iter("node")
                    if cls._suffix(child) == cls._USERNAME_ID
                    and child.get("text", "").strip()
                ),
                "",
            )
            if not username:
                continue
            menu_element = next(
                (
                    child
                    for child in element.iter("node")
                    if cls._suffix(child) == cls._MENU_ID
                ),
                None,
            )
            menu = None
            if menu_element is not None:
                parsed = AndroidFollowProvider._nodes(
                    ET.tostring(menu_element, encoding="unicode")
                )
                menu = parsed[0] if parsed else None
            action_state = next(
                (
                    child.get("text", "").strip().casefold()
                    for child in element.iter("node")
                    if cls._suffix(child) == cls._ACTION_ID
                    and child.get("text", "").strip()
                ),
                "",
            )
            rows.append(_FollowingRow(username, menu, action_state))
        return tuple(rows)

    @classmethod
    def _row_action_state(cls, hierarchy: str, username: str) -> str | None:
        expected = username.casefold()
        return next(
            (
                row.action_state
                for row in cls._rows(hierarchy)
                if row.username.casefold() == expected
            ),
            None,
        )

    @classmethod
    def _username_visible(cls, nodes, username: str) -> bool:
        expected = username.casefold()
        return any(
            AndroidFollowProvider._id_has_suffix(node.resource_id, (cls._USERNAME_ID,))
            and node.text.strip().casefold() == expected
            for node in nodes
        )

    @staticmethod
    def _suffix(element: ET.Element) -> str:
        return element.get("resource-id", "").rsplit("/", 1)[-1].casefold()
