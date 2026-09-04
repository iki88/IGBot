"""Smart-interaction-scheduler framework and contracts."""

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
)
from IGBot.runtime.scheduler.execution import ExecutionCoordinator
from IGBot.runtime.scheduler.models import (
    ExecutionBudget,
    LimitScope,
    ModuleBudget,
    ModuleExecutionResult,
    SchedulerResult,
    SchedulingDecision,
)
from IGBot.runtime.scheduler.pool import ModulePoolBuilder
from IGBot.runtime.scheduler.scheduler import Scheduler
from IGBot.runtime.scheduler.selector import ModuleSelector

__all__ = [
    "BudgetCalculator",
    "BudgetedRuntimeModule",
    "DailyLimitManager",
    "ExecutionBudget",
    "ExecutionCoordinator",
    "HourlyLimitManager",
    "LimitScope",
    "ModuleBudget",
    "ModuleExecutionResult",
    "ModuleExecutor",
    "ModulePoolBuilder",
    "ModuleProvider",
    "ModuleSelector",
    "RotationStrategy",
    "Scheduler",
    "SchedulerController",
    "SchedulerEntryPoint",
    "SchedulerResult",
    "SchedulingDecision",
]
