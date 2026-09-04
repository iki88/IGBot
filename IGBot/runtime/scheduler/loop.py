"""Persistent Smart Interaction Scheduler execution loop."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone

from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.modules import InteractionModule
from IGBot.runtime.recovery import FailureKind, RecoveryController, RecoveryRequest
from IGBot.runtime.scheduler.backoff import BackoffPolicy
from IGBot.runtime.scheduler.contracts import (
    BudgetedRuntimeModule,
    ModuleProvider,
    SessionActivityProvider,
)
from IGBot.runtime.scheduler.models import (
    ModuleExecutionOutcome,
    SchedulerLoopResult,
    SchedulerResult,
)
from IGBot.runtime.scheduler.scheduler import Scheduler
from IGBot.runtime.state import ModuleState


class SchedulerLoop:
    """Repeat bounded scheduler cycles while SessionController reports active."""

    def __init__(
        self,
        scheduler: Scheduler,
        module_provider: ModuleProvider,
        session_activity: SessionActivityProvider,
        backoff_policy: BackoffPolicy,
        recovery: RecoveryController,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        sleeper: Callable[[float], None] = time.sleep,
        idle_wait_seconds: float = 1.0,
    ) -> None:
        if idle_wait_seconds <= 0:
            raise ValueError("idle_wait_seconds must be positive")
        self._scheduler = scheduler
        self._module_provider = module_provider
        self._session_activity = session_activity
        self._backoff_policy = backoff_policy
        self._recovery = recovery
        self._clock = clock
        self._sleeper = sleeper
        self._idle_wait_seconds = idle_wait_seconds

    def start(self, context: RuntimeContext) -> SchedulerLoopResult:
        """Run cycles until the current scheduled session is no longer active."""

        modules = tuple(self._module_provider.modules_for(context))
        cycles: list[SchedulerResult] = []
        initial_dm_pending = self._has_new_followers(context)
        initial_dm_executed = False
        context.logger.info("Smart Scheduler Loop started", modules=len(modules))

        while self._session_activity.is_active(context):
            selected_dm = None
            if initial_dm_pending:
                initial_dm_pending = False
                selected_dm = next(
                    (
                        module
                        for module in modules
                        if module.module is InteractionModule.DM
                        and module.enabled
                        and module.is_eligible()
                    ),
                    None,
                )

            result = (
                self._scheduler.evaluate_selected(
                    context, selected_dm, start_module=True
                )
                if selected_dm is not None
                else self._evaluate_random(context, modules)
            )
            cycles.append(result)
            if selected_dm is not None and result.execution_started:
                initial_dm_executed = True

            if result.selected_module is None:
                self._sleeper(self._idle_wait_seconds)
                continue

            module = next(
                item for item in modules if item.module is result.selected_module
            )
            updated = self._apply_outcome(context, module, result)
            cycles[-1] = updated

        context.logger.info("Smart Scheduler Loop stopped", cycles=len(cycles))
        return SchedulerLoopResult(
            cycles=tuple(cycles),
            session_ended=True,
            initial_dm_executed=initial_dm_executed,
        )

    def _evaluate_random(
        self,
        context: RuntimeContext,
        modules: tuple[BudgetedRuntimeModule, ...],
    ) -> SchedulerResult:
        selected = self._scheduler.select(modules)
        if selected is None:
            return SchedulerResult(
                selected_module=None,
                budget=None,
                execution_started=False,
                execution_finished=False,
                next_module_state=None,
                detail="No eligible modules.",
            )
        return self._scheduler.evaluate_selected(context, selected, start_module=True)

    def _apply_outcome(
        self,
        context: RuntimeContext,
        module: BudgetedRuntimeModule,
        result: SchedulerResult,
    ) -> SchedulerResult:
        outcome = result.outcome
        if outcome is ModuleExecutionOutcome.SUCCESS:
            if module.state is ModuleState.RUNNING:
                module.mark_ready()
        elif outcome in (
            ModuleExecutionOutcome.NO_CANDIDATES,
            ModuleExecutionOutcome.SCROLL_BLOCK,
        ):
            boundary = self._backoff_policy.backoff_until(outcome, self._now())
            if boundary is None:
                raise RuntimeError("Backoff outcome requires a backoff boundary")
            module.enter_backoff(boundary)
        elif outcome is ModuleExecutionOutcome.DAILY_LIMIT_REACHED:
            module.mark_daily_limit_reached()
        elif outcome is ModuleExecutionOutcome.ACTION_BLOCK:
            self._recovery.recover(
                RecoveryRequest(
                    context=context,
                    failure=FailureKind.ACTION_BLOCK,
                    detail=result.detail or "Action block reported by module.",
                    attempt=1,
                )
            )
        return replace(result, next_module_state=module.state)

    @staticmethod
    def _has_new_followers(context: RuntimeContext) -> bool:
        startup = context.startup_result
        return startup is not None and startup.new_followers_found > 0

    def _now(self) -> datetime:
        current = self._clock()
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("Scheduler timestamps must be timezone-aware")
        return current.astimezone(timezone.utc)
