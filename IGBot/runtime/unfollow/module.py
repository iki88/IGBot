"""Search-based Unfollow orchestration and account-local persistence."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.database import RuntimeDatabase
from IGBot.runtime.database.timestamps import utc_timestamp
from IGBot.runtime.modules import InteractionModule, ModuleStateMachine
from IGBot.runtime.scheduler import ModuleExecutionOutcome, ModuleExecutionResult
from IGBot.runtime.unfollow.android import AndroidUnfollowProvider
from IGBot.runtime.unfollow.models import AndroidUnfollowStatus, UnfollowSettings


class UnfollowModule:
    """Select persisted Follow records and execute verified Unfollow actions."""

    module = InteractionModule.UNFOLLOW

    def __init__(
        self,
        context: RuntimeContext,
        settings: UnfollowSettings,
        android: AndroidUnfollowProvider,
        *,
        continue_after_search_failure: bool = False,
    ) -> None:
        self._context = context
        self._settings = settings
        self._android = android
        self._continue_after_search_failure = continue_after_search_failure
        self._unavailable_user_ids: set[int] = set()
        self._state = ModuleStateMachine(
            context,
            self.module,
            enabled=settings.enabled,
            configured=settings.configured,
        )
        self.budget_configuration = settings.budget
        self.daily_remaining = settings.daily_remaining
        self.hourly_remaining = settings.hourly_remaining

    @property
    def enabled(self):
        return self._state.enabled

    @property
    def configured(self):
        return self._state.configured

    @property
    def state(self):
        return self._state.state

    @property
    def backoff_until(self):
        return self._state.backoff_until

    def is_eligible(self):
        return (
            self.daily_remaining > 0
            and self.hourly_remaining > 0
            and self._state.is_eligible()
        )

    def start(self):
        return self._state.start()

    def mark_ready(self):
        return self._state.mark_ready()

    def enter_backoff(self, until):
        return self._state.enter_backoff(until)

    def mark_daily_limit_reached(self):
        return self._state.mark_daily_limit_reached()

    def execute(self, context: RuntimeContext, _budget) -> ModuleExecutionResult:
        cutoff = utc_timestamp(
            datetime.now(timezone.utc) - timedelta(days=self._settings.delay_days)
        )
        with RuntimeDatabase(context.session.account_directory) as database:
            records = database.follow.eligible_for_unfollow(
                cutoff,
                limit=100_000 if self._continue_after_search_failure else 1,
                require_no_follow_back=self._settings.require_no_follow_back,
            )
        records = tuple(
            record
            for record in records
            if record.user_id not in self._unavailable_user_ids
        )
        if not records:
            return self._result(
                ModuleExecutionOutcome.NO_CANDIDATES,
                "No eligible persisted Follow records.",
            )
        record = records[0]
        result = self._android.execute(context, record.username)
        while (
            self._continue_after_search_failure
            and result.status is AndroidUnfollowStatus.SEARCH_FAILED
        ):
            self._unavailable_user_ids.add(record.user_id)
            records = records[1:]
            if not records:
                return self._result(
                    ModuleExecutionOutcome.NO_CANDIDATES,
                    "No eligible persisted Follow records were found in Following.",
                )
            record = records[0]
            result = self._android.execute(context, record.username)
        if result.status is AndroidUnfollowStatus.NAVIGATION_FAILED:
            return self._result(ModuleExecutionOutcome.SCROLL_BLOCK, result.detail)
        if result.status is not AndroidUnfollowStatus.SUCCESS:
            return self._result(ModuleExecutionOutcome.SUCCESS, result.detail)
        unfollowed_at = utc_timestamp(datetime.now(timezone.utc))
        with RuntimeDatabase(context.session.account_directory) as database:
            database.follow.save(
                replace(record, unfollowed=True, unfollow_date=unfollowed_at)
            )
        context.logger.info("Runtime updated.", username=record.username)
        self.daily_remaining -= 1
        self.hourly_remaining -= 1
        outcome = (
            ModuleExecutionOutcome.DAILY_LIMIT_REACHED
            if self.daily_remaining == 0
            else ModuleExecutionOutcome.SUCCESS
        )
        return self._result(outcome)

    def _result(self, outcome: ModuleExecutionOutcome, detail: str | None = None):
        return ModuleExecutionResult(
            execution_started=True,
            execution_finished=True,
            next_module_state=self.state,
            detail=detail,
            outcome=outcome,
        )
