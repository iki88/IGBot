"""Persistent native-module daily targets and aggregated usage."""

from __future__ import annotations

import random
import sqlite3
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

from IGBot.runtime.database.timestamps import utc_timestamp


@dataclass(frozen=True, slots=True)
class DailyLimitRecord:
    module: str
    limit_date: str
    configured_spec: str
    resolved_target: int
    created_at: str
    updated_at: str


class DailyLimitsRepository:
    """Store one immutable ranged target per module and UTC calendar day."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def initialize_schema(self) -> None:
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS daily_limits (
                module TEXT NOT NULL,
                limit_date TEXT NOT NULL,
                configured_spec TEXT NOT NULL,
                resolved_target INTEGER NOT NULL CHECK (resolved_target >= 0),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (module, limit_date)
            )
            """)

    def get(self, module: str, limit_date: str) -> DailyLimitRecord | None:
        row = self._connection.execute(
            "SELECT * FROM daily_limits WHERE module = ? AND limit_date = ?",
            (module, limit_date),
        ).fetchone()
        return DailyLimitRecord(**dict(row)) if row is not None else None

    def create_if_absent(
        self, module: str, limit_date: str, configured_spec: str,
        resolved_target: int, timestamp: str,
    ) -> None:
        self._connection.execute(
            """
            INSERT OR IGNORE INTO daily_limits (
                module, limit_date, configured_spec, resolved_target,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (module, limit_date, configured_spec, resolved_target, timestamp, timestamp),
        )

    def update_fixed_target(
        self, module: str, limit_date: str, configured_spec: str,
        resolved_target: int, timestamp: str,
    ) -> None:
        self._connection.execute(
            """
            UPDATE daily_limits
            SET configured_spec = ?, resolved_target = ?, updated_at = ?
            WHERE module = ? AND limit_date = ?
            """,
            (configured_spec, resolved_target, timestamp, module, limit_date),
        )


@dataclass(frozen=True, slots=True)
class DailyLimitCapacity:
    module: str
    limit_date: str
    configured_spec: str
    resolved_target: int
    successful_interactions: int

    @property
    def remaining(self) -> int:
        return max(0, self.resolved_target - self.successful_interactions)


class ModuleUsageRepository:
    """Aggregate successful interactions across every provider of a module."""

    def __init__(self, account_directory: str | Path) -> None:
        self._account_directory = Path(account_directory)

    def successful_between(self, module: str, start: datetime, end: datetime) -> int:
        from IGBot.runtime.database.database import RuntimeDatabase

        start_text = utc_timestamp(start)
        end_text = utc_timestamp(end)
        with RuntimeDatabase(self._account_directory) as database:
            if module == "follow":
                return database.follow.count_followed_between(
                    start_text, end_text
                ) + database.specific_follow.count_successful_follows_between(
                    start_text, end_text
                )
            if module == "like":
                return database.like.count_liked_between(
                    start_text, end_text
                ) + database.specific_like.count_successful_likes_between(
                    start_text, end_text
                )
            if module == "dm":
                return database.dm.count_sent_between(
                    start_text, end_text
                ) + database.specific_dm.count_successful_dms_between(
                    start_text, end_text
                )
            if module == "unfollow":
                runtime_count = database.follow.count_unfollowed_between(
                    start_text, end_text
                ) + database.specific_unfollow.count_successful_unfollows_between(
                    start_text, end_text
                )
            else:
                raise ValueError(f"Unsupported daily-limit module: {module}")

        from IGBot.runtime.unfollow.following_list_database import FollowingListDatabase

        with FollowingListDatabase(self._account_directory) as database:
            return runtime_count + database.count_unfollowed_between(
                start_text, end_text
            )


class DailyLimitResolver:
    """Resolve and persist one account/module target per UTC calendar day."""

    def __init__(
        self,
        account_directory: str | Path,
        *,
        randint=None,
        usage: ModuleUsageRepository | None = None,
    ) -> None:
        self._account_directory = Path(account_directory)
        self._randint = randint or random.randint
        self._usage = usage or ModuleUsageRepository(self._account_directory)

    @staticmethod
    def parse(specification: object, *, default: int = 100_000) -> tuple[int, int, str]:
        text = "" if specification is None else str(specification).strip()
        if not text:
            text = str(default)
        try:
            if "-" in text:
                first, second = (int(part.strip()) for part in text.split("-", 1))
                lower, upper = sorted((first, second))
            else:
                lower = upper = int(text)
        except (TypeError, ValueError):
            lower = upper = default
            text = str(default)
        lower = max(lower, 0)
        upper = max(upper, 0)
        normalized = str(lower) if lower == upper else f"{lower}-{upper}"
        return lower, upper, normalized

    def capacity(
        self, module: str, configured_spec: object, *, now: datetime | None = None
    ) -> DailyLimitCapacity:
        from IGBot.runtime.database.database import RuntimeDatabase

        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        start = datetime.combine(current.date(), time.min, tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        successful = self._usage.successful_between(module, start, end)
        lower, upper, normalized = self.parse(configured_spec)
        timestamp = utc_timestamp(current)
        limit_date = current.date().isoformat()

        with RuntimeDatabase(self._account_directory) as database:
            record = database.daily_limits.get(module, limit_date)
            if record is None:
                target = lower if lower == upper else self._randint(lower, upper)
                database.daily_limits.create_if_absent(
                    module, limit_date, normalized, target, timestamp
                )
                record = database.daily_limits.get(module, limit_date)
                assert record is not None
            elif lower == upper and normalized != record.configured_spec:
                new_target = lower
                if new_target > record.resolved_target or successful < new_target:
                    database.daily_limits.update_fixed_target(
                        module, limit_date, normalized, new_target, timestamp
                    )
                    record = database.daily_limits.get(module, limit_date)
                    assert record is not None

        return DailyLimitCapacity(
            module=module,
            limit_date=limit_date,
            configured_spec=record.configured_spec,
            resolved_target=record.resolved_target,
            successful_interactions=successful,
        )
