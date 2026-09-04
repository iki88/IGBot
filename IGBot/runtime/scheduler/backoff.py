"""Scheduler-owned backoff-duration policy."""

from __future__ import annotations

import random
from collections.abc import Callable
from datetime import datetime, timedelta

from IGBot.runtime.scheduler.models import ModuleExecutionOutcome


class BackoffPolicy:
    """Map temporary execution outcomes to scheduler backoff boundaries."""

    def __init__(self, randint: Callable[[int, int], int] = random.randint) -> None:
        self._randint = randint

    def backoff_until(
        self,
        outcome: ModuleExecutionOutcome,
        current_time: datetime,
    ) -> datetime | None:
        if outcome is ModuleExecutionOutcome.NO_CANDIDATES:
            return current_time + timedelta(minutes=self._randint(15, 20))
        if outcome is ModuleExecutionOutcome.SCROLL_BLOCK:
            return current_time + timedelta(minutes=60)
        return None
