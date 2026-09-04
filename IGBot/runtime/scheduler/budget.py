"""Fixed/ranged execution-budget calculation."""

from __future__ import annotations

import random
import re
from collections.abc import Callable

from IGBot.runtime.scheduler.contracts import BudgetedRuntimeModule
from IGBot.runtime.scheduler.models import ExecutionBudget


class BudgetCalculator:
    """Resolve a module budget and clamp it to its daily allowance."""

    _FIXED = re.compile(r"\d+")
    _RANGE = re.compile(r"(\d+)\s*-\s*(\d+)")

    def __init__(self, randint: Callable[[int, int], int] = random.randint) -> None:
        self._randint = randint

    def calculate(self, module: BudgetedRuntimeModule) -> ExecutionBudget:
        configured = str(module.budget_configuration).strip()
        resolved = self._resolve(configured)
        daily_remaining = module.daily_remaining
        if (
            isinstance(daily_remaining, bool)
            or not isinstance(daily_remaining, int)
            or daily_remaining < 0
        ):
            raise ValueError("daily_remaining must be a non-negative integer")
        return ExecutionBudget(
            module=module.module,
            configured=configured,
            resolved=resolved,
            daily_remaining=daily_remaining,
            final=min(resolved, daily_remaining),
        )

    def _resolve(self, configured: str) -> int:
        if self._FIXED.fullmatch(configured):
            value = int(configured)
            if value > 0:
                return value
        matched = self._RANGE.fullmatch(configured)
        if matched is not None:
            minimum, maximum = (int(value) for value in matched.groups())
            if minimum > 0 and minimum <= maximum:
                return self._randint(minimum, maximum)
        raise ValueError("Module budget must be a positive integer or range")
