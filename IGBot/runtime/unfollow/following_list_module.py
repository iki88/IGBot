"""Runtime orchestration for Unfollow All Followings."""

from __future__ import annotations

from datetime import datetime, timezone

from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.database.timestamps import utc_timestamp
from IGBot.runtime.modules import InteractionModule, ModuleStateMachine
from IGBot.runtime.scheduler import ModuleExecutionOutcome, ModuleExecutionResult
from IGBot.runtime.unfollow.following_list_android import (
    AndroidFollowingListUnfollowProvider,
)
from IGBot.runtime.unfollow.following_list_database import FollowingListDatabase
from IGBot.runtime.unfollow.models import AndroidUnfollowStatus, UnfollowSettings


class AllFollowingsUnfollowModule:
    """Execute one sequential Following-list candidate per scheduler cycle."""

    module = InteractionModule.UNFOLLOW

    def __init__(
        self,
        context: RuntimeContext,
        settings: UnfollowSettings,
        android: AndroidFollowingListUnfollowProvider,
    ) -> None:
        self._settings = settings
        self._android = android
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
        with FollowingListDatabase(context.session.account_directory) as database:
            processed = database.processed_usernames()
        result = self._android.execute_next(context, processed)
        if result.status is AndroidUnfollowStatus.NO_CANDIDATES:
            return self._result(ModuleExecutionOutcome.NO_CANDIDATES, result.detail)
        if result.status is AndroidUnfollowStatus.NAVIGATION_FAILED:
            return self._result(ModuleExecutionOutcome.SCROLL_BLOCK, result.detail)
        if result.status is not AndroidUnfollowStatus.SUCCESS or not result.username:
            return self._result(ModuleExecutionOutcome.SUCCESS, result.detail)

        unfollowed_at = utc_timestamp(datetime.now(timezone.utc))
        with FollowingListDatabase(context.session.account_directory) as database:
            database.mark_unfollowed(
                result.username,
                unfollowed_at,
                str(context.session.session_id),
            )
        context.logger.info("Runtime updated.", username=result.username)
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
