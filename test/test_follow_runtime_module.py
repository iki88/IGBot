from datetime import datetime, timezone
from uuid import uuid4

import pytest

from IGBot.runtime import RuntimeContext, SessionContext
from IGBot.runtime.candidates import (
    Candidate,
    CandidateProviderType,
    CandidateResult,
    CandidateResultStatus,
)
from IGBot.runtime.follow import (
    CandidateProfile,
    ConfiguredFollowCandidateQualifier,
    FollowFilterSettings,
    FollowModule,
    FollowModuleExecutor,
    FollowModuleResultStatus,
    FollowModuleSettings,
    FollowQualificationResult,
    TextFilterSettings,
)
from IGBot.runtime.hooks import HookResult
from IGBot.runtime.modules import InteractionModule
from IGBot.runtime.scheduler import (
    BudgetCalculator,
    ExecutionBudget,
    ExecutionCoordinator,
    ModuleExecutionOutcome,
    ModulePoolBuilder,
    ModuleSelector,
    Scheduler,
)
from IGBot.runtime.state import ModuleState


class StubLogger:
    def __init__(self):
        self.messages = []

    def debug(self, message, **fields):
        self.messages.append(("debug", message, fields))

    def info(self, message, **fields):
        self.messages.append(("info", message, fields))

    def warning(self, message, **fields):
        self.messages.append(("warning", message, fields))

    def error(self, message, **fields):
        self.messages.append(("error", message, fields))


class StubCandidateProvider:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def next_candidate(self, context):
        self.calls.append(context)
        return self.result


class StubProfileProvider:
    def __init__(self, profile):
        self.profile = profile
        self.calls = []

    def open_profile(self, context, candidate):
        self.calls.append((context, candidate))
        return self.profile


class RecordingQualifier:
    def __init__(self, result=None):
        self.result = result or FollowQualificationResult(
            FollowModuleResultStatus.READY_TO_FOLLOW
        )
        self.calls = []

    def qualify(self, context, profile, settings):
        self.calls.append((context, profile, settings))
        return self.result


class RecordingHookManager:
    def __init__(self):
        self.events = []

    def dispatch(self, event):
        self.events.append(event)
        return (HookResult(True, "Contact profile inspected."),)


def make_context(tmp_path):
    return RuntimeContext(
        SessionContext(
            session_id=uuid4(),
            account_username="account",
            phone_id="phone-1",
            application_id="com.instagram.clone",
            account_directory=tmp_path,
            created_at=datetime.now(timezone.utc),
        ),
        StubLogger(),
    )


def make_candidate():
    return Candidate(
        "target_user",
        "source_account",
        CandidateProviderType.FOLLOWERS,
        "Target Name",
    )


def make_budget(final=1):
    return ExecutionBudget(
        InteractionModule.FOLLOW,
        configured="1",
        resolved=1,
        daily_remaining=10,
        final=final,
    )


def make_module(
    context,
    candidate_result,
    *,
    profile=None,
    qualifier=None,
    hooks=None,
    contact_scraping_enabled=False,
    filters=None,
):
    candidate = make_candidate()
    profile = profile or CandidateProfile(
        candidate,
        username=candidate.username,
        display_name=candidate.display_name or "",
        biography="Photography and travel",
    )
    candidate_provider = StubCandidateProvider(candidate_result)
    profile_provider = StubProfileProvider(profile)
    qualifier = qualifier or RecordingQualifier()
    hooks = hooks or RecordingHookManager()
    module = FollowModule(
        context,
        FollowModuleSettings(
            enabled=True,
            configured=True,
            budget=1,
            daily_remaining=10,
            filters=filters or FollowFilterSettings(),
            contact_scraping_enabled=contact_scraping_enabled,
        ),
        candidate_provider,
        profile_provider,
        qualifier,
        hooks,
    )
    return module, candidate_provider, profile_provider, qualifier, hooks


def test_follow_module_prepares_candidate_and_runs_enabled_profile_hooks(tmp_path):
    context = make_context(tmp_path)
    candidate = make_candidate()
    module, provider, profiles, qualifier, hooks = make_module(
        context,
        CandidateResult(CandidateResultStatus.CANDIDATE_FOUND, candidate),
        contact_scraping_enabled=True,
    )

    result = module.execute(context, make_budget())

    assert result.outcome is ModuleExecutionOutcome.SUCCESS
    assert result.module_result.status is FollowModuleResultStatus.READY_TO_FOLLOW
    assert result.module_result.candidate is candidate
    assert len(result.module_result.hook_results) == 1
    assert provider.calls == [context]
    assert profiles.calls == [(context, candidate)]
    assert qualifier.calls[0][0] is context
    assert hooks.events[0].payload["candidate"] is candidate
    assert context.logger.messages[-1] == (
        "info",
        "Follow candidate ready",
        {"username": "target_user"},
    )


def test_follow_module_does_not_dispatch_hooks_when_contact_scraping_is_disabled(
    tmp_path,
):
    context = make_context(tmp_path)
    candidate = make_candidate()
    module, _provider, _profiles, _qualifier, hooks = make_module(
        context,
        CandidateResult(CandidateResultStatus.CANDIDATE_FOUND, candidate),
    )

    result = module.execute(context, make_budget())

    assert result.module_result.status is FollowModuleResultStatus.READY_TO_FOLLOW
    assert hooks.events == []


@pytest.mark.parametrize(
    ("provider_status", "module_status", "scheduler_outcome"),
    (
        (
            CandidateResultStatus.FILTER_REJECTED,
            FollowModuleResultStatus.FILTER_REJECTED,
            ModuleExecutionOutcome.SUCCESS,
        ),
        (
            CandidateResultStatus.CURRENT_SOURCE_EXHAUSTED,
            FollowModuleResultStatus.NO_CANDIDATES,
            ModuleExecutionOutcome.NO_CANDIDATES,
        ),
        (
            CandidateResultStatus.ALL_SOURCES_EXHAUSTED,
            FollowModuleResultStatus.NO_CANDIDATES,
            ModuleExecutionOutcome.NO_CANDIDATES,
        ),
        (
            CandidateResultStatus.SCROLL_BLOCK,
            FollowModuleResultStatus.SCROLL_BLOCK,
            ModuleExecutionOutcome.SCROLL_BLOCK,
        ),
    ),
)
def test_follow_module_maps_candidate_provider_results(
    tmp_path, provider_status, module_status, scheduler_outcome
):
    context = make_context(tmp_path)
    module, _provider, profiles, qualifier, hooks = make_module(
        context, CandidateResult(provider_status, detail="provider result")
    )

    result = module.execute(context, make_budget())

    assert result.module_result.status is module_status
    assert result.outcome is scheduler_outcome
    assert profiles.calls == []
    assert qualifier.calls == []
    assert hooks.events == []


@pytest.mark.parametrize(
    ("profile", "settings", "expected"),
    (
        (
            {"username": "wrong_user"},
            {"username": TextFilterSettings(required=("target",))},
            FollowModuleResultStatus.FILTER_REJECTED,
        ),
        (
            {"display_name": "Blocked Name"},
            {"display_name": TextFilterSettings(blocked=("blocked",))},
            FollowModuleResultStatus.FILTER_REJECTED,
        ),
        (
            {"biography": "No matching subject"},
            {"biography": TextFilterSettings(required=("photography",))},
            FollowModuleResultStatus.FILTER_REJECTED,
        ),
        (
            {"is_private": True},
            {"allow_private": False},
            FollowModuleResultStatus.PRIVATE_SKIPPED,
        ),
    ),
)
def test_configured_qualifier_applies_follow_filters(
    tmp_path, profile, settings, expected
):
    context = make_context(tmp_path)
    candidate = make_candidate()
    values = {
        "candidate": candidate,
        "username": candidate.username,
        "display_name": candidate.display_name or "",
        "biography": "Photography and travel",
        "is_private": False,
    }
    values.update(profile)

    result = ConfiguredFollowCandidateQualifier().qualify(
        context,
        CandidateProfile(**values),
        FollowFilterSettings(**settings),
    )

    assert result.status is expected


def test_profile_qualification_result_is_returned_without_hooks(tmp_path):
    context = make_context(tmp_path)
    candidate = make_candidate()
    qualifier = RecordingQualifier(
        FollowQualificationResult(
            FollowModuleResultStatus.PRIVATE_SKIPPED,
            "Private account rejected.",
        )
    )
    module, _provider, _profiles, _qualifier, hooks = make_module(
        context,
        CandidateResult(CandidateResultStatus.CANDIDATE_FOUND, candidate),
        qualifier=qualifier,
        contact_scraping_enabled=True,
    )

    result = module.execute(context, make_budget())

    assert result.module_result.status is FollowModuleResultStatus.PRIVATE_SKIPPED
    assert result.detail == "Private account rejected."
    assert hooks.events == []


def test_scheduler_can_execute_follow_module_through_common_contract(tmp_path):
    context = make_context(tmp_path)
    candidate = make_candidate()
    module, _provider, _profiles, _qualifier, _hooks = make_module(
        context,
        CandidateResult(CandidateResultStatus.CANDIDATE_FOUND, candidate),
    )
    scheduler = Scheduler(
        ModulePoolBuilder(),
        ModuleSelector(chooser=lambda pool: pool[0]),
        BudgetCalculator(),
        ExecutionCoordinator(FollowModuleExecutor(module)),
    )

    result = scheduler.evaluate_once(context, (module,))

    assert result.selected_module is InteractionModule.FOLLOW
    assert result.module_result.status is FollowModuleResultStatus.READY_TO_FOLLOW
    assert result.next_module_state is ModuleState.READY


def test_follow_module_rejects_wrong_context_and_budget(tmp_path):
    context = make_context(tmp_path)
    candidate = make_candidate()
    module, *_unused = make_module(
        context,
        CandidateResult(CandidateResultStatus.CANDIDATE_FOUND, candidate),
    )

    with pytest.raises(ValueError, match="different RuntimeContext"):
        module.execute(make_context(tmp_path), make_budget())
    wrong_budget = ExecutionBudget(InteractionModule.LIKE, "1", 1, 1, 1)
    with pytest.raises(ValueError, match="Follow execution budget"):
        module.execute(context, wrong_budget)
    with pytest.raises(ValueError, match="positive execution budget"):
        module.execute(context, make_budget(final=0))
