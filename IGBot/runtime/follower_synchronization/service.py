"""Executable Follower Synchronization startup stage."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.database import RuntimeDatabase
from IGBot.runtime.follower_synchronization.contracts import (
    FollowerComparer,
    FollowerReader,
    FollowerWriter,
)
from IGBot.runtime.follower_synchronization.models import (
    FollowerSynchronizationResult,
)
from IGBot.runtime.startup.models import (
    StartupStageName,
    StartupStageResult,
    StartupStageStatus,
)


class FollowerSynchronization:
    """Coordinate one bounded follower scan and atomic Runtime Database update."""

    LIMIT_SETTING = "follower_synchronization_limit"

    def __init__(
        self,
        reader: FollowerReader,
        comparer: FollowerComparer,
        writer: FollowerWriter,
        *,
        database_factory: Callable[[Path], RuntimeDatabase] = RuntimeDatabase,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._reader = reader
        self._comparer = comparer
        self._writer = writer
        self._database_factory = database_factory
        self._clock = clock

    def execute(self, context: RuntimeContext) -> StartupStageResult:
        """Execute the session's sole follower synchronization pass."""

        try:
            limit = self._limit(context)
        except ValueError as error:
            return self._failed(context, str(error))

        context.logger.info("Follower Synchronization started", limit=limit)
        try:
            read_result = self._reader.read(context, limit)
        except Exception as error:  # noqa: BLE001 - provider isolation boundary
            return self._failed(context, f"Follower list inspection failed: {error}")
        if not read_result.completed:
            return self._failed(
                context,
                read_result.detail
                or "Follower Synchronization could not read followers.",
            )

        observed_at = self._clock()
        try:
            with self._database_factory(context.session.account_directory) as database:
                comparison = self._comparer.compare(
                    read_result.usernames,
                    database.users,
                    database.follow,
                    observed_at,
                )
                self._writer.write(
                    comparison,
                    database.users,
                    database.follow,
                    observed_at,
                )
        except Exception as error:  # noqa: BLE001 - transactional stage boundary
            return self._failed(context, f"Follower Synchronization failed: {error}")

        result = FollowerSynchronizationResult(
            synchronization_completed=True,
            scanned_count=len(read_result.usernames),
            follow_back_updates=len(comparison.follow_back_updates),
            newly_discovered_organic_followers=comparison.organic_usernames,
            limit_reached=read_result.limit_reached,
        )
        context.logger.info(
            "Follower Synchronization completed",
            scanned=result.scanned_count,
            follow_back_updates=result.follow_back_updates,
            organic_followers=len(result.newly_discovered_organic_followers),
            limit_reached=result.limit_reached,
        )
        return StartupStageResult(
            StartupStageName.FOLLOWER_SYNCHRONIZATION,
            StartupStageStatus.SUCCESS,
            new_followers_found=len(result.newly_discovered_organic_followers),
            follower_synchronization=result,
        )

    @classmethod
    def _limit(cls, context: RuntimeContext) -> int:
        value = context.runtime_settings.get(cls.LIMIT_SETTING)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(
                f"{cls.LIMIT_SETTING} must be configured as a positive integer"
            )
        return value

    @staticmethod
    def _failed(context: RuntimeContext, detail: str) -> StartupStageResult:
        context.logger.error(detail)
        return StartupStageResult(
            StartupStageName.FOLLOWER_SYNCHRONIZATION,
            StartupStageStatus.FAILED,
            detail=detail,
            follower_synchronization=FollowerSynchronizationResult(
                synchronization_completed=False,
                scanned_count=0,
                follow_back_updates=0,
                newly_discovered_organic_followers=(),
            ),
        )
