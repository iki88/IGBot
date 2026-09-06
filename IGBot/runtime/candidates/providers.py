"""Candidate providers used by interaction modules."""

from __future__ import annotations

from collections.abc import Iterable

from IGBot.runtime.candidates.contracts import (
    CandidateFilter,
    CandidateProfileReader,
    FollowersDiscovery,
    SpecificAccountDiscovery,
)
from IGBot.runtime.candidates.models import (
    Candidate,
    CandidateProviderType,
    CandidateResult,
    CandidateResultStatus,
    DiscoveryStatus,
    FollowersDiscoverySettings,
)
from IGBot.runtime.candidates.qualifier import CandidateQualifier
from IGBot.runtime.context import RuntimeContext


class FollowersProvider:
    """Discover filtered candidates from configured followers sources."""

    def __init__(
        self,
        sources: Iterable[str],
        discovery: FollowersDiscovery,
        candidate_filter: CandidateFilter,
        profile_reader: CandidateProfileReader,
        settings: FollowersDiscoverySettings,
    ) -> None:
        self._sources = self._clean_entries(sources)
        self._discovery = discovery
        self._qualifier = CandidateQualifier(candidate_filter, profile_reader)
        self._settings = settings
        self._source_index = 0
        self._source_open = False

    def next_candidate(self, context: RuntimeContext) -> CandidateResult:
        """Inspect one follower row and return a structured provider outcome."""

        if self._source_index >= len(self._sources):
            return CandidateResult(CandidateResultStatus.ALL_SOURCES_EXHAUSTED)

        source = self._sources[self._source_index]
        if not self._source_open:
            if not self._discovery.open_source(context, source):
                return self._finish_source(
                    detail=f"Followers source could not be opened: {source}"
                )
            self._source_open = True

        discovered = self._discovery.next_follower(context, source, self._settings)
        if discovered.status is DiscoveryStatus.SOURCE_EXHAUSTED:
            return self._finish_source(discovered.detail)
        if discovered.status is DiscoveryStatus.SCROLL_BLOCK:
            context.logger.warning("Candidate source scrolling blocked", source=source)
            return CandidateResult(
                CandidateResultStatus.SCROLL_BLOCK, detail=discovered.detail
            )

        observation = discovered.observation
        if observation is None:
            raise RuntimeError("Follower discovery returned no account observation")
        candidate = Candidate(
            username=observation.username,
            display_name=observation.display_name,
            source=source,
            provider_type=CandidateProviderType.FOLLOWERS,
        )
        return self._qualifier.qualify(context, candidate)

    def _finish_source(self, detail: str | None = None) -> CandidateResult:
        self._source_index += 1
        self._source_open = False
        status = (
            CandidateResultStatus.ALL_SOURCES_EXHAUSTED
            if self._source_index >= len(self._sources)
            else CandidateResultStatus.CURRENT_SOURCE_EXHAUSTED
        )
        return CandidateResult(status, detail=detail)

    @staticmethod
    def _clean_entries(entries: Iterable[str]) -> tuple[str, ...]:
        return tuple(entry.strip() for entry in entries if entry.strip())


class SpecificAccountsProvider:
    """Discover filtered candidates from a configured username list."""

    def __init__(
        self,
        usernames: Iterable[str],
        discovery: SpecificAccountDiscovery,
        candidate_filter: CandidateFilter,
        profile_reader: CandidateProfileReader,
    ) -> None:
        self._usernames = FollowersProvider._clean_entries(usernames)
        self._discovery = discovery
        self._qualifier = CandidateQualifier(candidate_filter, profile_reader)
        self._index = 0

    def next_candidate(self, context: RuntimeContext) -> CandidateResult:
        """Open and qualify the next configured username without scrolling."""

        if self._index >= len(self._usernames):
            return CandidateResult(CandidateResultStatus.ALL_SOURCES_EXHAUSTED)

        username = self._usernames[self._index]
        self._index += 1
        observation = self._discovery.open_account(context, username)
        if observation is None:
            return CandidateResult(
                CandidateResultStatus.FILTER_REJECTED,
                detail=f"Specific account could not be read: {username}",
            )

        candidate = Candidate(
            username=observation.username,
            display_name=observation.display_name,
            source=username,
            provider_type=CandidateProviderType.SPECIFIC_ACCOUNTS,
        )
        return self._qualifier.qualify(context, candidate)
