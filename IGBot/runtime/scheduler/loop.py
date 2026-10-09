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
    ModuleOperation,
    SchedulerLoopResult,
    SchedulerResult,
)
from IGBot.runtime.scheduler.scheduler import Scheduler
from IGBot.runtime.state import ModuleState


class SchedulerLoop:
    """Repeat bounded scheduler cycles while SessionController reports active."""

    _TERMINAL_STATE_VALUES = frozenset(
        {
            ModuleState.DAILY_LIMIT_REACHED.value,
            "OPERATION_LIMIT_REACHED",
            "SESSION_COMPLETE",
        }
    )

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
            enabled_modules = tuple(module for module in modules if module.enabled)
            if enabled_modules and all(
                self._session_work_complete(module) for module in enabled_modules
            ):
                break
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

            selected = selected_dm or self._scheduler.select(modules)
            if selected is None:
                result = SchedulerResult(
                    selected_module=None,
                    budget=None,
                    execution_started=False,
                    execution_finished=False,
                    next_module_state=None,
                    detail="No eligible modules.",
                )
                cycles.append(result)
                self._sleeper(self._idle_wait_seconds)
                continue

            context.logger.info("Scheduler selected module", module=selected.module.value)
            operation_cycles = self._run_operation(context, selected)
            cycles.extend(operation_cycles)
            if selected_dm is not None and any(
                result.execution_started for result in operation_cycles
            ):
                initial_dm_executed = True
            if operation_cycles and (
                operation_cycles[-1].outcome
                is ModuleExecutionOutcome.NAVIGATION_FAILED
            ):
                context.logger.warning(
                    "Scheduler session ending after failed navigation handoff.",
                    module=selected.module.value,
                )
                break

        context.logger.info("Smart Scheduler Loop stopped", cycles=len(cycles))
        return SchedulerLoopResult(
            cycles=tuple(cycles),
            session_ended=True,
            initial_dm_executed=initial_dm_executed,
        )

    def _run_operation(
        self,
        context: RuntimeContext,
        module: BudgetedRuntimeModule,
    ) -> tuple[SchedulerResult, ...]:
        operation = ModuleOperation(module.module, self._scheduler.resolve_budget(module))
        context.logger.info(
            "ModuleOperation created",
            module=module.module.value,
            target=operation.target,
        )
        results: list[SchedulerResult] = []
        first_step = True
        while first_step or self._session_activity.is_active(context):
            first_step = False
            if context.cancellation_checkpoint(
                f"{module.module.value} ModuleOperation"
            ):
                break
            if operation.completed:
                break
            if not module.is_eligible():
                context.logger.info(
                    "ModuleOperation relinquished",
                    module=module.module.value,
                    verified=operation.verified_successes,
                    target=operation.target,
                    reason="module no longer eligible",
                )
                break
            budget = operation.remaining_budget(module.daily_remaining)
            result = self._scheduler.evaluate_with_budget(
                context,
                module,
                budget,
                start_module=True,
            )
            updated = self._apply_outcome(context, module, result)
            results.append(updated)
            operation.record(updated.verified_successes)
            if updated.verified_successes:
                context.logger.info(
                    f"Verified {module.module.value}",
                    verified=operation.verified_successes,
                    target=operation.target,
                    remaining=operation.remaining,
                )
            if operation.completed:
                context.logger.info(
                    "ModuleOperation completed",
                    module=module.module.value,
                    verified=operation.verified_successes,
                    target=operation.target,
                )
                context.logger.info("Scheduler selecting next module")
                break
            if updated.outcome is not ModuleExecutionOutcome.SUCCESS:
                context.logger.info(
                    "ModuleOperation relinquished",
                    module=module.module.value,
                    verified=operation.verified_successes,
                    target=operation.target,
                    reason=(updated.outcome.value if updated.outcome else "unknown"),
                )
                break
        return tuple(results)

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

    @classmethod
    def _session_work_complete(cls, module: BudgetedRuntimeModule) -> bool:
        """Return whether one enabled module has no more work this session."""

        if getattr(module, "session_aborted", False) or getattr(
            module, "session_complete", False
        ):
            return True
        state = module.state
        return getattr(state, "value", state) in cls._TERMINAL_STATE_VALUES
