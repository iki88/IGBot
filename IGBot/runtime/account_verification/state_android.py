"""UIAutomator2 recovery from arbitrary Instagram screens to own Profile."""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass

from IGBot.runtime.context import RuntimeContext


@dataclass(frozen=True, slots=True)
class _Node:
    description: str
    resource_id: str
    bounds: tuple[int, int, int, int]

    @property
    def center(self) -> tuple[int, int]:
        left, top, right, bottom = self.bounds
        return ((left + right) // 2, (top + bottom) // 2)


class AndroidInstagramStateProvider:
    """Use bounded Back navigation and the Profile tab to establish known state."""

    _BOUNDS = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")
    _PROFILE_IDS = ("tab_avatar", "profile_tab", "profile_button")
    _HEADER_IDS = (
        "profile_header_username",
        "profile_header_user_name",
        "action_bar_title",
        "profile_username",
    )

    def __init__(
        self,
        *,
        device_factory: Callable[[str], object] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        attempts: int = 6,
        navigation_wait: float = 1.0,
    ) -> None:
        if attempts <= 0:
            raise ValueError("Recovery attempts must be positive")
        if navigation_wait < 0:
            raise ValueError("Navigation wait cannot be negative")
        self._device_factory = device_factory or self._connect
        self._sleeper = sleeper
        self._attempts = attempts
        self._navigation_wait = navigation_wait

    def recover(self, context: RuntimeContext) -> bool:
        device = self._device_factory(context.session.phone_id)
        for attempt in range(1, self._attempts + 1):
            context.logger.debug("Inspecting Instagram startup state", attempt=attempt)
            nodes = self._nodes(device.dump_hierarchy(compressed=False))
            profile = self._find(nodes, self._PROFILE_IDS, "profile")
            if profile is not None:
                context.logger.info("Opening own Instagram Profile", attempt=attempt)
                device.click(*profile.center)
                self._sleeper(self._navigation_wait)
                profile_nodes = self._nodes(device.dump_hierarchy(compressed=False))
                if self._find(profile_nodes, self._HEADER_IDS) is not None:
                    return True
            context.logger.debug(
                "Known startup state unavailable; navigating Back", attempt=attempt
            )
            device.press("back")
            self._sleeper(self._navigation_wait)
        return False

    @classmethod
    def _nodes(cls, hierarchy: str) -> tuple[_Node, ...]:
        root = ET.fromstring(hierarchy)
        nodes = []
        for element in root.iter("node"):
            bounds = cls._BOUNDS.fullmatch(element.get("bounds", ""))
            if bounds is None:
                continue
            nodes.append(
                _Node(
                    description=element.get("content-desc", ""),
                    resource_id=element.get("resource-id", ""),
                    bounds=tuple(int(value) for value in bounds.groups()),
                )
            )
        return tuple(nodes)

    @staticmethod
    def _find(
        nodes: tuple[_Node, ...], identifiers: tuple[str, ...], label: str = ""
    ) -> _Node | None:
        return next(
            (
                node
                for node in nodes
                if node.resource_id.rsplit("/", 1)[-1].casefold() in identifiers
                or (label and node.description.strip().casefold() == label)
            ),
            None,
        )

    @staticmethod
    def _connect(serial: str) -> object:
        import uiautomator2 as u2

        return u2.connect(serial)
