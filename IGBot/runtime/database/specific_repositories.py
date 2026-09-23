"""Repositories for account-local Specific Users workflow state."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass

from IGBot.runtime.database.timestamps import utc_timestamp


class SpecificInteractionRepository:
    def __init__(
        self, connection: sqlite3.Connection, table: str, columns: str
    ) -> None:
        self._connection = connection
        self._table = table
        self._columns = columns

    def initialize_schema(self) -> None:
        self._connection.execute(
            f'CREATE TABLE IF NOT EXISTS "{self._table}" ({self._columns})'
        )
        if self._table == "specific_unfollow":
            columns = {
                row[1]
                for row in self._connection.execute(
                    'PRAGMA table_info("specific_unfollow")'
                )
            }
            if "unfollowed" not in columns:
                self._connection.execute(
                    "ALTER TABLE specific_unfollow ADD COLUMN unfollowed "
                    "INTEGER NOT NULL DEFAULT 0 CHECK (unfollowed IN (0, 1))"
                )
            if "last_session_id" not in columns:
                self._connection.execute(
                    "ALTER TABLE specific_unfollow ADD COLUMN last_session_id TEXT"
                )

    def upsert_username(self, username: str, values: Mapping[str, object]) -> int:
        """Insert or update one module-local username without discovery-table joins."""

        columns = {
            row[1]
            for row in self._connection.execute(f'PRAGMA table_info("{self._table}")')
        }
        invalid = set(values) - columns
        if invalid or {"user_id", "username"} & set(values):
            raise ValueError("Specific interaction values contain unsupported columns")
        row = self._connection.execute(
            f'SELECT user_id FROM "{self._table}" WHERE username = ? COLLATE NOCASE',
            (username,),
        ).fetchone()
        if row is None:
            user_id = int(
                self._connection.execute(
                    f'SELECT COALESCE(MAX(user_id), 0) + 1 FROM "{self._table}"'
                ).fetchone()[0]
            )
            names = ("user_id", "username", *values)
            placeholders = ", ".join("?" for _ in names)
            self._connection.execute(
                f'INSERT INTO "{self._table}" '
                f'({", ".join(names)}) VALUES ({placeholders})',
                (user_id, username, *values.values()),
            )
            return user_id
        user_id = int(row[0])
        assignments = ", ".join(f'"{name}" = ?' for name in values)
        if assignments:
            self._connection.execute(
                f'UPDATE "{self._table}" SET username = ?, {assignments} '
                "WHERE user_id = ?",
                (username, *values.values(), user_id),
            )
        else:
            self._connection.execute(
                f'UPDATE "{self._table}" SET username = ? WHERE user_id = ?',
                (username, user_id),
            )
        return user_id

    def count_successful_follows_between(self, start: str, end: str) -> int:
        """Count successful Specific Follow outcomes in a UTC interval."""

        if self._table != "specific_follow":
            raise ValueError("Follow counts are available only for specific_follow")
        row = self._connection.execute(
            """
            SELECT COUNT(*)
            FROM specific_follow
            WHERE follow_date >= ? AND follow_date < ?
              AND status IN ('SUCCESS', 'REQUESTED')
            """,
            (utc_timestamp(start), utc_timestamp(end)),
        ).fetchone()
        return int(row[0])

    def synchronize_unfollow_usernames(self, usernames: tuple[str, ...]) -> None:
        """Mirror the Unfollow TXT source while retaining matching row state."""

        if self._table != "specific_unfollow":
            raise ValueError("Unfollow synchronization requires specific_unfollow")
        normalized: dict[str, str] = {}
        for username in usernames:
            cleaned = username.strip()
            if cleaned:
                normalized.setdefault(cleaned.casefold(), cleaned)
        existing = self._connection.execute(
            "SELECT user_id, username FROM specific_unfollow"
        ).fetchall()
        existing_by_name = {
            str(row[1]).casefold(): (int(row[0]), row[1]) for row in existing
        }
        for key, username in normalized.items():
            current = existing_by_name.get(key)
            if current is None:
                self.upsert_username(
                    username,
                    {
                        "unfollowed": 0,
                        "unfollow_date": None,
                        "last_session_id": None,
                        "status": None,
                    },
                )
            elif current[1] != username:
                self.upsert_username(username, {})
        removed_ids = [
            user_id
            for key, (user_id, _username) in existing_by_name.items()
            if key not in normalized
        ]
        if removed_ids:
            placeholders = ", ".join("?" for _ in removed_ids)
            self._connection.execute(
                f"DELETE FROM specific_unfollow WHERE user_id IN ({placeholders})",
                removed_ids,
            )

    def pending_unfollow_usernames(self) -> tuple[str, ...]:
        if self._table != "specific_unfollow":
            raise ValueError("Pending Unfollow users require specific_unfollow")
        rows = self._connection.execute(
            "SELECT username FROM specific_unfollow WHERE unfollowed = 0 "
            "ORDER BY user_id"
        ).fetchall()
        return tuple(str(row[0]) for row in rows)

    def mark_specific_unfollowed(
        self, username: str, unfollow_date: str, last_session_id: str
    ) -> None:
        if self._table != "specific_unfollow":
            raise ValueError("Unfollow updates require specific_unfollow")
        self._connection.execute(
            "UPDATE specific_unfollow SET unfollowed = 1, unfollow_date = ?, "
            "last_session_id = ?, status = 'SUCCESS' "
            "WHERE username = ? COLLATE NOCASE",
            (utc_timestamp(unfollow_date), last_session_id, username),
        )

    def count_successful_unfollows_between(self, start: str, end: str) -> int:
        if self._table != "specific_unfollow":
            raise ValueError("Unfollow counts require specific_unfollow")
        row = self._connection.execute(
            "SELECT COUNT(*) FROM specific_unfollow "
            "WHERE unfollowed = 1 AND unfollow_date >= ? AND unfollow_date < ?",
            (utc_timestamp(start), utc_timestamp(end)),
        ).fetchone()
        return int(row[0])


@dataclass(frozen=True, slots=True)
class SpecificProgress:
    module: str
    current_position: int = 0
    completed: bool = False
    repeat: bool = False


class SpecificProgressRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def initialize_schema(self) -> None:
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS specific_progress (
                module TEXT PRIMARY KEY,
                current_position INTEGER NOT NULL DEFAULT 0 CHECK (current_position >= 0),
                completed INTEGER NOT NULL DEFAULT 0 CHECK (completed IN (0, 1)),
                repeat INTEGER NOT NULL DEFAULT 0 CHECK (repeat IN (0, 1))
            )""")

    def save(self, progress: SpecificProgress) -> None:
        self._connection.execute(
            """
            INSERT INTO specific_progress (module, current_position, completed, repeat)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(module) DO UPDATE SET
                current_position=excluded.current_position,
                completed=excluded.completed,
                repeat=excluded.repeat""",
            (
                progress.module,
                progress.current_position,
                progress.completed,
                progress.repeat,
            ),
        )

    def get(self, module: str) -> SpecificProgress | None:
        row = self._connection.execute(
            "SELECT module, current_position, completed, repeat FROM specific_progress WHERE module = ?",
            (module,),
        ).fetchone()
        return (
            SpecificProgress(row[0], row[1], bool(row[2]), bool(row[3]))
            if row
            else None
        )


def specific_repositories(
    connection: sqlite3.Connection,
) -> dict[str, SpecificInteractionRepository]:
    common = "user_id INTEGER PRIMARY KEY, username TEXT NOT NULL"
    return {
        "specific_follow": SpecificInteractionRepository(
            connection,
            "specific_follow",
            common + ", follow_date TEXT, unfollow_date TEXT, contact TEXT, "
            "contact_scraped INTEGER NOT NULL DEFAULT 0 "
            "CHECK (contact_scraped IN (0, 1)), muted INTEGER NOT NULL DEFAULT 0 "
            "CHECK (muted IN (0, 1)), status TEXT",
        ),
        "specific_unfollow": SpecificInteractionRepository(
            connection,
            "specific_unfollow",
            common + ", unfollow_date TEXT, status TEXT, "
            "unfollowed INTEGER NOT NULL DEFAULT 0 "
            "CHECK (unfollowed IN (0, 1)), last_session_id TEXT",
        ),
        "specific_like": SpecificInteractionRepository(
            connection,
            "specific_like",
            common
            + ", likes_count INTEGER NOT NULL DEFAULT 0 CHECK (likes_count >= 0), "
            "last_like_date TEXT, status TEXT",
        ),
        "specific_dm": SpecificInteractionRepository(
            connection,
            "specific_dm",
            common + ", dm_count INTEGER NOT NULL DEFAULT 0 CHECK (dm_count >= 0), "
            "last_dm_date TEXT, status TEXT",
        ),
        "specific_comment": SpecificInteractionRepository(
            connection,
            "specific_comment",
            common + ", comments_count INTEGER NOT NULL DEFAULT 0 "
            "CHECK (comments_count >= 0), last_comment_date TEXT, status TEXT",
        ),
    }
