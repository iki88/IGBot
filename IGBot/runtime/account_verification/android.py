"""UIAutomator2 Instagram profile-provider implementation."""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass

from IGBot.runtime.account_verification.models import (
    ProfileObservation,
    ProfileObservationState,
    UsernameDetectionResult,
)
from IGBot.runtime.context import RuntimeContext


@dataclass(frozen=True, slots=True)
class _Node:
    text: str
    description: str
    resource_id: str
    bounds: tuple[int, int, int, int]

    @property
    def center(self) -> tuple[int, int]:
        left, top, right, bottom = self.bounds
        return ((left + right) // 2, (top + bottom) // 2)


class AndroidInstagramProfileProvider:
    """Support current and Instagram 372 profile identity workflows."""

    _BOUNDS_PATTERN = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")
    _USERNAME_PATTERN = re.compile(r"[A-Za-z0-9._]{1,30}")
    _TRUNCATED_PATTERN = re.compile(r"(?:\.\.\.|…)")
    _PROFILE_IDS = ("tab_avatar", "profile_tab", "profile_button")
    _HEADER_IDS = (
        "profile_header_username",
        "profile_header_user_name",
        "action_bar_title",
        "profile_username",
    )
    _SWITCHER_IDS = (
        "account_switcher_username",
        "row_user_primary_name",
        "igds_textcell_title",
        "account_username",
    )

    def __init__(
        self,
        *,
        device_factory: Callable[[str], object] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        navigation_wait: float = 2.0,
    ) -> None:
        self._device_factory = device_factory or self._connect
        self._sleeper = sleeper
        self._navigation_wait = navigation_wait
        self._profile_headers: dict[str, _Node] = {}

    def open_profile(self, context: RuntimeContext) -> ProfileObservation:
        """Open Profile and read a complete or explicitly truncated header."""
        try:
            device = self._device_factory(context.session.phone_id)
            nodes = self._nodes(device.dump_hierarchy(compressed=False))
            profile = self._profile_tab(nodes)
            if profile is None:
                return ProfileObservation(
                    ProfileObservationState.PROFILE_NOT_AVAILABLE,
                    detail="Instagram Profile navigation is not available.",
                )
            device.click(*profile.center)
            self._sleeper(self._navigation_wait)
            nodes = self._nodes(device.dump_hierarchy(compressed=False))
            header = self._profile_header(nodes)
            if header is None:
                return ProfileObservation(
                    ProfileObservationState.PROFILE_NOT_LOADED,
                    detail="Instagram Profile did not expose a username.",
                )
            username = header.text.strip()
            if self._TRUNCATED_PATTERN.search(username):
                self._profile_headers[context.session.phone_id] = header
                return ProfileObservation(
                    ProfileObservationState.USERNAME_TRUNCATED,
                    username=username,
                )
            self._profile_headers.pop(context.session.phone_id, None)
            return ProfileObservation(
                ProfileObservationState.USERNAME_VISIBLE,
                username=username,
            )
        except Exception as error:  # noqa: BLE001 - platform isolation boundary
            return ProfileObservation(
                ProfileObservationState.PROFILE_NOT_LOADED,
                detail=f"Instagram Profile inspection failed: {error}",
            )

    def complete_username_from_switcher(
        self, context: RuntimeContext
    ) -> UsernameDetectionResult:
        """Open Account Switcher, read its selected account, and always close it."""
        header = self._profile_headers.get(context.session.phone_id)
        if header is None:
            return UsernameDetectionResult(
                detail="The truncated Profile username is no longer available."
            )
        try:
            device = self._device_factory(context.session.phone_id)
            device.click(*header.center)
            self._sleeper(self._navigation_wait)
            try:
                nodes = self._nodes(device.dump_hierarchy(compressed=False))
                username = self._switcher_username(nodes)
                if username is None:
                    return UsernameDetectionResult(
                        detail="Account Switcher did not expose a complete username."
                    )
                return UsernameDetectionResult(username=username)
            finally:
                device.press("back")
        except Exception as error:  # noqa: BLE001 - platform isolation boundary
            return UsernameDetectionResult(
                detail=f"Account Switcher inspection failed: {error}"
            )
        finally:
            self._profile_headers.pop(context.session.phone_id, None)

    def _profile_tab(self, nodes: tuple[_Node, ...]) -> _Node | None:
        return next(
            (
                node
                for node in nodes
                if self._id_has_suffix(node.resource_id, self._PROFILE_IDS)
                or node.description.strip().casefold() == "profile"
            ),
            None,
        )

    def _profile_header(self, nodes: tuple[_Node, ...]) -> _Node | None:
        candidates = tuple(node for node in nodes if self._username_like(node.text))
        identified = next(
            (
                node
                for node in candidates
                if self._id_has_suffix(node.resource_id, self._HEADER_IDS)
            ),
            None,
        )
        if identified is not None:
            return identified
        screen_bottom = max((node.bounds[3] for node in nodes), default=0)
        return next(
            (
                node
                for node in candidates
                if screen_bottom and node.bounds[1] <= screen_bottom * 0.2
            ),
            None,
        )

    def _switcher_username(self, nodes: tuple[_Node, ...]) -> str | None:
        candidates = tuple(
            node
            for node in nodes
            if self._username_like(node.text)
            and self._TRUNCATED_PATTERN.search(node.text) is None
        )
        identified = next(
            (
                node
                for node in candidates
                if self._id_has_suffix(node.resource_id, self._SWITCHER_IDS)
            ),
            None,
        )
        if identified is not None:
            return identified.text.strip()
        screen_bottom = max((node.bounds[3] for node in nodes), default=0)
        fallback = next(
            (
                node
                for node in candidates
                if screen_bottom and node.bounds[1] >= screen_bottom * 0.45
            ),
            None,
        )
        return fallback.text.strip() if fallback is not None else None

    @classmethod
    def _nodes(cls, hierarchy: str) -> tuple[_Node, ...]:
        root = ET.fromstring(hierarchy)
        nodes: list[_Node] = []
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
                )
            )
        return tuple(nodes)

    @classmethod
    def _username_like(cls, value: str) -> bool:
        stripped = cls._TRUNCATED_PATTERN.sub("", value.strip())
        return bool(stripped) and cls._USERNAME_PATTERN.fullmatch(stripped) is not None

    @staticmethod
    def _id_has_suffix(resource_id: str, suffixes: tuple[str, ...]) -> bool:
        identifier = resource_id.rsplit("/", 1)[-1].casefold()
        return identifier in suffixes

    @staticmethod
    def _connect(serial: str) -> object:
        import uiautomator2 as u2

        return u2.connect(serial)
