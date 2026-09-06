"""Follow Module workflow through the pre-interaction boundary."""

from __future__ import annotations

from datetime import datetime

from IGBot.runtime.candidates import (
    CandidateProvider,
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
    ) -> None:
        self._context = context
        self._settings = settings
        self._candidate_provider = candidate_provider
        self._profile_provider = profile_provider
        self._qualifier = qualifier
        self._hook_manager = hook_manager
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
        return self._settings.daily_remaining

    def is_eligible(self) -> bool:
        return self._state.is_eligible()

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
        context.logger.debug("Follow candidate preparation started")
        discovered = self._candidate_provider.next_candidate(context)
        if discovered.status is CandidateResultStatus.SCROLL_BLOCK:
            return self._result(
                FollowModuleResultStatus.SCROLL_BLOCK,
                ModuleExecutionOutcome.SCROLL_BLOCK,
                discovered.detail,
            )
        if discovered.status in (
            CandidateResultStatus.CURRENT_SOURCE_EXHAUSTED,
            CandidateResultStatus.ALL_SOURCES_EXHAUSTED,
        ):
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
        profile = self._profile_provider.open_profile(context, candidate)
        if profile is None:
            return self._result(
                FollowModuleResultStatus.FILTER_REJECTED,
                detail=f"Candidate profile could not be opened: {candidate.username}",
            )
        qualification = self._qualifier.qualify(
            context, profile, self._settings.filters
        )
        if qualification.status is not FollowModuleResultStatus.READY_TO_FOLLOW:
            return self._result(qualification.status, detail=qualification.detail)

        hook_results = ()
        if self._settings.contact_scraping_enabled:
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
