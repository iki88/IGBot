"""Native Like module orchestration and Runtime Database persistence."""

from __future__ import annotations

from datetime import datetime, timezone

from IGBot.runtime.analytics import increment_analytics
from IGBot.runtime.candidates import CandidateResultStatus
from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.database import LikeRecord, RuntimeDatabase
from IGBot.runtime.database.timestamps import utc_timestamp
from IGBot.runtime.ignore import log_ignored
from IGBot.runtime.like.android import AndroidLikeProvider
from IGBot.runtime.like.models import AndroidLikeStatus
from IGBot.runtime.modules import InteractionModule, ModuleStateMachine
from IGBot.runtime.navigation import NavigationStatus
from IGBot.runtime.scheduler import ModuleExecutionOutcome, ModuleExecutionResult


class LikeModule:
    """Discover one Source Followers candidate and execute one photo Like."""

    module = InteractionModule.LIKE

    def __init__(
        self,
        context,
        settings,
        candidates,
        android: AndroidLikeProvider,
        persistence=None,
    ):
        self._context = context
        self._settings = settings
        self._candidates = candidates
        self._android = android
        self._persistence = persistence or _DiscoveryLikePersistence()
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

    def execute(self, context: RuntimeContext, budget) -> ModuleExecutionResult:
        if context is not self._context:
            raise ValueError("Like Module received a different RuntimeContext")
        while True:
            if context.cancellation_checkpoint("Like candidate discovery"):
                return self._result(
                    ModuleExecutionOutcome.SUCCESS, "Like execution cancelled."
                )
            discovered = self._candidates.next_candidate(context)
            if discovered.status is CandidateResultStatus.CURRENT_SOURCE_EXHAUSTED:
                continue
            if discovered.status is CandidateResultStatus.SCROLL_BLOCK:
                return self._result(
                    ModuleExecutionOutcome.SCROLL_BLOCK, discovered.detail
                )
            if discovered.status is CandidateResultStatus.ALL_SOURCES_EXHAUSTED:
                return self._result(
                    ModuleExecutionOutcome.NO_CANDIDATES, discovered.detail
                )
            if discovered.status is CandidateResultStatus.FILTER_REJECTED:
                continue
            candidate = discovered.candidate
            if candidate is None:
                raise RuntimeError("Like candidate provider returned no candidate")
            if context.ignore_service.is_ignored(candidate.username):
                log_ignored(context, candidate.username)
                mark_ignored = getattr(self._candidates, "mark_ignored", None)
                if mark_ignored is not None:
                    mark_ignored(candidate)
                continue
            if self._persistence.already_processed(context, candidate):
                continue
            if context.cancellation_checkpoint("Like profile opening"):
                return self._result(
                    ModuleExecutionOutcome.SUCCESS, "Like execution cancelled."
                )
            result = self._android.execute(
                context,
                candidate,
                maximum_likes=min(
                    self.daily_remaining,
                    self.hourly_remaining,
                    max(
                        1,
                        int(
                            getattr(
                                budget,
                                "final",
                                min(self.daily_remaining, self.hourly_remaining),
                            )
                        ),
                    ),
                ),
            )
            if result.status is AndroidLikeStatus.IGNORED:
                mark_ignored = getattr(self._candidates, "mark_ignored", None)
                if mark_ignored is not None:
                    mark_ignored(candidate)
                continue
            if result.status is not AndroidLikeStatus.PROFILE_UNAVAILABLE:
                record_evaluated = getattr(self._candidates, "record_evaluated", None)
                if record_evaluated is not None:
                    record_evaluated(context)
            if (
                context.cancellation_checkpoint("Like Android interaction")
                and not result.likes_completed
            ):
                return self._result(
                    ModuleExecutionOutcome.SUCCESS,
                    "Like execution cancelled.",
                    verified_successes=result.likes_completed,
                    module_result=result,
                )
            self._persistence.persist(
                context,
                candidate,
                result.status.value,
                result.likes_completed,
            )
            if result.likes_completed:
                increment_analytics(context, "liked", result.likes_completed)
                self.daily_remaining -= result.likes_completed
                self.hourly_remaining -= result.likes_completed
            if context.cancellation_checkpoint("Like result persisted"):
                return self._result(
                    ModuleExecutionOutcome.SUCCESS,
                    "Like execution cancelled.",
                    verified_successes=result.likes_completed,
                    module_result=result,
                )
            if result.navigation.status is NavigationStatus.FAILED:
                return self._result(
                    ModuleExecutionOutcome.NAVIGATION_FAILED,
                    result.navigation.detail or result.detail,
                    verified_successes=result.likes_completed,
                    module_result=result,
                )
            if result.status in {
                AndroidLikeStatus.NO_POSTS,
                AndroidLikeStatus.FILTER_REJECTED,
            }:
                continue
            if result.status is not AndroidLikeStatus.SUCCESS:
                return self._result(
                    ModuleExecutionOutcome.SUCCESS,
                    result.detail,
                    verified_successes=result.likes_completed,
                    module_result=result,
                )
            outcome = (
                ModuleExecutionOutcome.DAILY_LIMIT_REACHED
                if self.daily_remaining == 0
                else ModuleExecutionOutcome.SUCCESS
            )
            return self._result(
                outcome,
                result.detail,
                verified_successes=result.likes_completed,
                module_result=result,
            )

    def _result(
        self,
        outcome,
        detail=None,
        *,
        verified_successes=0,
        module_result=None,
    ):
        return ModuleExecutionResult(
            execution_started=True,
            execution_finished=True,
            next_module_state=self.state,
            detail=detail,
            outcome=outcome,
            verified_successes=verified_successes,
            module_result=module_result,
        )


class _DiscoveryLikePersistence:
    """Account-local persistence used by source-discovery Like workflows."""

    @staticmethod
    def already_processed(context: RuntimeContext, candidate) -> bool:
        with RuntimeDatabase(context.session.account_directory) as database:
            user = database.users.get_by_username(candidate.username)
            if user is None:
                return False
            previous = database.like.get(user.id, candidate.source)
        if previous is None or previous.status == "UNKNOWN":
            return False
        context.logger.info(
            "[Like] Candidate already processed. Skipping.",
            username=candidate.username,
            source=candidate.source,
            status=previous.status,
        )
        return True

    @staticmethod
    def persist(
        context: RuntimeContext,
        candidate,
        status: str,
        likes_completed: int,
    ) -> None:
        username = candidate.username
        source = candidate.source
        processed_at = utc_timestamp(datetime.now(timezone.utc))
        with RuntimeDatabase(context.session.account_directory) as database:
            user = database.users.get_by_username(username)
            if user is None:
                user = database.users.create(username, processed_at, "LIKE")
            existing = database.like.get(user.id, source)
            database.like.save(
                LikeRecord(
                    user_id=user.id,
                    username=username,
                    source=source,
                    status=status,
                    likes_count=(existing.likes_count if existing else 0)
                    + likes_completed,
                    last_like_date=(
                        processed_at
                        if likes_completed
                        else existing.last_like_date if existing else None
                    ),
                    processed_date=processed_at,
                    follow_back=existing.follow_back if existing else False,
                    follow_back_date=existing.follow_back_date if existing else None,
                    last_session_id=str(context.session.session_id),
                )
            )
        context.logger.info(
            "Like runtime updated.", username=username, source=source, status=status
        )
