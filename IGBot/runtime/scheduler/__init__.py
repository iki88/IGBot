"""Smart-interaction-scheduler framework and contracts."""

from IGBot.runtime.scheduler.backoff import BackoffPolicy
from IGBot.runtime.scheduler.budget import BudgetCalculator
from IGBot.runtime.scheduler.contracts import (
    BudgetedRuntimeModule,
    DailyLimitManager,
    HourlyLimitManager,
    ModuleExecutor,
    ModuleProvider,
    RotationStrategy,
    SchedulerController,
    SchedulerEntryPoint,
    SessionActivityProvider,
)
from IGBot.runtime.scheduler.execution import ExecutionCoordinator
from IGBot.runtime.scheduler.loop import SchedulerLoop
from IGBot.runtime.scheduler.models import (
    ExecutionBudget,
    LimitScope,
    ModuleBudget,
    ModuleExecutionOutcome,
    ModuleExecutionResult,
    SchedulerLoopResult,
    SchedulerResult,
    SchedulingDecision,
)
from IGBot.runtime.scheduler.pool import ModulePoolBuilder
from IGBot.runtime.scheduler.scheduler import Scheduler
from IGBot.runtime.scheduler.selector import ModuleSelector

__all__ = [
    "BackoffPolicy",
    "BudgetCalculator",
    "BudgetedRuntimeModule",
    "DailyLimitManager",
    "ExecutionBudget",
    "ExecutionCoordinator",
    "HourlyLimitManager",
    "LimitScope",
    "ModuleBudget",
    "ModuleExecutionOutcome",
    "ModuleExecutionResult",
    "ModuleExecutor",
    "ModulePoolBuilder",
    "ModuleProvider",
    "ModuleSelector",
    "RotationStrategy",
    "Scheduler",
    "SchedulerController",
    "SchedulerEntryPoint",
    "SchedulerLoop",
    "SchedulerLoopResult",
    "SchedulerResult",
    "SchedulingDecision",
    "SessionActivityProvider",
]
