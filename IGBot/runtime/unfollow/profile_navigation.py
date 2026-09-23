"""Shared verified profile restoration for Following-list providers."""

from __future__ import annotations

import time
from collections.abc import Callable

from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.follow import AndroidFollowProvider


class FollowingListProfileRestorer:
    """Return arbitrary Instagram state to the exact account profile."""

    _FOLLOW_LIST_IDS = ("unified_follow_list_view_pager", "follow_list_container")
    _PROFILE_IDS = ("tab_avatar", "profile_tab", "profile_button")

    def __init__(
        self,
        android: AndroidFollowProvider,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        timeout: float = 3.0,
        poll_interval: float = 0.25,
    ) -> None:
        self._android = android
        self._clock = clock
        self._sleeper = sleeper
        self._timeout = timeout
        self._poll_interval = poll_interval

    def ensure_profile_page(self, context: RuntimeContext, device: object) -> bool:
        """Perform at most two verified navigation attempts."""

        expected = context.session.account_username.casefold()
        for attempt in range(2):
            nodes = self._snapshot(device)
            if self._is_profile(nodes, expected):
                return True

            if self._android._find_by_id(nodes, self._FOLLOW_LIST_IDS) is not None:
                device.press("back")
            else:
                profile = self._android._find_navigation(
                    nodes, self._PROFILE_IDS, "profile"
                )
                if profile is not None:
                    self._android._tap(device, profile)
                else:
                    device.press("back")

            if self._wait_for_profile(device, expected):
                return True
            if attempt == 0:
                context.logger.info(
                    "[Following List] Profile not restored. Retrying..."
                )

        context.logger.warning(
            "[Following List] Account profile unavailable. Starting recovery."
        )
        return False

    def _wait_for_profile(self, device: object, expected: str) -> bool:
        deadline = self._clock() + self._timeout
        while self._clock() < deadline:
            if self._is_profile(self._snapshot(device), expected):
                return True
            self._sleeper(self._poll_interval)
        return False

    def _snapshot(self, device: object):
        return self._android._nodes(device.dump_hierarchy(compressed=False))

    def _is_profile(self, nodes, expected: str) -> bool:
        return (
            self._android._profile_username(nodes).casefold() == expected
            and self._android._find_by_id(nodes, self._android._FOLLOWING_IDS)
            is not None
        )
