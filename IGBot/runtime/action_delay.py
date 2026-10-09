"""Reusable post-interaction delay handling."""

from __future__ import annotations

import random
import re
import time
from collections.abc import Callable


class ActionDelay:
    """Resolve and wait a configured fixed or ranged delay in seconds."""

    _FIXED = re.compile(r"\d+")
    _RANGE = re.compile(r"(\d+)\s*-\s*(\d+)")

    def __init__(
        self,
        configured: int | str = 0,
        *,
        selector: Callable[[float, float], float] = random.uniform,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.minimum, self.maximum = self.parse(configured)
        self._selector = selector
        self._sleeper = sleeper

    @classmethod
    def parse(cls, configured: int | str) -> tuple[float, float]:
        value = str(configured).strip()
        if cls._FIXED.fullmatch(value):
            seconds = float(value)
            return seconds, seconds
        matched = cls._RANGE.fullmatch(value)
        if matched is None:
            raise ValueError("Action delay must be a non-negative integer or range")
        minimum, maximum = (float(item) for item in matched.groups())
        if minimum > maximum:
            raise ValueError("Minimum action delay cannot exceed maximum action delay")
        return minimum, maximum

    def wait(
        self,
        cancellation_requested: Callable[[], bool] | None = None,
        *,
        cancellation_wait: Callable[[float], bool] | None = None,
    ) -> float:
        seconds = self._selector(self.minimum, self.maximum)
        if seconds <= 0:
            return seconds
        if cancellation_requested is None:
            self._sleeper(seconds)
            return seconds
        if cancellation_wait is not None:
            cancellation_wait(seconds)
            return seconds
        # Test/custom runtimes without an interruptible event retain the
        # established one-shot sleeper behavior.
        self._sleeper(seconds)
        return seconds
