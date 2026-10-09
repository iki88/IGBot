"""Specific Users adapters for the native Like execution pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from IGBot.runtime.candidates import (
    Candidate,
    CandidateProviderType,
    CandidateResult,
    CandidateResultStatus,
)
from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.database import RuntimeDatabase
from IGBot.runtime.database.timestamps import utc_timestamp
from IGBot.runtime.follow import AndroidFollowProvider
from IGBot.runtime.follow.android_models import AndroidFollowResult, AndroidFollowStatus
from IGBot.runtime.ignore import IgnoreService


class SpecificLikeSynchronizer:
    """Synchronize likespecific.txt into account-local execution state."""

    def synchronize(
        self,
        account_directory: str | Path,
        ignore_service: IgnoreService | None = None,
    ) -> tuple[str, ...]:
        directory = Path(account_directory)
        path = directory / "Lists" / "likespecific.txt"
        usernames = (
            tuple(
                line.strip()
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            )
            if path.is_file()
            else ()
        )
        if ignore_service is not None:
            usernames = tuple(
                username
                for username in usernames
                if not ignore_service.is_ignored(username)
            )
        with RuntimeDatabase(directory) as database:
            database.specific_like.synchronize_like_usernames(usernames)
        return usernames


class SpecificLikeCandidates:
    """Supply pending usernames from specific_like in stable TXT order."""

    def __init__(self, account_directory: str | Path) -> None:
        self._account_directory = Path(account_directory)
        self._ignored_for_session: set[str] = set()

    def next_candidate(self, context: RuntimeContext) -> CandidateResult:
        with RuntimeDatabase(self._account_directory) as database:
            usernames = database.specific_like.pending_like_usernames()
        usernames = tuple(
            username
            for username in usernames
            if username.casefold() not in self._ignored_for_session
        )
        if not usernames:
            context.logger.info("[Specific Like] List completed.")
            return CandidateResult(CandidateResultStatus.ALL_SOURCES_EXHAUSTED)
        username = usernames[0]
        context.logger.info("[Specific Like] Username selected.", username=username)
        return CandidateResult(
            CandidateResultStatus.CANDIDATE_FOUND,
            Candidate(
                username=username,
                source="specific_users",
                provider_type=CandidateProviderType.SPECIFIC_ACCOUNTS,
            ),
        )

    def mark_ignored(self, candidate: Candidate) -> None:
        self._ignored_for_session.add(candidate.username.casefold())


class SpecificLikeNavigation:
    """Adapt Instagram Search to AndroidLikeProvider's navigation contract."""

    def __init__(self, profiles: AndroidFollowProvider) -> None:
        self._profiles = profiles

    def open_candidate_profile(
        self, context: RuntimeContext, candidate: Candidate
    ) -> AndroidFollowResult:
        context.logger.info(
            "[Specific Like] Searching username...", username=candidate.username
        )
        located = self._profiles.locate_source(
            context, candidate.username, bounded_accounts_scroll=True
        )
        if located.status is not AndroidFollowStatus.SUCCESS:
            if (
                located.status is AndroidFollowStatus.FOLLOW_FAILED
                and not located.navigation_failed
            ):
                restored = self._profiles.return_to_search(context)
                if not restored.succeeded:
                    return AndroidFollowResult(
                        AndroidFollowStatus.FOLLOW_FAILED,
                        restored.detail or located.detail,
                        navigation_failed=True,
                    )
            return located
        opened = self._profiles.open_candidate_profile(context, candidate)
        if opened.status is not AndroidFollowStatus.SUCCESS:
            context.logger.warning(
                "[Specific Like] Requested profile unavailable.",
                username=candidate.username,
                reason=opened.detail,
            )
            restored = self._profiles.return_to_search(context)
            if not restored.succeeded:
                return AndroidFollowResult(
                    AndroidFollowStatus.FOLLOW_FAILED,
                    restored.detail or opened.detail,
                    navigation_failed=True,
                )
        return opened

    def return_to_followers(self, context: RuntimeContext) -> AndroidFollowResult:
        """Map the shared Like return hook to Search for Specific Users."""

        return self._profiles.return_to_search(context)


class SpecificLikePersistence:
    """Persist outcomes without touching discovery Like history."""

    @staticmethod
    def already_processed(context: RuntimeContext, candidate: Candidate) -> bool:
        with RuntimeDatabase(context.session.account_directory) as database:
            pending = database.specific_like.pending_like_usernames()
        return not any(
            username.casefold() == candidate.username.casefold() for username in pending
        )

    @staticmethod
    def persist(
        context: RuntimeContext,
        candidate: Candidate,
        status: str,
        likes_completed: int,
    ) -> None:
        processed_at = utc_timestamp(datetime.now(timezone.utc))
        with RuntimeDatabase(context.session.account_directory) as database:
            database.specific_like.mark_specific_like_result(
                candidate.username,
                status=status,
                likes_count=likes_completed,
                processed_at=processed_at,
                last_session_id=str(context.session.session_id),
            )
        context.logger.info(
            "Specific Like runtime updated.",
            username=candidate.username,
            status=status,
        )
