"""Execution coordination boundary for selected modules."""

from __future__ import annotations

from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.scheduler.contracts import BudgetedRuntimeModule, ModuleExecutor
from IGBot.runtime.scheduler.models import ExecutionBudget, ModuleExecutionResult


class ExecutionCoordinator:
    """Delegate one selected, budgeted module to an injected executor."""

    def __init__(self, executor: ModuleExecutor) -> None:
        self._executor = executor

    def coordinate(
        self,
        context: RuntimeContext,
        module: BudgetedRuntimeModule,
        budget: ExecutionBudget,
    ) -> ModuleExecutionResult:
        if budget.final <= 0:
            raise ValueError("Execution budget must be positive")
        result = self._executor.execute(context, module, budget)
        if not isinstance(result, ModuleExecutionResult):
            raise TypeError("ModuleExecutor must return ModuleExecutionResult")
        return result
