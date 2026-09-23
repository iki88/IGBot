"""Follow Module workflow through the pre-interaction boundary."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from IGBot.runtime.candidates import (
    Candidate,
    CandidateProvider,
    CandidateProviderType,
    CandidateResultStatus,
)
from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.follow.contracts import (
    CandidateProfileProvider,
    FollowCandidateQualifier,
)
from IGBot.runtime.follow.models import (
    FollowModuleResult,
    FollowModuleResultStatus,
    FollowModuleSettings,
)
from IGBot.runtime.hooks import HookEvent, HookEventType, HookManager
from IGBot.runtime.modules import InteractionModule, ModuleStateMachine
from IGBot.runtime.scheduler import (
    ExecutionBudget,
    ModuleExecutionOutcome,
    ModuleExecutionResult,
)
from IGBot.runtime.state import ModuleState


class FollowModule:
    """Prepare one qualified profile without tapping the Follow button."""

    def __init__(
        self,
        context: RuntimeContext,
        settings: FollowModuleSettings,
        candidate_provider: CandidateProvider,
        profile_provider: CandidateProfileProvider,
        qualifier: FollowCandidateQualifier,
        hook_manager: HookManager,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        cancellation_requested: Callable[[], bool] = lambda: False,
    ) -> None:
        self._context = context
        self._settings = settings
        self._candidate_provider = candidate_provider
        self._profile_provider = profile_provider
        self._qualifier = qualifier
        self._hook_manager = hook_manager
        self._clock = clock
        self._cancellation_requested = cancellation_requested
        self.consecutive_profile_timeouts = 0
        self.session_aborted = False
        now = self._now()
        self._daily_limit = settings.daily_remaining
        self._daily_remaining = settings.daily_remaining
        self._daily_started = now.date()
        self._hourly_limit = settings.hourly_remaining
        self._hourly_remaining = settings.hourly_remaining
        self._hour_started = now.replace(minute=0, second=0, microsecond=0)
        self._state = ModuleStateMachine(
            context,
            InteractionModule.FOLLOW,
            enabled=settings.enabled,
            configured=settings.configured,
        )

    @property
    def module(self) -> InteractionModule:
        return InteractionModule.FOLLOW

    @property
    def context(self) -> RuntimeContext:
        return self._context

    @property
    def state(self) -> ModuleState:
        return self._state.state

    @property
    def enabled(self) -> bool:
        return self._state.enabled

    @property
    def backoff_until(self) -> datetime | None:
        return self._state.backoff_until

    @property
    def budget_configuration(self) -> int | str:
        return self._settings.budget

    @property
    def daily_remaining(self) -> int:
        self._refresh_limits()
        return self._daily_remaining

    @property
    def hourly_remaining(self) -> int:
        """Return successful follows remaining in the current hourly window."""
        self._refresh_limits()
        return self._hourly_remaining

    def is_eligible(self) -> bool:
        state_eligible = self._state.is_eligible()
        self._refresh_limits()
        return (
            not self.session_aborted
            and self._daily_remaining > 0
            and self._hourly_remaining > 0
            and state_eligible
        )

    def record_verified_follow(self) -> tuple[bool, bool]:
        """Account for one verified Follow and report exhausted limits."""
        self._refresh_limits()
        if self._daily_remaining <= 0 or self._hourly_remaining <= 0:
            raise RuntimeError("A verified Follow exceeded its runtime allowance")
        self._daily_remaining -= 1
        self._hourly_remaining -= 1
        self._context.logger.info(
            "Follow runtime counters updated",
            daily_remaining=self._daily_remaining,
            hourly_remaining=self._hourly_remaining,
        )
        return self._daily_remaining == 0, self._hourly_remaining == 0

    def complete_verified_follow(self) -> ModuleExecutionOutcome:
        """Update counters and return the authoritative post-Follow outcome."""
        daily_reached, hourly_reached = self.record_verified_follow()
        self._context.logger.info(
            "Follow limit evaluation completed",
            operation_limit_reached=True,
            hourly_limit_reached=hourly_reached,
            daily_limit_reached=daily_reached,
        )
        return (
            ModuleExecutionOutcome.DAILY_LIMIT_REACHED
            if daily_reached
            else ModuleExecutionOutcome.SUCCESS
        )

    def cancellation_requested(self) -> bool:
        """Return the session-owned cancellation signal."""
        return self._cancellation_requested()

    def _refresh_limits(self) -> None:
        now = self._now()
        if now.date() > self._daily_started:
            self._daily_started = now.date()
            self._daily_remaining = self._daily_limit
        hour = now.replace(minute=0, second=0, microsecond=0)
        if hour > self._hour_started:
            self._hour_started = hour
            self._hourly_remaining = self._hourly_limit

    def _now(self) -> datetime:
        current = self._clock()
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("Follow counter timestamps must be timezone-aware")
        return current.astimezone(timezone.utc)

    def start(self) -> object:
        return self._state.start()

    def mark_ready(self) -> object:
        return self._state.mark_ready()

    def enter_backoff(self, backoff_until: datetime) -> object:
        return self._state.enter_backoff(backoff_until)

    def mark_daily_limit_reached(self) -> object:
        return self._state.mark_daily_limit_reached()

    def execute(
        self, context: RuntimeContext, budget: ExecutionBudget
    ) -> ModuleExecutionResult:
        """Run one bounded preparation cycle and stop before Follow interaction."""

        self._validate_execution(context, budget)
        if self.session_aborted:
            return self._result(
                FollowModuleResultStatus.FILTER_REJECTED,
                detail="Follow session aborted after consecutive profile loading timeouts.",
            )
        context.logger.debug("Follow candidate preparation started")
        while True:
            if self._cancelled(context, "locating candidate"):
                return self._cancelled_result()
            discovered = self._candidate_provider.next_candidate(context)
            if discovered.status is CandidateResultStatus.SCROLL_BLOCK:
                return self._result(
                    FollowModuleResultStatus.SCROLL_BLOCK,
                    ModuleExecutionOutcome.SCROLL_BLOCK,
                    discovered.detail,
                )
            if discovered.status is CandidateResultStatus.CURRENT_SOURCE_EXHAUSTED:
                continue
            if discovered.status is CandidateResultStatus.ALL_SOURCES_EXHAUSTED:
                return self._result(
                    FollowModuleResultStatus.NO_CANDIDATES,
                    ModuleExecutionOutcome.NO_CANDIDATES,
                    discovered.detail,
                )
            if discovered.status is CandidateResultStatus.FILTER_REJECTED:
                return self._result(
                    FollowModuleResultStatus.FILTER_REJECTED,
                    detail=discovered.detail,
                )

            candidate = discovered.candidate
            if candidate is None:
                raise RuntimeError("Candidate provider returned no candidate")
            if self._cancelled(context, "opening candidate"):
                return self._cancelled_result()
            profile = self._profile_provider.open_profile(context, candidate)
            if profile is None and getattr(
                self._profile_provider, "profile_loading_timed_out", False
            ):
                self.consecutive_profile_timeouts += 1
                self._mark_specific_processed(context, candidate)
                if self.consecutive_profile_timeouts >= 3:
                    self.session_aborted = True
                    context.logger.warning(
                        "[Profile] Consecutive profile loading timeouts detected."
                    )
                    context.logger.warning("[Follow] Aborting current Follow session.")
                    return self._result(
                        FollowModuleResultStatus.FILTER_REJECTED,
                        detail="Follow session aborted after consecutive profile loading timeouts.",
                    )
                continue
            if profile is None:
                context.logger.warning(
                    "Candidate processing stopped",
                    username=candidate.username,
                    reason="profile unavailable",
                )
                self._mark_specific_processed(context, candidate)
                return self._result(
                    FollowModuleResultStatus.FILTER_REJECTED,
                    detail=(
                        f"Candidate profile could not be opened: {candidate.username}"
                    ),
                )
            context.logger.info(
                "Candidate processing started", username=candidate.username
            )
            self.consecutive_profile_timeouts = 0
            if self._cancelled(context, "filter evaluation"):
                self._profile_provider.return_to_followers(context)
                return self._cancelled_result()
            context.logger.info(
                "Filter evaluation started", username=candidate.username
            )
            record_evaluated = getattr(
                self._candidate_provider, "record_evaluated", None
            )
            if record_evaluated is not None:
                record_evaluated(context)
            if (
                candidate.provider_type is CandidateProviderType.SPECIFIC_ACCOUNTS
                and not self._profile_filters_enabled()
            ):
                context.logger.info(
                    "Profile filter evaluation skipped",
                    username=candidate.username,
                    reason="no profile filters configured",
                )
                qualification = None
            else:
                qualification = self._qualifier.qualify(
                    context, profile, self._settings.filters
                )
            if (
                qualification is None
                or qualification.status is FollowModuleResultStatus.READY_TO_FOLLOW
            ):
                context.logger.info(
                    "Filter evaluation completed", username=candidate.username
                )
                break

            context.logger.info(
                "Filter evaluation stopped candidate processing",
                username=candidate.username,
                status=qualification.status.value,
                detail=qualification.detail or "",
            )
            if candidate.provider_type is CandidateProviderType.SPECIFIC_ACCOUNTS:
                self._mark_specific_processed(context, candidate)
                context.logger.info(
                    "[Specific] Candidate skipped.", username=candidate.username
                )
                continue
            restored = self._profile_provider.return_to_followers(context)
            if not restored.succeeded:
                context.logger.error(
                    "Candidate rejection recovery failed",
                    username=candidate.username,
                    detail=restored.detail or "",
                )
                return self._result(
                    qualification.status,
                    detail=restored.detail or qualification.detail,
                )
            context.logger.info(
                "[Candidate] Continuing with next candidate",
                rejected_username=candidate.username,
            )

        hook_results = ()
        if self._settings.contact_scraping_enabled:
            if self._cancelled(context, "contact scraping"):
                self._profile_provider.return_to_followers(context)
                return self._cancelled_result()
            hook_results = tuple(
                self._hook_manager.dispatch(
                    HookEvent(
                        HookEventType.PROFILE_OPENED,
                        context,
                        {"candidate": candidate, "profile": profile},
                    )
                )
            )
        context.logger.info("Follow candidate ready", username=candidate.username)
        domain_result = FollowModuleResult(
            FollowModuleResultStatus.READY_TO_FOLLOW,
            candidate=candidate,
            hook_results=hook_results,
        )
        return ModuleExecutionResult(
            execution_started=True,
            execution_finished=True,
            next_module_state=self.state,
            outcome=ModuleExecutionOutcome.SUCCESS,
            module_result=domain_result,
        )

    def mark_candidate_processed(
        self, context: RuntimeContext, candidate: Candidate
    ) -> None:
        """Advance provider-owned progress after an interaction outcome."""

        self._mark_specific_processed(context, candidate)

    def _mark_specific_processed(
        self, context: RuntimeContext, candidate: Candidate
    ) -> None:
        if candidate.provider_type is not CandidateProviderType.SPECIFIC_ACCOUNTS:
            return
        mark_processed = getattr(self._candidate_provider, "mark_processed", None)
        if mark_processed is not None:
            mark_processed(context)

    def _profile_filters_enabled(self) -> bool:
        filters = self._settings.filters
        return any(
            (
                not filters.allow_private,
                filters.follow_only_private,
                filters.skip_business,
                filters.follow_only_business,
                filters.skip_link_in_bio,
                filters.follow_only_link_in_bio,
                filters.min_followers is not None,
                filters.max_followers is not None,
                filters.min_following is not None,
                filters.max_following is not None,
                filters.min_posts is not None,
                bool(filters.keywords.required),
                bool(filters.keywords.blocked),
                bool(filters.allowed_alphabets),
                bool(filters.biography_languages),
            )
        )

    def _cancelled(self, context: RuntimeContext, next_stage: str) -> bool:
        cancelled = self._cancellation_requested()
        if cancelled:
            context.logger.info(
                "Follow cancellation acknowledged", next_stage=next_stage
            )
        return cancelled

    def _cancelled_result(self) -> ModuleExecutionResult:
        return self._result(
            FollowModuleResultStatus.CANCELLED,
            detail="Follow execution cancelled.",
        )

    def _validate_execution(
        self, context: RuntimeContext, budget: ExecutionBudget
    ) -> None:
        if context is not self._context:
            raise ValueError("Follow Module received a different RuntimeContext")
        if budget.module is not InteractionModule.FOLLOW:
            raise ValueError("Follow Module requires a Follow execution budget")
        if budget.final <= 0:
            raise ValueError("Follow Module requires a positive execution budget")

    def _result(
        self,
        status: FollowModuleResultStatus,
        outcome: ModuleExecutionOutcome = ModuleExecutionOutcome.SUCCESS,
        detail: str | None = None,
    ) -> ModuleExecutionResult:
        return ModuleExecutionResult(
            execution_started=True,
            execution_finished=True,
            next_module_state=self.state,
            detail=detail,
            outcome=outcome,
            module_result=FollowModuleResult(status, detail=detail),
        )
