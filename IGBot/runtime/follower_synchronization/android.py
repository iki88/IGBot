"""UIAutomator2 follower-list reader using stable Instagram resource IDs."""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass

from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.follower_synchronization.models import FollowerReadResult


@dataclass(frozen=True, slots=True)
class _Node:
    text: str
    resource_id: str
    bounds: tuple[int, int, int, int]
    scrollable: bool

    @property
    def center(self) -> tuple[int, int]:
        left, top, right, bottom = self.bounds
        return ((left + right) // 2, (top + bottom) // 2)


class AndroidFollowerReader:
    """Navigate to Followers and read complete usernames without OCR."""

    _BOUNDS_PATTERN = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")
    _USERNAME_PATTERN = re.compile(r"[A-Za-z0-9._]{1,30}")
    _PROFILE_IDS = ("tab_avatar", "profile_tab", "profile_button")
    _FOLLOWERS_IDS = (
        "row_profile_header_followers_container",
        "row_profile_header_container_followers",
        "profile_header_followers_stacked_familiar",
    )
    _USERNAME_IDS = (
        "follow_list_username",
        "row_user_primary_name",
        "row_user_textview",
        "username_textview",
    )
    _SCROLL_IDS = ("recycler_view", "follow_list_container")

    def __init__(
        self,
        *,
        device_factory: Callable[[str], object] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        navigation_wait: float = 2.0,
        scroll_wait: float = 1.0,
    ) -> None:
        self._device_factory = device_factory or self._connect
        self._sleeper = sleeper
        self._navigation_wait = navigation_wait
        self._scroll_wait = scroll_wait

    def read(self, context: RuntimeContext, limit: int) -> FollowerReadResult:
        """Open Followers and return at most the configured number of usernames."""

        if limit <= 0:
            raise ValueError("Follower synchronization limit must be positive")
        try:
            device = self._device_factory(context.session.phone_id)
            nodes = self._nodes(device.dump_hierarchy(compressed=False))
            profile = self._find(nodes, self._PROFILE_IDS)
            if profile is None:
                return FollowerReadResult(False, detail="Profile is not available.")
            device.click(*profile.center)
            self._sleeper(self._navigation_wait)

            nodes = self._nodes(device.dump_hierarchy(compressed=False))
            followers = self._find(nodes, self._FOLLOWERS_IDS)
            if followers is None:
                return FollowerReadResult(
                    False, detail="Followers list is not available."
                )
            device.click(*followers.center)
            self._sleeper(self._navigation_wait)
            return self._read_list(device, limit)
        except Exception as error:  # noqa: BLE001 - platform isolation boundary
            return FollowerReadResult(
                False, detail=f"Follower list inspection failed: {error}"
            )

    def _read_list(self, device: object, limit: int) -> FollowerReadResult:
        usernames: list[str] = []
        seen: set[str] = set()
        while len(usernames) < limit:
            nodes = self._nodes(device.dump_hierarchy(compressed=False))
            added = False
            for node in nodes:
                if not self._id_has_suffix(node.resource_id, self._USERNAME_IDS):
                    continue
                username = node.text.strip()
                normalized = username.casefold()
                if (
                    self._USERNAME_PATTERN.fullmatch(username) is None
                    or "..." in username
                    or "…" in username
                    or normalized in seen
                ):
                    continue
                seen.add(normalized)
                usernames.append(username)
                added = True
                if len(usernames) == limit:
                    return FollowerReadResult(
                        True, tuple(usernames), limit_reached=True
                    )

            scrollable = self._scrollable(nodes)
            if scrollable is None or not added:
                break
            self._swipe(device, scrollable)
            self._sleeper(self._scroll_wait)
        return FollowerReadResult(True, tuple(usernames), limit_reached=False)

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
                    resource_id=element.get("resource-id", ""),
                    bounds=tuple(int(value) for value in bounds.groups()),
                    scrollable=element.get("scrollable", "false") == "true",
                )
            )
        return tuple(nodes)

    @classmethod
    def _find(
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
    def _scrollable(cls, nodes: tuple[_Node, ...]) -> _Node | None:
        return next(
            (
                node
                for node in nodes
                if node.scrollable
                or cls._id_has_suffix(node.resource_id, cls._SCROLL_IDS)
            ),
            None,
        )

    @staticmethod
    def _swipe(device: object, container: _Node) -> None:
        left, top, right, bottom = container.bounds
        x = (left + right) // 2
        device.swipe(x, bottom - 1, x, top + 1, duration=0.4)

    @staticmethod
    def _id_has_suffix(resource_id: str, suffixes: tuple[str, ...]) -> bool:
        return resource_id.rsplit("/", 1)[-1].casefold() in suffixes

    @staticmethod
    def _connect(serial: str) -> object:
        import uiautomator2 as u2

        return u2.connect(serial)
