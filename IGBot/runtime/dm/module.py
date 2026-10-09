"""Welcome-DM candidate selection and Runtime Database persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from IGBot.runtime.action_delay import ActionDelay
from IGBot.runtime.analytics import increment_analytics
from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.database import DMRecord, RuntimeDatabase
from IGBot.runtime.database.timestamps import utc_timestamp
from IGBot.runtime.dm.android import AndroidDMProvider
from IGBot.runtime.dm.message_renderer import DMMessageRenderer
from IGBot.runtime.dm.models import AndroidDMStatus, DMSettings
from IGBot.runtime.ignore import log_ignored
from IGBot.runtime.modules import InteractionModule, ModuleStateMachine
from IGBot.runtime.navigation import NavigationStatus
from IGBot.runtime.scheduler import ModuleExecutionOutcome, ModuleExecutionResult


class DMModule:
    """Send one Welcome DM to each locally known follow-back candidate."""

    module = InteractionModule.DM

    def __init__(
        self,
        context: RuntimeContext,
        settings: DMSettings,
        android: AndroidDMProvider,
        *,
        recipients=None,
        persistence=None,
        private_fallback: bool = False,
        bounded_search: bool = False,
        message_renderer: DMMessageRenderer | None = None,
        action_delay: ActionDelay | None = None,
    ) -> None:
        self._context = context
        self._settings = settings
        self._android = android
        self._recipients = recipients or WelcomeDMRecipients()
        self._persistence = persistence or WelcomeDMPersistence()
        self._private_fallback = private_fallback
        self._bounded_search = bounded_search
        self._message_renderer = message_renderer or DMMessageRenderer()
        self._action_delay = action_delay or ActionDelay(settings.action_delay)
        self._attempted: set[int] = set()
        self.session_complete = False
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
            not self.session_complete
            and self.daily_remaining > 0
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

    def execute(self, context: RuntimeContext, budget) -> ModuleExecutionResult:
        target = max(1, int(getattr(budget, "final", 1)))
        successful = 0
        while successful < target:
            if context.cancellation_checkpoint("DM recipient selection"):
                return self._result(
                    ModuleExecutionOutcome.SUCCESS,
                    "DM execution cancelled.",
                    verified_successes=successful,
                )
            context.logger.info("[DM] Looking for recipient...")
            candidate = self._next_candidate(context)
            if candidate is None:
                self.session_complete = True
                return self._result(
                    ModuleExecutionOutcome.NO_CANDIDATES,
                    "No unmessaged recipients remain.",
                    verified_successes=successful,
                )

            self._attempted.add(candidate.user_id)
            context.logger.info("[DM] Candidate selected", username=candidate.username)
            rendered_message = self._message_renderer.render(self._settings.message)
            if context.cancellation_checkpoint("DM profile opening"):
                return self._result(
                    ModuleExecutionOutcome.SUCCESS,
                    "DM execution cancelled.",
                    verified_successes=successful,
                )
            result = self._android.execute(
                context,
                candidate.username,
                rendered_message,
                private_fallback=self._private_fallback,
                bounded_search=self._bounded_search,
            )
            if result.status is AndroidDMStatus.IGNORED:
                log_ignored(context, candidate.username)
                continue

            if (
                context.cancellation_checkpoint("DM Android interaction")
                and result.status is not AndroidDMStatus.SUCCESS
            ):
                return self._result(
                    ModuleExecutionOutcome.SUCCESS,
                    "DM execution cancelled.",
                    verified_successes=successful,
                )

            self._persistence.persist(
                context, candidate, result.status.value, rendered_message
            )
            if context.cancellation_checkpoint("DM result persisted"):
                return self._result(
                    ModuleExecutionOutcome.SUCCESS,
                    "DM execution cancelled.",
                    verified_successes=successful,
                )
            if result.status is not AndroidDMStatus.SUCCESS:
                if result.navigation.status is NavigationStatus.FAILED:
                    return self._result(
                        ModuleExecutionOutcome.NAVIGATION_FAILED,
                        result.navigation.detail or result.detail,
                        verified_successes=successful,
                    )
                continue

            successful += 1
            increment_analytics(context, "dm")
            self.daily_remaining -= 1
            self.hourly_remaining -= 1
            if result.navigation.status is NavigationStatus.FAILED:
                return self._result(
                    ModuleExecutionOutcome.NAVIGATION_FAILED,
                    result.navigation.detail or result.detail,
                    verified_successes=successful,
                )
            if self.daily_remaining == 0:
                return self._result(
                    ModuleExecutionOutcome.DAILY_LIMIT_REACHED,
                    verified_successes=successful,
                )
            if successful == target or self.hourly_remaining == 0:
                self.session_complete = successful == target
                return self._result(
                    ModuleExecutionOutcome.SUCCESS,
                    verified_successes=successful,
                )
            self._action_delay.wait(
                context.cancellation_requested,
                cancellation_wait=context.cancellation_wait,
            )

        raise RuntimeError("DM execution target loop exited unexpectedly")

    def _next_candidate(self, context: RuntimeContext) -> DMRecipient | None:
        candidates = self._recipients.pending(context)
        candidate = next(
            (item for item in candidates if item.user_id not in self._attempted), None
        )
        while candidate is not None and context.ignore_service.is_ignored(
            candidate.username
        ):
            self._attempted.add(candidate.user_id)
            log_ignored(context, candidate.username)
            candidate = next(
                (item for item in candidates if item.user_id not in self._attempted),
                None,
            )
        return candidate

    def _result(self, outcome, detail=None, *, verified_successes=0):
        return ModuleExecutionResult(
            execution_started=True,
            execution_finished=True,
            next_module_state=self.state,
            detail=detail,
            outcome=outcome,
            verified_successes=verified_successes,
        )


@dataclass(frozen=True, slots=True)
class DMRecipient:
    user_id: int
    username: str
    source: str | None = None


class DMRecipients(Protocol):
    def pending(self, context: RuntimeContext) -> tuple[DMRecipient, ...]: ...


class DMPersistence(Protocol):
    def persist(
        self,
        context: RuntimeContext,
        recipient: DMRecipient,
        status: str,
        message: str,
    ) -> None: ...


class WelcomeDMRecipients:
    def pending(self, context: RuntimeContext) -> tuple[DMRecipient, ...]:
        with RuntimeDatabase(context.session.account_directory) as database:
            rows = database.dm.eligible_new_followers()
        return tuple(DMRecipient(*row) for row in rows)


class WelcomeDMPersistence:
    def persist(
        self,
        context: RuntimeContext,
        recipient: DMRecipient,
        status: str,
        message: str,
    ) -> None:
        sent_at = utc_timestamp(datetime.now(timezone.utc))
        successful = status == AndroidDMStatus.SUCCESS.value
        with RuntimeDatabase(context.session.account_directory) as database:
            existing = database.dm.get(recipient.user_id)
            database.dm.save(
                DMRecord(
                    user_id=recipient.user_id,
                    source=recipient.source,
                    dm_count=(existing.dm_count if existing else 0) + int(successful),
                    last_dm_date=(
                        sent_at
                        if successful
                        else existing.last_dm_date if existing else None
                    ),
                    last_message=(
                        message
                        if successful
                        else existing.last_message if existing else None
                    ),
                    last_reply=existing.last_reply if existing else None,
                    status=status,
                )
            )
        context.logger.info(
            "[DM] Database updated", username=recipient.username, status=status
        )
