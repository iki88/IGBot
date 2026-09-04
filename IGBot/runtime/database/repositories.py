"""Repositories for the frozen per-account Runtime Database schema.

All timestamps are persisted as UTC ISO-8601 text. All Runtime Database SQL is
contained here; runtime components consume repositories instead of connections.
"""

from __future__ import annotations

import sqlite3
from dataclasses import astuple

from IGBot.runtime.database.models import (
    CommentRecord,
    DMRecord,
    FollowRecord,
    LikeRecord,
    StoryRecord,
    UserRecord,
)


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
                first_seen TEXT NOT NULL CHECK (
                    first_seen GLOB '*Z' OR first_seen GLOB '*+00:00'
                ),
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
            (username, first_seen, first_discovered_by),
        )
        return UserRecord(
            id=cursor.lastrowid,
            username=username,
            first_seen=first_seen,
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


class FollowRepository:
    """Persist Follow-owned relationship state."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def initialize_schema(self) -> None:
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS follow (
                user_id INTEGER PRIMARY KEY,
                source TEXT,
                follow_date TEXT CHECK (
                    follow_date IS NULL OR follow_date GLOB '*Z'
                    OR follow_date GLOB '*+00:00'
                ),
                follow_back INTEGER NOT NULL DEFAULT 0
                    CHECK (follow_back IN (0, 1)),
                follow_back_date TEXT CHECK (
                    follow_back_date IS NULL OR follow_back_date GLOB '*Z'
                    OR follow_back_date GLOB '*+00:00'
                ),
                unfollowed INTEGER NOT NULL DEFAULT 0
                    CHECK (unfollowed IN (0, 1)),
                unfollow_date TEXT CHECK (
                    unfollow_date IS NULL OR unfollow_date GLOB '*Z'
                    OR unfollow_date GLOB '*+00:00'
                ),
                last_session_id TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """)

    def save(self, record: FollowRecord) -> None:
        self._connection.execute(
            """
            INSERT INTO follow (
                user_id, source, follow_date, follow_back, follow_back_date,
                unfollowed, unfollow_date, last_session_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                source = excluded.source,
                follow_date = excluded.follow_date,
                follow_back = excluded.follow_back,
                follow_back_date = excluded.follow_back_date,
                unfollowed = excluded.unfollowed,
                unfollow_date = excluded.unfollow_date,
                last_session_id = excluded.last_session_id
            """,
            astuple(record),
        )

    def get(self, user_id: int) -> FollowRecord | None:
        row = self._connection.execute(
            """
            SELECT user_id, source, follow_date, follow_back, follow_back_date,
                   unfollowed, unfollow_date, last_session_id
            FROM follow WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        return FollowRecord(
            user_id=row[0],
            source=row[1],
            follow_date=row[2],
            follow_back=bool(row[3]),
            follow_back_date=row[4],
            unfollowed=bool(row[5]),
            unfollow_date=row[6],
            last_session_id=row[7],
        )


class LikeRepository:
    """Persist Like-owned aggregate interaction state."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def initialize_schema(self) -> None:
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS "like" (
                user_id INTEGER PRIMARY KEY,
                source TEXT,
                likes_count INTEGER NOT NULL DEFAULT 0 CHECK (likes_count >= 0),
                last_like_date TEXT CHECK (
                    last_like_date IS NULL OR last_like_date GLOB '*Z'
                    OR last_like_date GLOB '*+00:00'
                ),
                follow_back INTEGER NOT NULL DEFAULT 0
                    CHECK (follow_back IN (0, 1)),
                follow_back_date TEXT CHECK (
                    follow_back_date IS NULL OR follow_back_date GLOB '*Z'
                    OR follow_back_date GLOB '*+00:00'
                ),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """)

    def save(self, record: LikeRecord) -> None:
        self._connection.execute(
            """
            INSERT INTO "like" (
                user_id, source, likes_count, last_like_date,
                follow_back, follow_back_date
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                source = excluded.source,
                likes_count = excluded.likes_count,
                last_like_date = excluded.last_like_date,
                follow_back = excluded.follow_back,
                follow_back_date = excluded.follow_back_date
            """,
            astuple(record),
        )

    def get(self, user_id: int) -> LikeRecord | None:
        row = self._connection.execute(
            """
            SELECT user_id, source, likes_count, last_like_date,
                   follow_back, follow_back_date
            FROM "like" WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        return LikeRecord(row[0], row[1], row[2], row[3], bool(row[4]), row[5])


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
                last_comment_date TEXT CHECK (
                    last_comment_date IS NULL OR last_comment_date GLOB '*Z'
                    OR last_comment_date GLOB '*+00:00'
                ),
                follow_back INTEGER NOT NULL DEFAULT 0
                    CHECK (follow_back IN (0, 1)),
                follow_back_date TEXT CHECK (
                    follow_back_date IS NULL OR follow_back_date GLOB '*Z'
                    OR follow_back_date GLOB '*+00:00'
                ),
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
            astuple(record),
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
                last_story_date TEXT CHECK (
                    last_story_date IS NULL OR last_story_date GLOB '*Z'
                    OR last_story_date GLOB '*+00:00'
                ),
                follow_back INTEGER NOT NULL DEFAULT 0
                    CHECK (follow_back IN (0, 1)),
                follow_back_date TEXT CHECK (
                    follow_back_date IS NULL OR follow_back_date GLOB '*Z'
                    OR follow_back_date GLOB '*+00:00'
                ),
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
            astuple(record),
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
                last_dm_date TEXT CHECK (
                    last_dm_date IS NULL OR last_dm_date GLOB '*Z'
                    OR last_dm_date GLOB '*+00:00'
                ),
                last_message TEXT,
                last_reply TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """)

    def save(self, record: DMRecord) -> None:
        self._connection.execute(
            """
            INSERT INTO dm (
                user_id, source, dm_count, last_dm_date, last_message, last_reply
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                source = excluded.source,
                dm_count = excluded.dm_count,
                last_dm_date = excluded.last_dm_date,
                last_message = excluded.last_message,
                last_reply = excluded.last_reply
            """,
            astuple(record),
        )

    def get(self, user_id: int) -> DMRecord | None:
        row = self._connection.execute(
            """
            SELECT user_id, source, dm_count, last_dm_date, last_message, last_reply
            FROM dm WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
        return DMRecord(*row) if row is not None else None
