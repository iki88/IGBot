"""Single-cycle Smart Interaction Scheduler framework."""

from __future__ import annotations

from collections.abc import Iterable
from typing import cast

from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.scheduler.budget import BudgetCalculator
from IGBot.runtime.scheduler.contracts import BudgetedRuntimeModule
from IGBot.runtime.scheduler.execution import ExecutionCoordinator
from IGBot.runtime.scheduler.models import SchedulerResult
from IGBot.runtime.scheduler.pool import ModulePoolBuilder
from IGBot.runtime.scheduler.selector import ModuleSelector


class Scheduler:
    """Coordinate one framework cycle without implementing a scheduling loop."""

    def __init__(
        self,
        pool_builder: ModulePoolBuilder,
        selector: ModuleSelector,
        budget_calculator: BudgetCalculator,
        execution_coordinator: ExecutionCoordinator,
    ) -> None:
        self._pool_builder = pool_builder
        self._selector = selector
        self._budget_calculator = budget_calculator
        self._execution_coordinator = execution_coordinator

    def evaluate_once(
        self,
        context: RuntimeContext,
        modules: Iterable[BudgetedRuntimeModule],
    ) -> SchedulerResult:
        """Select, budget, and coordinate at most one eligible module."""

        pool = self._pool_builder.build(modules)
        selected = self._selector.select(pool)
        if selected is None:
            return SchedulerResult(
                selected_module=None,
                budget=None,
                execution_started=False,
                execution_finished=False,
                next_module_state=None,
                detail="No eligible modules.",
            )

        selected = cast(BudgetedRuntimeModule, selected)
        budget = self._budget_calculator.calculate(selected)
        if budget.final == 0:
            return SchedulerResult(
                selected_module=selected.module,
                budget=budget,
                execution_started=False,
                execution_finished=False,
                next_module_state=selected.state,
                detail="Daily limit reached.",
            )

        execution = self._execution_coordinator.coordinate(context, selected, budget)
        return SchedulerResult(
            selected_module=selected.module,
            budget=budget,
            execution_started=execution.execution_started,
            execution_finished=execution.execution_finished,
            next_module_state=execution.next_module_state,
            detail=execution.detail,
        )
