"""Persistent account-local Follow daily-limit queries."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from pathlib import Path

from IGBot.runtime.database import DailyLimitResolver, ModuleUsageRepository


def successful_follows_today(
    account_directory: str | Path, now: datetime | None = None
) -> int:
    """Return successful discovery and Specific Follows for the current UTC day."""

    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    start = datetime.combine(current.date(), time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    return ModuleUsageRepository(account_directory).successful_between(
        "follow", start, end
    )


def remaining_daily_follows(
    account_directory: str | Path, configured_limit: object
) -> int:
    """Return persisted Follow capacity for the current UTC day."""

    return DailyLimitResolver(account_directory).capacity(
        "follow", configured_limit
    ).remaining
