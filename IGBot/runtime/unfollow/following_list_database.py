"""Dedicated persistence for Unfollow All Followings history."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Self


@dataclass(frozen=True, slots=True)
class FollowingListRecord:
    username: str
    unfollowed: bool
    unfollow_date: str | None
    last_session_id: str | None


class FollowingListDatabase:
    """Own ``following_list.db`` independently from account ``runtime.db``."""

    def __init__(self, account_directory: str | Path) -> None:
        self.path = Path(account_directory) / "following_list.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS following_list (
                username TEXT PRIMARY KEY COLLATE NOCASE,
                unfollowed INTEGER NOT NULL DEFAULT 0,
                unfollow_date TEXT,
                last_session_id TEXT
            )
            """)
        self._connection.commit()

    def processed_usernames(self) -> frozenset[str]:
        rows = self._connection.execute(
            "SELECT username FROM following_list WHERE unfollowed = 1"
        ).fetchall()
        return frozenset(str(row["username"]).casefold() for row in rows)

    def mark_unfollowed(
        self, username: str, unfollow_date: str, last_session_id: str
    ) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO following_list (
                    username, unfollowed, unfollow_date, last_session_id
                ) VALUES (?, 1, ?, ?)
                ON CONFLICT(username) DO UPDATE SET
                    unfollowed = 1,
                    unfollow_date = excluded.unfollow_date,
                    last_session_id = excluded.last_session_id
                """,
                (username, unfollow_date, last_session_id),
            )

    def count_unfollowed_between(self, start: str, end: str) -> int:
        row = self._connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM following_list
            WHERE unfollowed = 1
              AND unfollow_date >= ?
              AND unfollow_date < ?
            """,
            (start, end),
        ).fetchone()
        return int(row["count"] if row is not None else 0)

    def get(self, username: str) -> FollowingListRecord | None:
        row = self._connection.execute(
            "SELECT * FROM following_list WHERE username = ? COLLATE NOCASE",
            (username,),
        ).fetchone()
        if row is None:
            return None
        return FollowingListRecord(
            username=str(row["username"]),
            unfollowed=bool(row["unfollowed"]),
            unfollow_date=row["unfollow_date"],
            last_session_id=row["last_session_id"],
        )

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
