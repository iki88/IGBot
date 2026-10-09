"""Side-effect-free scheduler inputs and decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from IGBot.runtime.modules import InteractionModule
from IGBot.runtime.state import ModuleState


class LimitScope(StrEnum):
    """Supported accounting windows for interaction limits."""

    SESSION = "Session"
    DAILY = "Daily"
    HOURLY = "Hourly"


class ModuleExecutionOutcome(StrEnum):
    """Structured outcomes consumed by the Scheduler Loop."""

    SUCCESS = "SUCCESS"
    NO_CANDIDATES = "NO_CANDIDATES"
    SCROLL_BLOCK = "SCROLL_BLOCK"
    DAILY_LIMIT_REACHED = "DAILY_LIMIT_REACHED"
    ACTION_BLOCK = "ACTION_BLOCK"
    NAVIGATION_FAILED = "NAVIGATION_FAILED"


class ModuleDomainResult(Protocol):
    """Module-specific structured result carried through scheduling."""

    @property
    def status(self) -> str:
        """Return the module-owned outcome identity."""
        ...


@dataclass(frozen=True, slots=True)
class ModuleBudget:
    """Current scheduler budget for one enabled interaction module."""

    module: str
    session_remaining: int
    daily_remaining: int
    hourly_remaining: int
    priority: int = 0


@dataclass(frozen=True, slots=True)
class SchedulingDecision:
    """A strategy decision; execution remains the controller's responsibility."""

    module: str | None
    reason: str


@dataclass(frozen=True, slots=True)
class ExecutionBudget:
    """Resolved and daily-limit-clamped budget for one scheduler cycle."""

    module: InteractionModule
    configured: str
    resolved: int
    daily_remaining: int
    final: int


@dataclass(frozen=True, slots=True)
class ModuleExecutionResult:
    """Provider-neutral outcome returned by a future module executor."""

    execution_started: bool
    execution_finished: bool
    next_module_state: ModuleState
    detail: str | None = None
    outcome: ModuleExecutionOutcome = ModuleExecutionOutcome.SUCCESS
    module_result: ModuleDomainResult | None = None
    verified_successes: int = 0

    def __post_init__(self) -> None:
        if self.verified_successes < 0:
            raise ValueError("verified_successes cannot be negative")


@dataclass(slots=True)
class ModuleOperation:
    """One scheduler-owned module lease with one immutable resolved target."""

    module: InteractionModule
    budget: ExecutionBudget
    verified_successes: int = 0

    @property
    def target(self) -> int:
        return self.budget.final

    @property
    def remaining(self) -> int:
        return max(0, self.target - self.verified_successes)

    @property
    def completed(self) -> bool:
        return self.remaining == 0

    def record(self, count: int) -> None:
        if count < 0:
            raise ValueError("Verified operation progress cannot be negative")
        if count > self.remaining:
            raise ValueError("Verified operation progress exceeded its target")
        self.verified_successes += count

    def remaining_budget(self, daily_remaining: int) -> ExecutionBudget:
        return ExecutionBudget(
            module=self.budget.module,
            configured=self.budget.configured,
            resolved=self.budget.resolved,
            daily_remaining=daily_remaining,
            final=min(self.remaining, daily_remaining),
        )


@dataclass(frozen=True, slots=True)
class SchedulerResult:
    """Observable result of one scheduler framework evaluation."""

    selected_module: InteractionModule | None
    budget: ExecutionBudget | None
    execution_started: bool
    execution_finished: bool
    next_module_state: ModuleState | None
    detail: str | None = None
    outcome: ModuleExecutionOutcome | None = None
    module_result: ModuleDomainResult | None = None
    verified_successes: int = 0


@dataclass(frozen=True, slots=True)
class SchedulerLoopResult:
    """Terminal report for one persistent account-session scheduler loop."""

    cycles: tuple[SchedulerResult, ...]
    session_ended: bool
    initial_dm_executed: bool
