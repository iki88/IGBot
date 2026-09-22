"""Persistent account-local Follow daily-limit queries."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from pathlib import Path

from IGBot.runtime.database import RuntimeDatabase


def successful_follows_today(
    account_directory: str | Path, now: datetime | None = None
) -> int:
    """Return successful discovery and Specific Follows for the current UTC day."""

    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    start = datetime.combine(current.date(), time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    with RuntimeDatabase(account_directory) as database:
        return database.follow.count_followed_between(
            start.isoformat(), end.isoformat()
        ) + database.specific_follow.count_successful_follows_between(
            start.isoformat(), end.isoformat()
        )


def remaining_daily_follows(
    account_directory: str | Path, configured_limit: object
) -> int:
    """Return persisted Follow capacity for the current UTC day."""

    try:
        limit = max(0, int(str(configured_limit).split("-", 1)[-1]))
    except (TypeError, ValueError):
        limit = 100_000
    return max(0, limit - successful_follows_today(account_directory))
