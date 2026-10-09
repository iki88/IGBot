"""Repositories for the frozen per-account Runtime Database schema.

All timestamps are persisted as UTC ISO-8601 text. All Runtime Database SQL is
contained here; runtime components consume repositories instead of connections.
"""

from __future__ import annotations

import sqlite3
from dataclasses import astuple, replace

from IGBot.runtime.database.models import (
    CommentRecord,
    DMRecord,
    FollowRecord,
    LikeRecord,
    StoryRecord,
    UserRecord,
)
from IGBot.runtime.database.timestamps import optional_utc_timestamp, utc_timestamp


class UsersRepository:
    """Persist the minimal shared identity of a discovered user."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def initialize_schema(self) -> None:
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                first_seen TEXT NOT NULL,
                first_discovered_by TEXT
            )
            """)

    def create(
        self,
        username: str,
        first_seen: str,
        first_discovered_by: str | None = None,
    ) -> UserRecord:
        cursor = self._connection.execute(
            """
            INSERT INTO users (username, first_seen, first_discovered_by)
            VALUES (?, ?, ?)
            """,
            (username, utc_timestamp(first_seen), first_discovered_by),
        )
        return UserRecord(
            id=cursor.lastrowid,
            username=username,
            first_seen=utc_timestamp(first_seen),
            first_discovered_by=first_discovered_by,
        )

    def get_by_username(self, username: str) -> UserRecord | None:
        row = self._connection.execute(
            """
            SELECT id, username, first_seen, first_discovered_by
            FROM users
            WHERE username = ? COLLATE NOCASE
            """,
            (username,),
        ).fetchone()
        return UserRecord(*row) if row is not None else None

    def update_username(self, user_id: int, username: str) -> None:
        """Rename one identity; the Follow trigger synchronizes its copy."""

        self._connection.execute(
            "UPDATE users SET username = ? WHERE id = ?", (username, user_id)
        )


class FollowRepository:
    """Persist Follow-owned relationship state."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def initialize_schema(self) -> None:
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS follow (
                user_id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                source TEXT,
                follow_date TEXT,
                follow_back INTEGER NOT NULL DEFAULT 0
                    CHECK (follow_back IN (0, 1)),
                follow_back_date TEXT,
                unfollowed INTEGER NOT NULL DEFAULT 0
                    CHECK (unfollowed IN (0, 1)),
                unfollow_date TEXT,
                last_session_id TEXT,
                muted INTEGER NOT NULL DEFAULT 0 CHECK (muted IN (0, 1)),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """)
        self._connection.execute("""
            CREATE TRIGGER IF NOT EXISTS follow_username_sync
            AFTER UPDATE OF username ON users
            BEGIN
                UPDATE follow SET username = NEW.username WHERE user_id = NEW.id;
            END
            """)

    def save(self, record: FollowRecord) -> None:
        self._connection.execute(
            """
            INSERT INTO follow (
                user_id, username, source, follow_date, follow_back,
                follow_back_date, unfollowed, unfollow_date, last_session_id, muted
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                source = excluded.source,
                follow_date = excluded.follow_date,
                follow_back = excluded.follow_back,
                follow_back_date = excluded.follow_back_date,
                unfollowed = excluded.unfollowed,
                unfollow_date = excluded.unfollow_date,
                last_session_id = excluded.last_session_id,
                muted = excluded.muted
            """,
            astuple(
                replace(
                    record,
                    follow_date=optional_utc_timestamp(record.follow_date),
                    follow_back_date=optional_utc_timestamp(record.follow_back_date),
                    unfollow_date=optional_utc_timestamp(record.unfollow_date),
                )
            ),
        )

    def get(self, user_id: int) -> FollowRecord | None:
        row = self._connection.execute(
            """
            SELECT user_id, username, source, follow_date, follow_back,
                   follow_back_date, unfollowed, unfollow_date, last_session_id, muted
            FROM follow WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        return FollowRecord(
            user_id=row[0],
            username=row[1],
            source=row[2],
            follow_date=row[3],
            follow_back=bool(row[4]),
            follow_back_date=row[5],
            unfollowed=bool(row[6]),
            unfollow_date=row[7],
            last_session_id=row[8],
            muted=bool(row[9]),
        )

    def count_followed_between(self, start: str, end: str) -> int:
        """Count persisted Follow successes in the half-open UTC interval."""

        row = self._connection.execute(
            """
            SELECT COUNT(*)
            FROM follow
            WHERE follow_date >= ? AND follow_date < ?
            """,
            (utc_timestamp(start), utc_timestamp(end)),
        ).fetchone()
        return int(row[0])

    def eligible_for_unfollow(
        self,
        cutoff: str,
        *,
        limit: int = 1,
        require_no_follow_back: bool = False,
    ) -> tuple[FollowRecord, ...]:
        """Return IGBot-followed relationships old enough to unfollow."""

        statement = (
            """
                SELECT user_id, username, source, follow_date, follow_back,
                       follow_back_date, unfollowed, unfollow_date,
                       last_session_id, muted
                FROM follow
                WHERE unfollowed = 0
                  AND follow_date IS NOT NULL
                  AND follow_date <= ?
                  AND follow_back = 0
                ORDER BY follow_date, user_id
                LIMIT ?
            """
            if require_no_follow_back
            else """
                SELECT user_id, username, source, follow_date, follow_back,
                       follow_back_date, unfollowed, unfollow_date,
                       last_session_id, muted
                FROM follow
                WHERE unfollowed = 0
                  AND follow_date IS NOT NULL
                  AND follow_date <= ?
                ORDER BY follow_date, user_id
                LIMIT ?
            """
        )
        rows = self._connection.execute(
            statement, (utc_timestamp(cutoff), limit)
        ).fetchall()
        return tuple(
            FollowRecord(
                user_id=row[0],
                username=row[1],
                source=row[2],
                follow_date=row[3],
                follow_back=bool(row[4]),
                follow_back_date=row[5],
                unfollowed=bool(row[6]),
                unfollow_date=row[7],
                last_session_id=row[8],
                muted=bool(row[9]),
            )
            for row in rows
        )

    def count_unfollowed_between(self, start: str, end: str) -> int:
        row = self._connection.execute(
            "SELECT COUNT(*) FROM follow WHERE unfollowed = 1 AND unfollow_date >= ? AND unfollow_date < ?",
            (utc_timestamp(start), utc_timestamp(end)),
        ).fetchone()
        return int(row[0])


class LikeRepository:
    """Persist per-source Like candidate outcomes and aggregate success state."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def initialize_schema(self) -> None:
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS "like" (
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'UNKNOWN',
                likes_count INTEGER NOT NULL DEFAULT 0 CHECK (likes_count >= 0),
                last_like_date TEXT,
                processed_date TEXT,
                follow_back INTEGER NOT NULL DEFAULT 0
                    CHECK (follow_back IN (0, 1)),
                follow_back_date TEXT,
                last_session_id TEXT,
                PRIMARY KEY (user_id, source),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """)
        self._connection.execute("""
            CREATE TRIGGER IF NOT EXISTS like_username_sync
            AFTER UPDATE OF username ON users
            BEGIN
                UPDATE "like" SET username = NEW.username WHERE user_id = NEW.id;
            END
            """)

    def save(self, record: LikeRecord) -> None:
        self._connection.execute(
            """
            INSERT INTO "like" (
                user_id, username, source, status, likes_count, last_like_date,
                processed_date, follow_back, follow_back_date, last_session_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, source) DO UPDATE SET
                username = excluded.username,
                status = excluded.status,
                likes_count = excluded.likes_count,
                last_like_date = excluded.last_like_date,
                processed_date = excluded.processed_date,
                follow_back = excluded.follow_back,
                follow_back_date = excluded.follow_back_date,
                last_session_id = excluded.last_session_id
            """,
            astuple(
                replace(
                    record,
                    last_like_date=optional_utc_timestamp(record.last_like_date),
                    processed_date=optional_utc_timestamp(record.processed_date),
                    follow_back_date=optional_utc_timestamp(record.follow_back_date),
                )
            ),
        )

    def get(self, user_id: int, source: str | None = None) -> LikeRecord | None:
        where = "user_id = ? AND source = ?" if source is not None else "user_id = ?"
        parameters = (user_id, source) if source is not None else (user_id,)
        row = self._connection.execute(
            f"""
            SELECT user_id, username, source, status, likes_count, last_like_date,
                   processed_date, follow_back, follow_back_date, last_session_id
            FROM "like" WHERE {where}
            ORDER BY processed_date DESC
            LIMIT 1
            """,
            parameters,
        ).fetchone()
        if row is None:
            return None
        return LikeRecord(
            row[0],
            row[1],
            row[2],
            row[3],
            row[4],
            row[5],
            row[6],
            bool(row[7]),
            row[8],
            row[9],
        )

    def count_liked_between(self, start: str, end: str) -> int:
        """Count users with a verified Like in the half-open UTC interval."""

        row = self._connection.execute(
            'SELECT COALESCE(SUM(likes_count), 0) FROM "like" '
            "WHERE last_like_date >= ? AND last_like_date < ?",
            (utc_timestamp(start), utc_timestamp(end)),
        ).fetchone()
        return int(row[0])


class CommentRepository:
    """Persist Comment-owned aggregate interaction state."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def initialize_schema(self) -> None:
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS comment (
                user_id INTEGER PRIMARY KEY,
                source TEXT,
                comments_count INTEGER NOT NULL DEFAULT 0
                    CHECK (comments_count >= 0),
                last_comment_date TEXT,
                follow_back INTEGER NOT NULL DEFAULT 0
                    CHECK (follow_back IN (0, 1)),
                follow_back_date TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """)

    def save(self, record: CommentRecord) -> None:
        self._connection.execute(
            """
            INSERT INTO comment (
                user_id, source, comments_count, last_comment_date,
                follow_back, follow_back_date
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                source = excluded.source,
                comments_count = excluded.comments_count,
                last_comment_date = excluded.last_comment_date,
                follow_back = excluded.follow_back,
                follow_back_date = excluded.follow_back_date
            """,
            astuple(
                replace(
                    record,
                    last_comment_date=optional_utc_timestamp(record.last_comment_date),
                    follow_back_date=optional_utc_timestamp(record.follow_back_date),
                )
            ),
        )

    def get(self, user_id: int) -> CommentRecord | None:
        row = self._connection.execute(
            """
            SELECT user_id, source, comments_count, last_comment_date,
                   follow_back, follow_back_date
            FROM comment WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        return CommentRecord(row[0], row[1], row[2], row[3], bool(row[4]), row[5])


class StoryRepository:
    """Persist Story-owned aggregate interaction state."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def initialize_schema(self) -> None:
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS story (
                user_id INTEGER PRIMARY KEY,
                source TEXT,
                story_views_count INTEGER NOT NULL DEFAULT 0
                    CHECK (story_views_count >= 0),
                last_story_date TEXT,
                follow_back INTEGER NOT NULL DEFAULT 0
                    CHECK (follow_back IN (0, 1)),
                follow_back_date TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """)

    def save(self, record: StoryRecord) -> None:
        self._connection.execute(
            """
            INSERT INTO story (
                user_id, source, story_views_count, last_story_date,
                follow_back, follow_back_date
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                source = excluded.source,
                story_views_count = excluded.story_views_count,
                last_story_date = excluded.last_story_date,
                follow_back = excluded.follow_back,
                follow_back_date = excluded.follow_back_date
            """,
            astuple(
                replace(
                    record,
                    last_story_date=optional_utc_timestamp(record.last_story_date),
                    follow_back_date=optional_utc_timestamp(record.follow_back_date),
                )
            ),
        )

    def get(self, user_id: int) -> StoryRecord | None:
        row = self._connection.execute(
            """
            SELECT user_id, source, story_views_count, last_story_date,
                   follow_back, follow_back_date
            FROM story WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        return StoryRecord(row[0], row[1], row[2], row[3], bool(row[4]), row[5])


class DMRepository:
    """Persist the latest Direct Message exchange and aggregate count."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def initialize_schema(self) -> None:
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS dm (
                user_id INTEGER PRIMARY KEY,
                source TEXT,
                dm_count INTEGER NOT NULL DEFAULT 0 CHECK (dm_count >= 0),
                last_dm_date TEXT,
                last_message TEXT,
                last_reply TEXT,
                status TEXT NOT NULL DEFAULT 'UNKNOWN',
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """)
        columns = {
            row[1] for row in self._connection.execute('PRAGMA table_info("dm")')
        }
        if "status" not in columns:
            self._connection.execute(
                "ALTER TABLE dm ADD COLUMN status TEXT NOT NULL DEFAULT 'UNKNOWN'"
            )

    def save(self, record: DMRecord) -> None:
        self._connection.execute(
            """
            INSERT INTO dm (
                user_id, source, dm_count, last_dm_date, last_message, last_reply,
                status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                source = excluded.source,
                dm_count = excluded.dm_count,
                last_dm_date = excluded.last_dm_date,
                last_message = excluded.last_message,
                last_reply = excluded.last_reply,
                status = excluded.status
            """,
            astuple(
                replace(
                    record, last_dm_date=optional_utc_timestamp(record.last_dm_date)
                )
            ),
        )

    def get(self, user_id: int) -> DMRecord | None:
        row = self._connection.execute(
            """
            SELECT user_id, source, dm_count, last_dm_date, last_message, last_reply,
                   status
            FROM dm WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
        return DMRecord(*row) if row is not None else None

    def eligible_new_followers(self, *, limit: int = 100_000) -> tuple[tuple, ...]:
        """Return followed-back users without a successful Welcome DM."""

        rows = self._connection.execute(
            """
            SELECT u.id, u.username,
                   COALESCE(
                       f.source,
                       (SELECT l.source FROM "like" l
                        WHERE l.user_id = u.id AND l.follow_back = 1
                        ORDER BY l.follow_back_date, l.source LIMIT 1)
                   ) AS source
            FROM users u
            LEFT JOIN follow f ON f.user_id = u.id
            LEFT JOIN dm d ON d.user_id = u.id
            WHERE (
                f.follow_back = 1
                OR EXISTS (
                    SELECT 1 FROM "like" l
                    WHERE l.user_id = u.id AND l.follow_back = 1
                )
            )
              AND COALESCE(d.dm_count, 0) = 0
              AND COALESCE(d.status, 'UNKNOWN') != 'SUCCESS'
            ORDER BY COALESCE(f.follow_back_date, u.first_seen), u.id
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return tuple((int(row[0]), str(row[1]), row[2]) for row in rows)

    def count_sent_between(self, start: str, end: str) -> int:
        row = self._connection.execute(
            """
            SELECT COALESCE(SUM(dm_count), 0)
            FROM dm
            WHERE last_dm_date >= ? AND last_dm_date < ? AND status = 'SUCCESS'
            """,
            (utc_timestamp(start), utc_timestamp(end)),
        ).fetchone()
        return int(row[0])
