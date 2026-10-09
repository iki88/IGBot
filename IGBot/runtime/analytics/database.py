"""Separate per-account Analytics Database."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import TracebackType
from typing import Self


@dataclass(frozen=True, slots=True)
class DailySummary:
    date: str
    username: str
    posts: int
    followers: int
    following: int
    followed: int
    unfollowed: int
    liked: int
    commented: int
    story: int
    dm: int
    posted: int


@dataclass(frozen=True, slots=True)
class DailySummaryDisplay:
    today: DailySummary | None
    previous: DailySummary | None

    @staticmethod
    def absolute_with_change(current: int, previous: int | None) -> str:
        if previous is None or current == previous:
            return str(current)
        difference = current - previous
        return f"{current} {'▲' if difference > 0 else '▼'}{abs(difference)}"


class AnalyticsDatabase:
    """Own ``analytics.db`` and one UTC-keyed daily summary table."""

    COUNTERS = frozenset(
        {"followed", "unfollowed", "liked", "commented", "story", "dm", "posted"}
    )

    def __init__(
        self,
        account_directory: str | Path,
        *,
        clock=lambda: datetime.now(timezone.utc),
    ) -> None:
        self.path = Path(account_directory) / "analytics.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock
        self._connection = sqlite3.connect(self.path)
        self._connection.row_factory = sqlite3.Row
        self._closed = False
        with self._connection:
            self._connection.execute("""
                CREATE TABLE IF NOT EXISTS daily_summary (
                    date TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    posts INTEGER NOT NULL DEFAULT 0,
                    followers INTEGER NOT NULL DEFAULT 0,
                    following INTEGER NOT NULL DEFAULT 0,
                    followed INTEGER NOT NULL DEFAULT 0,
                    unfollowed INTEGER NOT NULL DEFAULT 0,
                    liked INTEGER NOT NULL DEFAULT 0,
                    commented INTEGER NOT NULL DEFAULT 0,
                    story INTEGER NOT NULL DEFAULT 0,
                    dm INTEGER NOT NULL DEFAULT 0,
                    posted INTEGER NOT NULL DEFAULT 0
                )
                """)

    def update_snapshot(
        self,
        username: str,
        *,
        posts: int | None,
        followers: int | None,
        following: int | None,
    ) -> DailySummary:
        today = self._today()
        self._ensure_today(today, username)
        assignments = ["username = ?"]
        values: list[object] = [username]
        for column, value in (
            ("posts", posts),
            ("followers", followers),
            ("following", following),
        ):
            if value is not None:
                assignments.append(f"{column} = ?")
                values.append(max(0, int(value)))
        values.append(today)
        self._connection.execute(
            f"UPDATE daily_summary SET {', '.join(assignments)} WHERE date = ?",
            values,
        )
        summary = self.get(today)
        if summary is None:  # pragma: no cover - protected by _ensure_today
            raise RuntimeError("Today's analytics row was not created")
        return summary

    def increment(self, username: str, counter: str, amount: int = 1) -> DailySummary:
        if counter not in self.COUNTERS:
            raise ValueError(f"Unsupported analytics counter: {counter}")
        if amount <= 0:
            raise ValueError("Analytics increments must be positive")
        today = self._today()
        self._ensure_today(today, username)
        self._connection.execute(
            f"UPDATE daily_summary SET username = ?, {counter} = {counter} + ? "
            "WHERE date = ?",
            (username, amount, today),
        )
        summary = self.get(today)
        if summary is None:  # pragma: no cover - protected by _ensure_today
            raise RuntimeError("Today's analytics row was not created")
        return summary

    def get(self, summary_date: str | date) -> DailySummary | None:
        row = self._connection.execute(
            "SELECT * FROM daily_summary WHERE date = ?", (str(summary_date),)
        ).fetchone()
        return DailySummary(**dict(row)) if row is not None else None

    def history(self, days: int | None = 30) -> tuple[DailySummary, ...]:
        if days is not None and days <= 0:
            raise ValueError("Analytics window must be positive or All")
        parameters: tuple[object, ...] = ()
        where = ""
        if days is not None:
            first = self._current().date() - timedelta(days=days - 1)
            where = "WHERE date >= ?"
            parameters = (first.isoformat(),)
        rows = self._connection.execute(
            f"SELECT * FROM daily_summary {where} ORDER BY date DESC", parameters
        ).fetchall()
        return tuple(DailySummary(**dict(row)) for row in rows)

    def today_display(self) -> DailySummaryDisplay:
        today = self._today()
        current = self.get(today)
        previous_row = self._connection.execute(
            "SELECT * FROM daily_summary WHERE date < ? ORDER BY date DESC LIMIT 1",
            (today,),
        ).fetchone()
        previous = (
            DailySummary(**dict(previous_row)) if previous_row is not None else None
        )
        return DailySummaryDisplay(current, previous)

    def _ensure_today(self, today: str, username: str) -> None:
        self._connection.execute(
            "INSERT OR IGNORE INTO daily_summary (date, username) VALUES (?, ?)",
            (today, username),
        )

    def _today(self) -> str:
        return self._current().date().isoformat()

    def _current(self) -> datetime:
        current = self._clock()
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("Analytics timestamps must be timezone-aware")
        return current.astimezone(timezone.utc)

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        if not self._closed:
            self._connection.close()
            self._closed = True

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exception_type, exception, traceback: TracebackType | None) -> None:
        if exception_type is None:
            self.commit()
        else:
            self.rollback()
        self.close()
