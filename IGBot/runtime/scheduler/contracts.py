"""Contracts for selection, limits, and scheduler lifecycle."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Protocol

from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.modules import RuntimeModule
from IGBot.runtime.scheduler.models import (
    ExecutionBudget,
    ModuleBudget,
    ModuleExecutionResult,
    SchedulingDecision,
)


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


class BudgetedRuntimeModule(RuntimeModule, Protocol):
    """Scheduler inputs exposed uniformly by an interaction module."""

    @property
    def budget_configuration(self) -> int | str:
        """Return a fixed budget or inclusive range expression."""
        ...

    @property
    def daily_remaining(self) -> int:
        """Return the authoritative remaining daily allowance."""
        ...


class ModuleProvider(Protocol):
    """Supply modules belonging to the current RuntimeContext."""

    def modules_for(self, context: RuntimeContext) -> Iterable[BudgetedRuntimeModule]:
        """Return the session's interaction modules."""
        ...


class ModuleExecutor(Protocol):
    """Future execution boundary consumed by ExecutionCoordinator."""

    def execute(
        self,
        context: RuntimeContext,
        module: BudgetedRuntimeModule,
        budget: ExecutionBudget,
    ) -> ModuleExecutionResult:
        """Execute an already selected module through its provider."""
        ...
