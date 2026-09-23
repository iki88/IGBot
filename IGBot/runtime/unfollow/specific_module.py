"""Runtime orchestration for Unfollow Specific Users."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.database import RuntimeDatabase
from IGBot.runtime.database.timestamps import utc_timestamp
from IGBot.runtime.modules import InteractionModule, ModuleStateMachine
from IGBot.runtime.scheduler import ModuleExecutionOutcome, ModuleExecutionResult
from IGBot.runtime.unfollow.android import AndroidUnfollowProvider
from IGBot.runtime.unfollow.models import AndroidUnfollowStatus, UnfollowSettings


class SpecificUnfollowSynchronizer:
    """Synchronize the account-local TXT source into runtime execution state."""

    def synchronize(self, account_directory: str | Path) -> tuple[str, ...]:
        directory = Path(account_directory)
        path = directory / "Lists" / "unfollowspecific.txt"
        usernames = (
            tuple(
                line.strip()
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            )
            if path.is_file()
            else ()
        )
        with RuntimeDatabase(directory) as database:
            database.specific_unfollow.synchronize_unfollow_usernames(usernames)
        return usernames


class SpecificUnfollowModule:
    """Execute verified Search-based unfollows from specific_unfollow state."""

    module = InteractionModule.UNFOLLOW

    def __init__(
        self,
        context: RuntimeContext,
        settings: UnfollowSettings,
        android: AndroidUnfollowProvider,
    ) -> None:
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
        with RuntimeDatabase(context.session.account_directory) as database:
            usernames = database.specific_unfollow.pending_unfollow_usernames()
        if not usernames:
            return self._result(
                ModuleExecutionOutcome.NO_CANDIDATES,
                "No pending Specific Unfollow users remain.",
            )
        username = usernames[0]
        context.logger.info(
            "[Specific Unfollow] Searching username...", username=username
        )
        result = self._android.execute(context, username)
        if result.status is not AndroidUnfollowStatus.SUCCESS:
            return self._result(ModuleExecutionOutcome.SUCCESS, result.detail)

        unfollowed_at = utc_timestamp(datetime.now(timezone.utc))
        with RuntimeDatabase(context.session.account_directory) as database:
            database.specific_unfollow.mark_specific_unfollowed(
                username, unfollowed_at, str(context.session.session_id)
            )
        context.logger.info("Runtime updated.", username=username)
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
