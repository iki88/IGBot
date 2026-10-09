"""Search-based Unfollow orchestration and account-local persistence."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from IGBot.runtime.analytics import increment_analytics
from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.database import RuntimeDatabase
from IGBot.runtime.database.timestamps import utc_timestamp
from IGBot.runtime.ignore import log_ignored
from IGBot.runtime.modules import InteractionModule, ModuleStateMachine
from IGBot.runtime.navigation import NavigationStatus
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
        if context.cancellation_checkpoint("Unfollow candidate selection"):
            return self._result(
                ModuleExecutionOutcome.SUCCESS, "Unfollow execution cancelled."
            )
        cutoff = utc_timestamp(
            datetime.now(timezone.utc) - timedelta(days=self._settings.delay_days)
        )
        with RuntimeDatabase(context.session.account_directory) as database:
            records = database.follow.eligible_for_unfollow(
                cutoff,
                limit=100_000,
                require_no_follow_back=self._settings.require_no_follow_back,
            )
        available = []
        for record in records:
            if record.user_id in self._unavailable_user_ids:
                continue
            if context.ignore_service.is_ignored(record.username):
                log_ignored(context, record.username)
                self._unavailable_user_ids.add(record.user_id)
                continue
            available.append(record)
        records = tuple(available)
        if not records:
            return self._result(
                ModuleExecutionOutcome.NO_CANDIDATES,
                "No eligible persisted Follow records.",
            )
        record = records[0]
        if context.cancellation_checkpoint("Unfollow profile opening"):
            return self._result(
                ModuleExecutionOutcome.SUCCESS, "Unfollow execution cancelled."
            )
        result = self._android.execute(context, record.username)
        while result.status is AndroidUnfollowStatus.IGNORED:
            self._unavailable_user_ids.add(record.user_id)
            records = records[1:]
            if not records:
                return self._result(
                    ModuleExecutionOutcome.NO_CANDIDATES,
                    "No eligible persisted Follow records remain.",
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
            return self._result(ModuleExecutionOutcome.NAVIGATION_FAILED, result.detail)
        if result.status is not AndroidUnfollowStatus.SUCCESS:
            return self._result(ModuleExecutionOutcome.SUCCESS, result.detail)
        unfollowed_at = utc_timestamp(datetime.now(timezone.utc))
        with RuntimeDatabase(context.session.account_directory) as database:
            database.follow.save(
                replace(record, unfollowed=True, unfollow_date=unfollowed_at)
            )
        context.logger.info("Runtime updated.", username=record.username)
        increment_analytics(context, "unfollowed")
        self.daily_remaining -= 1
        self.hourly_remaining -= 1
        if result.navigation.status is NavigationStatus.FAILED:
            return self._result(
                ModuleExecutionOutcome.NAVIGATION_FAILED,
                result.navigation.detail or result.detail,
                verified_successes=1,
            )
        if context.cancellation_checkpoint("Unfollow result persisted"):
            return self._result(
                ModuleExecutionOutcome.SUCCESS, "Unfollow execution cancelled."
            )
        outcome = (
            ModuleExecutionOutcome.DAILY_LIMIT_REACHED
            if self.daily_remaining == 0
            else ModuleExecutionOutcome.SUCCESS
        )
        return self._result(outcome, verified_successes=1)

    def _result(
        self,
        outcome: ModuleExecutionOutcome,
        detail: str | None = None,
        *,
        verified_successes: int = 0,
    ):
        return ModuleExecutionResult(
            execution_started=True,
            execution_finished=True,
            next_module_state=self.state,
            detail=detail,
            outcome=outcome,
            verified_successes=verified_successes,
        )
