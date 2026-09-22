"""Candidate providers used by interaction modules."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

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
from IGBot.runtime.database import RuntimeDatabase, SpecificProgress


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

        failed_sources: list[str] = []
        while self._source_index < len(self._sources) and not self._source_open:
            source = self._sources[self._source_index]
            self._source_selected(context, source)
            if self._discovery.open_source(context, source):
                self._source_open = True
                break
            failed_sources.append(source)
            self._source_index += 1
            context.logger.warning(
                "[Search] Source failed. Trying next configured source.", source=source
            )

        if self._source_index >= len(self._sources):
            if failed_sources:
                context.logger.warning(
                    "[Search] All configured sources exhausted.",
                    failed_sources=", ".join(failed_sources),
                )
            return CandidateResult(
                CandidateResultStatus.ALL_SOURCES_EXHAUSTED,
                detail=(
                    "Every configured source failed: " + ", ".join(failed_sources)
                    if failed_sources
                    else None
                ),
            )

        source = self._sources[self._source_index]

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

    def _source_selected(self, context: RuntimeContext, source: str) -> None:
        """Allow module-specific summary logging without changing selection."""

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


class SpecificUsersProvider:
    """Supply account-local Follow Specific Users with a persistent cursor."""

    def __init__(
        self, account_directory: str | Path, discovery: SpecificAccountDiscovery
    ) -> None:
        self._account_directory = Path(account_directory)
        self._discovery = discovery
        self._current_username: str | None = None

    def next_candidate(self, context: RuntimeContext) -> CandidateResult:
        usernames = self._usernames()
        with RuntimeDatabase(self._account_directory) as database:
            progress = database.specific_progress.get("follow") or SpecificProgress(
                "follow"
            )
        if progress.completed or progress.current_position >= len(usernames):
            self._complete(context, len(usernames))
            return CandidateResult(CandidateResultStatus.ALL_SOURCES_EXHAUSTED)

        context.logger.info("[Specific] Starting Follow Specific Users.")
        context.logger.info(f"[Specific] Current position: {progress.current_position}")
        position = progress.current_position
        while position < len(usernames):
            username = usernames[position]
            context.logger.info(f"[Specific] Username: {username}")
            context.logger.info("[Specific] Opening candidate profile.")
            observation = self._discovery.open_account(context, username)
            if observation is not None:
                self._current_username = username
                return CandidateResult(
                    CandidateResultStatus.CANDIDATE_FOUND,
                    Candidate(
                        username=observation.username,
                        display_name=observation.display_name,
                        source="specific_users",
                        provider_type=CandidateProviderType.SPECIFIC_ACCOUNTS,
                    ),
                )
            position += 1
            self._save_progress(context, position, len(usernames))

        return CandidateResult(CandidateResultStatus.ALL_SOURCES_EXHAUSTED)

    def mark_processed(self, context: RuntimeContext) -> None:
        if self._current_username is None:
            return
        usernames = self._usernames()
        with RuntimeDatabase(self._account_directory) as database:
            progress = database.specific_progress.get("follow") or SpecificProgress(
                "follow"
            )
        self._current_username = None
        self._save_progress(context, progress.current_position + 1, len(usernames))

    def _save_progress(
        self, context: RuntimeContext, position: int, total: int
    ) -> None:
        completed = position >= total
        with RuntimeDatabase(self._account_directory) as database:
            database.specific_progress.save(
                SpecificProgress(
                    "follow",
                    current_position=position,
                    completed=completed,
                    repeat=False,
                )
            )
        context.logger.info(f"[Specific] Progress updated: {position}")
        if completed:
            context.logger.info("[Specific] List completed.")

    def _complete(self, context: RuntimeContext, total: int) -> None:
        with RuntimeDatabase(self._account_directory) as database:
            progress = database.specific_progress.get("follow")
            if progress is None or not progress.completed:
                database.specific_progress.save(
                    SpecificProgress(
                        "follow", current_position=total, completed=True, repeat=False
                    )
                )
        context.logger.info("[Specific] List completed.")

    def _usernames(self) -> tuple[str, ...]:
        path = self._account_directory / "Lists" / "followspecific.txt"
        if not path.is_file():
            return ()
        return tuple(
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
