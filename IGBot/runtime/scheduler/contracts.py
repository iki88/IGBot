"""Contracts for selection, limits, and scheduler lifecycle."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.scheduler.models import ModuleBudget, SchedulingDecision


class SchedulerEntryPoint(Protocol):
    """Boundary through which a completed startup enters scheduling."""

    def start(self, context: RuntimeContext) -> None:
        """Accept control through the shared session context."""
        ...


class RotationStrategy(Protocol):
    """Choose the next eligible module from immutable budget inputs."""

    def select(
        self, context: RuntimeContext, budgets: Sequence[ModuleBudget]
    ) -> SchedulingDecision:
        """Return the next scheduling decision."""
        ...


class DailyLimitManager(Protocol):
    """Read and account for per-account daily module limits."""

    def remaining(self, context: RuntimeContext, module: str) -> int:
        """Return the remaining daily budget."""
        ...


class HourlyLimitManager(Protocol):
    """Read and account for global hourly module limits."""

    def remaining(self, context: RuntimeContext, module: str) -> int:
        """Return the remaining global hourly budget."""
        ...


class SchedulerController(SchedulerEntryPoint, Protocol):
    """Own module rotation for one account session."""

    def run(self, context: RuntimeContext) -> None:
        """Run scheduler decisions until the session ends or is stopped."""
        ...

    def request_stop(self, context: RuntimeContext) -> None:
        """Request an orderly scheduler stop."""
        ...
