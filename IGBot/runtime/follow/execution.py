"""Execution adapter connecting one Follow Module to the scheduler contract."""

from __future__ import annotations

from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.follow.module import FollowModule
from IGBot.runtime.scheduler import (
    BudgetedRuntimeModule,
    ExecutionBudget,
    ModuleExecutionResult,
)


class FollowModuleExecutor:
    """Delegate scheduler execution only to its injected Follow Module."""

    def __init__(self, follow_module: FollowModule) -> None:
        self._follow_module = follow_module

    def execute(
        self,
        context: RuntimeContext,
        module: BudgetedRuntimeModule,
        budget: ExecutionBudget,
    ) -> ModuleExecutionResult:
        """Execute Follow preparation through the common module boundary."""

        if module is not self._follow_module:
            raise ValueError("FollowModuleExecutor received an unknown module")
        return self._follow_module.execute(context, budget)
