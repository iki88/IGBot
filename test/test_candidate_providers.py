from datetime import datetime, timezone
from uuid import uuid4

import pytest

from IGBot.runtime import RuntimeContext, SessionContext
from IGBot.runtime.candidates import (
    Candidate,
    CandidateObservation,
    CandidateProvider,
    CandidateProviderType,
    CandidateResult,
    CandidateResultStatus,
    DiscoveryResult,
    DiscoveryStatus,
    FollowersDiscoverySettings,
    FollowersProvider,
    SpecificAccountsProvider,
)


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


class RecordingFilter:
    def __init__(self, *, visible=True, biography_required=False, biography=True):
        self.biography_required = biography_required
        self.visible = visible
        self.biography = biography
        self.calls = []

    def accepts_visible(self, context, candidate):
        self.calls.append(("visible", context, candidate))
        return self.visible

    def accepts_biography(self, context, candidate, biography):
        self.calls.append(("biography", context, candidate, biography))
        return self.biography


class RecordingProfileReader:
    def __init__(self, biography="profile bio"):
        self.value = biography
        self.calls = []

    def biography(self, context, username):
        self.calls.append((context, username))
        return self.value


class SequenceFollowersDiscovery:
    def __init__(self, results, *, openable=True):
        self.results = list(results)
        self.openable = openable
        self.open_calls = []
        self.next_calls = []

    def open_source(self, context, source):
        self.open_calls.append((context, source))
        return self.openable

    def next_follower(self, context, source, settings):
        self.next_calls.append((context, source, settings))
        return self.results.pop(0)


class RecordingSpecificDiscovery:
    def __init__(self, observations):
        self.observations = list(observations)
        self.calls = []

    def open_account(self, context, username):
        self.calls.append((context, username))
        return self.observations.pop(0)


def make_context(tmp_path):
    return RuntimeContext(
        SessionContext(
            session_id=uuid4(),
            account_username="operator_account",
            phone_id="phone-1",
            application_id="com.instagram.clone",
            account_directory=tmp_path,
            created_at=datetime.now(timezone.utc),
        ),
        StubLogger(),
    )


def make_followers_provider(discovery, candidate_filter=None, profile=None):
    return FollowersProvider(
        ("source_account",),
        discovery,
        candidate_filter or RecordingFilter(),
        profile or RecordingProfileReader(),
        FollowersDiscoverySettings(
            scrolling_timeout_seconds=90,
            use_random_search_letters=True,
            first_character_pool="abc",
            second_character_pool="aeiou",
        ),
    )


def test_candidate_provider_contract_has_one_common_entry_point():
    assert CandidateProvider.next_candidate.__name__ == "next_candidate"


def test_candidate_and_result_enforce_structured_found_outcome():
    candidate = Candidate(
        "target_user",
        "source_account",
        CandidateProviderType.FOLLOWERS,
        "Target User",
    )

    result = CandidateResult(CandidateResultStatus.CANDIDATE_FOUND, candidate=candidate)

    assert result.candidate is candidate
    with pytest.raises(ValueError, match="requires a candidate"):
        CandidateResult(CandidateResultStatus.CANDIDATE_FOUND)
    with pytest.raises(ValueError, match="other statuses forbid"):
        CandidateResult(CandidateResultStatus.FILTER_REJECTED, candidate=candidate)


def test_followers_provider_passes_scrolling_policy_and_returns_candidate(tmp_path):
    context = make_context(tmp_path)
    discovery = SequenceFollowersDiscovery(
        (
            DiscoveryResult(
                DiscoveryStatus.ACCOUNT_FOUND,
                CandidateObservation("target_user", "Target User"),
            ),
        )
    )
    provider = make_followers_provider(discovery)

    result = provider.next_candidate(context)

    assert result.status is CandidateResultStatus.CANDIDATE_FOUND
    assert result.candidate == Candidate(
        "target_user",
        "source_account",
        CandidateProviderType.FOLLOWERS,
        "Target User",
    )
    assert discovery.open_calls == [(context, "source_account")]
    settings = discovery.next_calls[0][2]
    assert settings.scrolling_timeout_seconds == 90
    assert settings.use_random_search_letters is True
    assert settings.first_character_pool == "abc"


def test_followers_provider_reports_source_progression(tmp_path):
    context = make_context(tmp_path)
    discovery = SequenceFollowersDiscovery(
        (
            DiscoveryResult(DiscoveryStatus.SOURCE_EXHAUSTED),
            DiscoveryResult(DiscoveryStatus.SOURCE_EXHAUSTED),
        )
    )
    provider = FollowersProvider(
        ("source_one", "source_two"),
        discovery,
        RecordingFilter(),
        RecordingProfileReader(),
        FollowersDiscoverySettings(60),
    )

    first = provider.next_candidate(context)
    second = provider.next_candidate(context)

    assert first.status is CandidateResultStatus.CURRENT_SOURCE_EXHAUSTED
    assert second.status is CandidateResultStatus.ALL_SOURCES_EXHAUSTED
    assert [call[1] for call in discovery.open_calls] == [
        "source_one",
        "source_two",
    ]


def test_followers_provider_reports_scroll_block_without_scheduler_state(tmp_path):
    context = make_context(tmp_path)
    discovery = SequenceFollowersDiscovery(
        (DiscoveryResult(DiscoveryStatus.SCROLL_BLOCK, detail="restricted"),)
    )

    result = make_followers_provider(discovery).next_candidate(context)

    assert result == CandidateResult(
        CandidateResultStatus.SCROLL_BLOCK, detail="restricted"
    )
    assert context.logger.messages[-1][1] == "Candidate source scrolling blocked"


def test_visible_rejection_does_not_open_profile(tmp_path):
    context = make_context(tmp_path)
    discovery = SequenceFollowersDiscovery(
        (
            DiscoveryResult(
                DiscoveryStatus.ACCOUNT_FOUND,
                CandidateObservation("rejected_user"),
            ),
        )
    )
    candidate_filter = RecordingFilter(visible=False, biography_required=True)
    profile = RecordingProfileReader()

    result = make_followers_provider(
        discovery, candidate_filter, profile
    ).next_candidate(context)

    assert result.status is CandidateResultStatus.FILTER_REJECTED
    assert profile.calls == []


def test_biography_filter_opens_profile_only_after_visible_filters(tmp_path):
    context = make_context(tmp_path)
    discovery = SequenceFollowersDiscovery(
        (
            DiscoveryResult(
                DiscoveryStatus.ACCOUNT_FOUND,
                CandidateObservation("bio_user"),
            ),
        )
    )
    candidate_filter = RecordingFilter(biography_required=True, biography=False)
    profile = RecordingProfileReader("blocked biography")

    result = make_followers_provider(
        discovery, candidate_filter, profile
    ).next_candidate(context)

    assert result.status is CandidateResultStatus.FILTER_REJECTED
    assert [call[0] for call in candidate_filter.calls] == [
        "visible",
        "biography",
    ]
    assert profile.calls == [(context, "bio_user")]


def test_specific_accounts_provider_reads_list_without_scrolling(tmp_path):
    context = make_context(tmp_path)
    discovery = RecordingSpecificDiscovery(
        (CandidateObservation("specific_user", "Specific User"),)
    )
    provider = SpecificAccountsProvider(
        ("specific_user",),
        discovery,
        RecordingFilter(),
        RecordingProfileReader(),
    )

    found = provider.next_candidate(context)
    exhausted = provider.next_candidate(context)

    assert found.candidate == Candidate(
        "specific_user",
        "specific_user",
        CandidateProviderType.SPECIFIC_ACCOUNTS,
        "Specific User",
    )
    assert exhausted.status is CandidateResultStatus.ALL_SOURCES_EXHAUSTED
    assert discovery.calls == [(context, "specific_user")]


def test_specific_account_failure_is_structured_and_advances(tmp_path):
    context = make_context(tmp_path)
    discovery = RecordingSpecificDiscovery((None,))
    provider = SpecificAccountsProvider(
        ("missing_user",),
        discovery,
        RecordingFilter(),
        RecordingProfileReader(),
    )

    rejected = provider.next_candidate(context)
    exhausted = provider.next_candidate(context)

    assert rejected.status is CandidateResultStatus.FILTER_REJECTED
    assert exhausted.status is CandidateResultStatus.ALL_SOURCES_EXHAUSTED


def test_followers_settings_reject_non_positive_timeout():
    with pytest.raises(ValueError, match="positive"):
        FollowersDiscoverySettings(0)
