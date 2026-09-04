"""Side-effect-free scheduler inputs and decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

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


@dataclass(frozen=True, slots=True)
class SchedulerLoopResult:
    """Terminal report for one persistent account-session scheduler loop."""

    cycles: tuple[SchedulerResult, ...]
    session_ended: bool
    initial_dm_executed: bool
