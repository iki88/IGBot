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
    AndroidFollowResult,
    AndroidFollowStatus,
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
        self.results = list(result) if isinstance(result, tuple) else [result]
        self.calls = []

    def next_candidate(self, context):
        self.calls.append(context)
        if self.results:
            return self.results.pop(0)
        return CandidateResult(CandidateResultStatus.ALL_SOURCES_EXHAUSTED)


class StubProfileProvider:
    def __init__(self, profile):
        self.profile = profile
        self.calls = []
        self.return_calls = []

    def open_profile(self, context, candidate):
        self.calls.append((context, candidate))
        return self.profile

    def return_to_followers(self, context):
        self.return_calls.append(context)
        return AndroidFollowResult(AndroidFollowStatus.SUCCESS)


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
    profile_provider=None,
    qualifier=None,
    hooks=None,
    contact_scraping_enabled=False,
    filters=None,
    daily_remaining=10,
    hourly_remaining=100_000,
    cancellation_requested=lambda: False,
):
    candidate = make_candidate()
    profile = profile or CandidateProfile(
        candidate,
        username=candidate.username,
        display_name=candidate.display_name or "",
        biography="Photography and travel",
    )
    candidate_provider = StubCandidateProvider(candidate_result)
    profile_provider = profile_provider or StubProfileProvider(profile)
    qualifier = qualifier or RecordingQualifier()
    hooks = hooks or RecordingHookManager()
    module = FollowModule(
        context,
        FollowModuleSettings(
            enabled=True,
            configured=True,
            budget=1,
            daily_remaining=daily_remaining,
            hourly_remaining=hourly_remaining,
            filters=filters or FollowFilterSettings(),
            contact_scraping_enabled=contact_scraping_enabled,
        ),
        candidate_provider,
        profile_provider,
        qualifier,
        hooks,
        cancellation_requested=cancellation_requested,
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
    assert [message for _level, message, _fields in context.logger.messages] == [
        "Follow candidate preparation started",
        "Candidate processing started",
        "Filter evaluation started",
        "Filter evaluation completed",
        "Follow candidate ready",
    ]


def test_specific_user_without_profile_filters_skips_qualifier(tmp_path):
    context = make_context(tmp_path)
    candidate = Candidate(
        "specific_user",
        "specific_users",
        CandidateProviderType.SPECIFIC_ACCOUNTS,
    )
    qualifier = RecordingQualifier()
    module, _provider, _profiles, _qualifier, _hooks = make_module(
        context,
        CandidateResult(CandidateResultStatus.CANDIDATE_FOUND, candidate),
        profile=CandidateProfile(candidate, username=candidate.username),
        qualifier=qualifier,
        filters=FollowFilterSettings(allow_private=True),
    )

    result = module.execute(context, make_budget())

    assert result.module_result.status is FollowModuleResultStatus.READY_TO_FOLLOW
    assert qualifier.calls == []
    assert context.logger.messages[-1] == (
        "info",
        "Follow candidate ready",
        {"username": "specific_user"},
    )


@pytest.mark.parametrize("timed_out", (False, True))
def test_source_session_counts_opened_profiles_and_loading_timeouts(
    tmp_path, timed_out
):
    context = make_context(tmp_path)
    module, provider, profiles, *_ = make_module(
        context,
        CandidateResult(CandidateResultStatus.CANDIDATE_FOUND, make_candidate()),
    )
    evaluated = []
    provider.record_evaluated = lambda context: evaluated.append(context)
    if timed_out:
        profiles.profile = None
        profiles.profile_loading_timed_out = True
    module.execute(context, make_budget())
    assert evaluated == ([] if timed_out else [context])


def test_three_loading_timeouts_abort_follow_without_source_evaluations(tmp_path):
    context = make_context(tmp_path)
    found = CandidateResult(CandidateResultStatus.CANDIDATE_FOUND, make_candidate())
    module, provider, profiles, qualifier, *_ = make_module(context, (found,) * 4)
    profiles.profile = None
    profiles.profile_loading_timed_out = True
    provider.record_evaluated = lambda _: pytest.fail("timeout counted as evaluation")
    module.execute(context, make_budget())
    assert module.consecutive_profile_timeouts == 3
    assert module.session_aborted
    assert not module.is_eligible()
    assert len(profiles.calls) == 3
    assert qualifier.calls == []
    assert any(
        message == "[Follow] Aborting current Follow session."
        for _, message, _ in context.logger.messages
    )


def test_ready_profile_resets_consecutive_loading_timeouts(tmp_path):
    context = make_context(tmp_path)
    found = CandidateResult(CandidateResultStatus.CANDIDATE_FOUND, make_candidate())
    module, *_ = make_module(context, found)
    module.consecutive_profile_timeouts = 2
    module.execute(context, make_budget())
    assert module.consecutive_profile_timeouts == 0
    assert not module.session_aborted


def test_specific_profile_timeout_continues_with_next_username(tmp_path):
    context = make_context(tmp_path)
    first = Candidate(
        "first_user", "specific_users", CandidateProviderType.SPECIFIC_ACCOUNTS
    )
    second = Candidate(
        "second_user", "specific_users", CandidateProviderType.SPECIFIC_ACCOUNTS
    )

    class SpecificProvider(StubCandidateProvider):
        def __init__(self):
            super().__init__(
                (
                    CandidateResult(CandidateResultStatus.CANDIDATE_FOUND, first),
                    CandidateResult(CandidateResultStatus.CANDIDATE_FOUND, second),
                )
            )
            self.processed = []

        def mark_processed(self, context):
            self.processed.append(context)

    class TimeoutThenReadyProfiles(StubProfileProvider):
        profile_loading_timed_out = False

        def open_profile(self, context, candidate):
            self.calls.append((context, candidate))
            self.profile_loading_timed_out = candidate is first
            if self.profile_loading_timed_out:
                return None
            return CandidateProfile(candidate, candidate.username)

    provider = SpecificProvider()
    profiles = TimeoutThenReadyProfiles(None)
    module, *_unused = make_module(
        context,
        CandidateResult(CandidateResultStatus.ALL_SOURCES_EXHAUSTED),
        profile_provider=profiles,
    )
    module._candidate_provider = provider

    result = module.execute(context, make_budget())

    assert result.module_result.status is FollowModuleResultStatus.READY_TO_FOLLOW
    assert result.module_result.candidate is second
    assert [candidate for _context, candidate in profiles.calls] == [first, second]
    assert provider.processed == [context]
    assert profiles.return_calls == []


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


def test_verified_follow_updates_daily_and_hourly_runtime_counters(tmp_path):
    context = make_context(tmp_path)
    candidate = make_candidate()
    module, *_ = make_module(
        context,
        CandidateResult(CandidateResultStatus.CANDIDATE_FOUND, candidate),
        daily_remaining=3,
        hourly_remaining=3,
    )

    assert module.record_verified_follow() == (False, False)
    assert module.daily_remaining == 2
    assert module.hourly_remaining == 2
    assert module.is_eligible() is True

    module.record_verified_follow()
    assert module.record_verified_follow() == (True, True)
    assert module.daily_remaining == 0
    assert module.hourly_remaining == 0
    assert module.is_eligible() is False


def test_hourly_limit_removes_follow_from_eligibility_before_daily_limit(tmp_path):
    context = make_context(tmp_path)
    candidate = make_candidate()
    module, *_ = make_module(
        context,
        CandidateResult(CandidateResultStatus.CANDIDATE_FOUND, candidate),
        daily_remaining=3,
        hourly_remaining=1,
    )

    assert module.record_verified_follow() == (False, True)
    assert module.daily_remaining == 2
    assert module.is_eligible() is False


def test_daily_limit_completion_returns_daily_limit_reached_immediately(tmp_path):
    context = make_context(tmp_path)
    candidate = make_candidate()
    module, *_ = make_module(
        context,
        CandidateResult(CandidateResultStatus.CANDIDATE_FOUND, candidate),
        daily_remaining=1,
        hourly_remaining=3,
    )

    outcome = module.complete_verified_follow()

    assert outcome is ModuleExecutionOutcome.DAILY_LIMIT_REACHED
    assert module.daily_remaining == 0
    assert module.is_eligible() is False


@pytest.mark.parametrize(
    ("cancel_on_call", "provider_calls", "profile_calls", "qualifier_calls"),
    (
        (1, 0, 0, 0),
        (2, 1, 0, 0),
        (3, 1, 1, 0),
        (4, 1, 1, 1),
    ),
)
def test_cancellation_is_checked_before_each_follow_preparation_stage(
    tmp_path, cancel_on_call, provider_calls, profile_calls, qualifier_calls
):
    context = make_context(tmp_path)
    candidate = make_candidate()

    class Cancellation:
        def __init__(self):
            self.calls = 0

        def __call__(self):
            self.calls += 1
            return self.calls == cancel_on_call

    cancellation = Cancellation()
    module, provider, profiles, qualifier, hooks = make_module(
        context,
        CandidateResult(CandidateResultStatus.CANDIDATE_FOUND, candidate),
        contact_scraping_enabled=True,
        cancellation_requested=cancellation,
    )

    result = module.execute(context, make_budget())

    assert result.module_result.status is FollowModuleResultStatus.CANCELLED
    assert len(provider.calls) == provider_calls
    assert len(profiles.calls) == profile_calls
    assert len(qualifier.calls) == qualifier_calls
    assert hooks.events == []
    if cancel_on_call >= 3:
        assert profiles.return_calls == [context]


@pytest.mark.parametrize(
    ("provider_status", "module_status", "scheduler_outcome"),
    (
        (
            CandidateResultStatus.FILTER_REJECTED,
            FollowModuleResultStatus.FILTER_REJECTED,
            ModuleExecutionOutcome.SUCCESS,
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


@pytest.mark.parametrize("discovery", ("Followers", "Following"))
def test_follow_module_immediately_continues_after_current_source_exhaustion(
    tmp_path, discovery
):
    context = make_context(tmp_path)
    candidate = make_candidate()
    module, provider, profiles, qualifier, hooks = make_module(
        context,
        (
            CandidateResult(
                CandidateResultStatus.CURRENT_SOURCE_EXHAUSTED,
                detail=f"{discovery} source exhausted",
            ),
            CandidateResult(CandidateResultStatus.CANDIDATE_FOUND, candidate),
        ),
    )

    result = module.execute(context, make_budget())

    assert result.module_result.status is FollowModuleResultStatus.READY_TO_FOLLOW
    assert result.module_result.candidate is candidate
    assert provider.calls == [context, context]
    assert len(profiles.calls) == 1
    assert len(qualifier.calls) == 1
    assert hooks.events == []


@pytest.mark.parametrize(
    ("profile", "settings", "expected"),
    (
        (
            {"username": "wrong_user"},
            {"username": TextFilterSettings(required=("not-present",))},
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


def test_follow_qualifier_skips_business_only_when_configured(tmp_path):
    context = make_context(tmp_path)
    candidate = make_candidate()
    profile = CandidateProfile(
        candidate,
        username=candidate.username,
        display_name="Business Name",
        category="Financial service",
        is_business=True,
    )
    qualifier = ConfiguredFollowCandidateQualifier()

    allowed = qualifier.qualify(context, profile, FollowFilterSettings())
    skipped = qualifier.qualify(
        context, profile, FollowFilterSettings(skip_business=True)
    )

    assert allowed.status is FollowModuleResultStatus.READY_TO_FOLLOW
    assert skipped.status is FollowModuleResultStatus.FILTER_REJECTED
    messages = [message for _level, message, _fields in context.logger.messages]
    assert "[Filter] Business profile detected." in messages
    assert "[Filter] Business profile skipped." in messages


def test_follow_qualifier_follows_only_business_profiles_when_configured(tmp_path):
    context = make_context(tmp_path)
    candidate = make_candidate()
    business = CandidateProfile(
        candidate,
        username=candidate.username,
        category="Financial service",
        is_business=True,
    )
    personal = CandidateProfile(candidate, username=candidate.username)
    qualifier = ConfiguredFollowCandidateQualifier()

    default_business = qualifier.qualify(context, business, FollowFilterSettings())
    default_personal = qualifier.qualify(context, personal, FollowFilterSettings())
    only_business = FollowFilterSettings(follow_only_business=True)
    accepted = qualifier.qualify(context, business, only_business)
    rejected = qualifier.qualify(context, personal, only_business)

    assert default_business.status is FollowModuleResultStatus.READY_TO_FOLLOW
    assert default_personal.status is FollowModuleResultStatus.READY_TO_FOLLOW
    assert accepted.status is FollowModuleResultStatus.READY_TO_FOLLOW
    assert rejected.status is FollowModuleResultStatus.FILTER_REJECTED
    assert any(
        message == "[Filter] Personal profile skipped."
        for _level, message, _fields in context.logger.messages
    )


def test_follow_qualifier_private_profile_modes(tmp_path):
    context = make_context(tmp_path)
    candidate = make_candidate()
    public = CandidateProfile(candidate, username=candidate.username)
    private = CandidateProfile(candidate, username=candidate.username, is_private=True)
    qualifier = ConfiguredFollowCandidateQualifier()

    default_public = qualifier.qualify(context, public, FollowFilterSettings())
    default_private = qualifier.qualify(context, private, FollowFilterSettings())
    allow_private = FollowFilterSettings(allow_private=True)
    allowed_public = qualifier.qualify(context, public, allow_private)
    allowed_private = qualifier.qualify(context, private, allow_private)
    only_private = FollowFilterSettings(follow_only_private=True)
    rejected_public = qualifier.qualify(context, public, only_private)
    accepted_private = qualifier.qualify(context, private, only_private)

    assert default_public.status is FollowModuleResultStatus.READY_TO_FOLLOW
    assert default_private.status is FollowModuleResultStatus.PRIVATE_SKIPPED
    assert allowed_public.status is FollowModuleResultStatus.READY_TO_FOLLOW
    assert allowed_private.status is FollowModuleResultStatus.READY_TO_FOLLOW
    assert rejected_public.status is FollowModuleResultStatus.FILTER_REJECTED
    assert accepted_private.status is FollowModuleResultStatus.READY_TO_FOLLOW
    assert any(
        message == "[Filter] Public profile skipped."
        for _level, message, _fields in context.logger.messages
    )


def test_follow_qualifier_link_in_bio_modes(tmp_path):
    context = make_context(tmp_path)
    candidate = make_candidate()
    without_link = CandidateProfile(candidate, username=candidate.username)
    with_link = CandidateProfile(
        candidate,
        username=candidate.username,
        website="https://example.com",
        has_external_links=True,
    )
    qualifier = ConfiguredFollowCandidateQualifier()

    assert (
        qualifier.qualify(context, without_link, FollowFilterSettings()).status
        is FollowModuleResultStatus.READY_TO_FOLLOW
    )
    assert (
        qualifier.qualify(context, with_link, FollowFilterSettings()).status
        is FollowModuleResultStatus.READY_TO_FOLLOW
    )
    assert (
        qualifier.qualify(
            context, with_link, FollowFilterSettings(skip_link_in_bio=True)
        ).status
        is FollowModuleResultStatus.FILTER_REJECTED
    )
    only_link = FollowFilterSettings(follow_only_link_in_bio=True)
    assert (
        qualifier.qualify(context, without_link, only_link).status
        is FollowModuleResultStatus.FILTER_REJECTED
    )
    assert (
        qualifier.qualify(context, with_link, only_link).status
        is FollowModuleResultStatus.READY_TO_FOLLOW
    )


def test_keyword_filters_search_one_combined_normalized_profile(tmp_path):
    context = make_context(tmp_path)
    candidate = make_candidate()
    profile = CandidateProfile(
        candidate,
        username="target_user",
        display_name="Renova Energy",
        biography="Independent advice",
        category="Financial Service",
    )
    qualifier = ConfiguredFollowCandidateQualifier()

    accepted = qualifier.qualify(
        context,
        profile,
        FollowFilterSettings(
            keywords=TextFilterSettings(required=("FINANCIAL service",))
        ),
    )
    rejected = qualifier.qualify(
        context,
        profile,
        FollowFilterSettings(
            keywords=TextFilterSettings(blocked=("energy independent",))
        ),
    )

    assert accepted.status is FollowModuleResultStatus.READY_TO_FOLLOW
    assert rejected.status is FollowModuleResultStatus.FILTER_REJECTED


@pytest.mark.parametrize(
    ("text", "allowed", "expected"),
    (
        ("München", ("Latin",), FollowModuleResultStatus.READY_TO_FOLLOW),
        ("Москва", ("Latin",), FollowModuleResultStatus.FILTER_REJECTED),
        ("Москва", ("Cyrillic",), FollowModuleResultStatus.READY_TO_FOLLOW),
        ("東京 カフェ", ("Japanese",), FollowModuleResultStatus.READY_TO_FOLLOW),
        ("서울", ("Korean",), FollowModuleResultStatus.READY_TO_FOLLOW),
        ("नमस्ते", ("Hindi",), FollowModuleResultStatus.READY_TO_FOLLOW),
    ),
)
def test_allowed_alphabet_uses_cached_unicode_script_ranges(
    tmp_path, text, allowed, expected
):
    context = make_context(tmp_path)
    candidate = make_candidate()
    profile = CandidateProfile(candidate, username="latin_username", display_name=text)

    result = ConfiguredFollowCandidateQualifier().qualify(
        context, profile, FollowFilterSettings(allowed_alphabets=allowed)
    )

    assert result.status is expected


def test_biography_language_detector_is_lazy_and_runs_last(tmp_path):
    context = make_context(tmp_path)
    candidate = make_candidate()
    profile = CandidateProfile(
        candidate,
        username=candidate.username,
        display_name="Deutsches Profil",
        biography="Fotografie und Reisen in Deutschland",
    )
    detected = []
    qualifier = ConfiguredFollowCandidateQualifier(
        lambda text: detected.append(text) or "de"
    )

    without_filter = qualifier.qualify(context, profile, FollowFilterSettings())
    with_filter = qualifier.qualify(
        context,
        profile,
        FollowFilterSettings(biography_languages=("de",)),
    )
    rejected_before_language = qualifier.qualify(
        context,
        profile,
        FollowFilterSettings(
            keywords=TextFilterSettings(blocked=("fotografie",)),
            biography_languages=("de",),
        ),
    )

    assert without_filter.status is FollowModuleResultStatus.READY_TO_FOLLOW
    assert with_filter.status is FollowModuleResultStatus.READY_TO_FOLLOW
    assert rejected_before_language.status is FollowModuleResultStatus.FILTER_REJECTED
    assert detected == ["Deutsches Profil Fotografie und Reisen in Deutschland"]


def test_numeric_filters_run_before_language_detection(tmp_path):
    context = make_context(tmp_path)
    candidate = make_candidate()
    profile = CandidateProfile(candidate, username=candidate.username, followers=5)
    detected = []
    qualifier = ConfiguredFollowCandidateQualifier(
        lambda text: detected.append(text) or "en"
    )

    result = qualifier.qualify(
        context,
        profile,
        FollowFilterSettings(min_followers=10, biography_languages=("en",)),
    )

    assert result.status is FollowModuleResultStatus.FILTER_REJECTED
    assert detected == []


def test_link_in_bio_filter_uses_scraped_profile_state(tmp_path):
    context = make_context(tmp_path)
    candidate = make_candidate()
    profile = CandidateProfile(
        candidate,
        username=candidate.username,
        website="https://example.com",
        has_external_links=True,
    )
    qualifier = ConfiguredFollowCandidateQualifier()

    allowed = qualifier.qualify(context, profile, FollowFilterSettings())
    rejected = qualifier.qualify(
        context, profile, FollowFilterSettings(skip_link_in_bio=True)
    )

    assert allowed.status is FollowModuleResultStatus.READY_TO_FOLLOW
    assert rejected.status is FollowModuleResultStatus.FILTER_REJECTED
    assert rejected.detail == "Profile exposes one or more external links."
    assert any(
        message == "[Filter] Link in Bio detected. Candidate skipped."
        for _level, message, _fields in context.logger.messages
    )


@pytest.mark.parametrize(
    ("profile_values", "settings", "expected_log"),
    (
        (
            {"followers": 9},
            {"min_followers": 10},
            "[Filter] Minimum followers not satisfied. Candidate skipped.",
        ),
        (
            {"followers": 101},
            {"max_followers": 100},
            "[Filter] Maximum followers exceeded. Candidate skipped.",
        ),
        (
            {"posts": 2},
            {"min_posts": 3},
            "[Filter] Minimum posts not satisfied. Candidate skipped.",
        ),
    ),
)
def test_numeric_filter_rejections_explain_the_exact_boundary(
    tmp_path, profile_values, settings, expected_log
):
    context = make_context(tmp_path)
    candidate = make_candidate()
    profile = CandidateProfile(
        candidate,
        username=candidate.username,
        **profile_values,
    )

    result = ConfiguredFollowCandidateQualifier().qualify(
        context, profile, FollowFilterSettings(**settings)
    )

    assert result.status is FollowModuleResultStatus.FILTER_REJECTED
    assert any(
        message == expected_log for _level, message, _fields in context.logger.messages
    )


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

    assert result.module_result.status is FollowModuleResultStatus.NO_CANDIDATES
    assert hooks.events == []
    assert (
        "info",
        "Filter evaluation stopped candidate processing",
        {
            "username": "target_user",
            "status": "PRIVATE_SKIPPED",
            "detail": "Private account rejected.",
        },
    ) in context.logger.messages
    assert _profiles.return_calls == [context]


def test_filter_rejection_returns_to_followers_and_continues_candidate(tmp_path):
    context = make_context(tmp_path)
    rejected = make_candidate()
    accepted = Candidate(
        "next_target",
        "source_account",
        CandidateProviderType.FOLLOWERS,
    )

    class SequenceProfiles(StubProfileProvider):
        def open_profile(self, context, candidate):
            self.calls.append((context, candidate))
            return CandidateProfile(candidate, candidate.username)

    class SequenceQualifier:
        def __init__(self):
            self.calls = 0

        def qualify(self, context, profile, settings):
            self.calls += 1
            status = (
                FollowModuleResultStatus.PRIVATE_SKIPPED
                if self.calls == 1
                else FollowModuleResultStatus.READY_TO_FOLLOW
            )
            return FollowQualificationResult(status)

    profiles = SequenceProfiles(None)
    module, provider, _unused, qualifier, hooks = make_module(
        context,
        (
            CandidateResult(CandidateResultStatus.CANDIDATE_FOUND, rejected),
            CandidateResult(CandidateResultStatus.CANDIDATE_FOUND, accepted),
        ),
        profile_provider=profiles,
        qualifier=SequenceQualifier(),
    )

    result = module.execute(context, make_budget())

    assert result.module_result.status is FollowModuleResultStatus.READY_TO_FOLLOW
    assert result.module_result.candidate is accepted
    assert provider.calls == [context, context]
    assert profiles.return_calls == [context]
    assert qualifier.calls == 2
    assert hooks.events == []
    messages = [message for _level, message, _fields in context.logger.messages]
    assert "[Candidate] Continuing with next candidate" in messages


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
