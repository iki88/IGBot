"""UTC timestamps displayed as ``YYYY-MM-DD HH:MM:SS`` in SQLite.

The offset-free database representation is always UTC, not local time.
"""

from __future__ import annotations

from datetime import datetime, timezone


def utc_timestamp(value: str | datetime) -> str:
    """Normalize a UTC instant without changing its time-zone semantics."""

    if isinstance(value, str):
        if "T" not in value:
            return (
                datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
                .replace(tzinfo=timezone.utc)
                .strftime("%Y-%m-%d %H:%M:%S")
            )
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Runtime database timestamps must be UTC-aware")
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def optional_utc_timestamp(value: str | None) -> str | None:
    return utc_timestamp(value) if value is not None else None
