"""Single asynchronous writer for the shared Global Profile Database."""

from __future__ import annotations

import queue
import sqlite3
import threading
from pathlib import Path

from IGBot.runtime.database.timestamps import utc_timestamp
from IGBot.runtime.profile_database.models import ProfileUpdate


class GlobalDatabaseWriter:
    """Persist shared profile facts without blocking Android automation."""

    _STOP = object()

    def __init__(self, workspace: Path) -> None:
        self.path = Path(workspace) / "global_profiles.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._queue: queue.Queue[ProfileUpdate | object] = queue.Queue()
        self._error: Exception | None = None
        self._thread = threading.Thread(
            target=self._run, name="global-profile-writer", daemon=True
        )
        self._thread.start()

    def submit(self, update: ProfileUpdate) -> None:
        """Queue one immutable update and return immediately."""
        if self._error is not None:
            raise RuntimeError("Global profile writer failed") from self._error
        self._queue.put_nowait(update)

    def flush(self) -> None:
        self._queue.join()
        if self._error is not None:
            raise RuntimeError("Global profile writer failed") from self._error

    def close(self) -> None:
        self.flush()
        self._queue.put(self._STOP)
        self._thread.join(timeout=5)
        if self._thread.is_alive():
            raise RuntimeError("Global profile writer did not stop")

    def _run(self) -> None:
        try:
            with sqlite3.connect(self.path) as connection:
                self._initialize(connection)
                while True:
                    item = self._queue.get()
                    try:
                        if item is self._STOP:
                            return
                        assert isinstance(item, ProfileUpdate)
                        self._save(connection, item)
                        connection.commit()
                    finally:
                        self._queue.task_done()
        except Exception as error:  # noqa: BLE001
            self._error = error
            while True:
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    break
                else:
                    self._queue.task_done()

    @staticmethod
    def _initialize(connection: sqlite3.Connection) -> None:
        existing_columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(profiles)").fetchall()
        }
        if (
            "category" in existing_columns
            and "business_category" not in existing_columns
        ):
            connection.execute(
                "ALTER TABLE profiles RENAME COLUMN category TO business_category"
            )
        connection.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                username TEXT PRIMARY KEY COLLATE NOCASE,
                full_name TEXT NOT NULL DEFAULT '',
                biography TEXT NOT NULL DEFAULT '',
                business_category TEXT NOT NULL DEFAULT '',
                website TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '',
                email TEXT NOT NULL DEFAULT '',
                address TEXT NOT NULL DEFAULT '',
                followers INTEGER,
                following INTEGER,
                posts INTEGER,
                private INTEGER NOT NULL CHECK (private IN (0, 1)),
                business INTEGER NOT NULL CHECK (business IN (0, 1)),
                verified INTEGER NOT NULL CHECK (verified IN (0, 1)),
                follow_status TEXT NOT NULL DEFAULT '',
                source_account TEXT NOT NULL DEFAULT '',
                discovered_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        connection.execute("""
            UPDATE profiles
            SET discovered_at = strftime('%Y-%m-%d %H:%M:%S', discovered_at),
                updated_at = strftime('%Y-%m-%d %H:%M:%S', updated_at)
            WHERE discovered_at LIKE '%T%' OR updated_at LIKE '%T%'
            """)

    @staticmethod
    def _save(connection: sqlite3.Connection, update: ProfileUpdate) -> None:
        connection.execute(
            """
            INSERT INTO profiles (
                username, full_name, biography, business_category, website, phone, email,
                address, followers, following, posts, private, business, verified,
                follow_status, source_account, discovered_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                full_name=CASE WHEN excluded.full_name != '' THEN excluded.full_name ELSE profiles.full_name END,
                biography=CASE WHEN excluded.biography != '' THEN excluded.biography ELSE profiles.biography END,
                business_category=CASE WHEN excluded.business_category != '' THEN excluded.business_category ELSE profiles.business_category END,
                website=CASE WHEN excluded.website != '' THEN excluded.website ELSE profiles.website END,
                phone=CASE WHEN excluded.phone != '' THEN excluded.phone ELSE profiles.phone END,
                email=CASE WHEN excluded.email != '' THEN excluded.email ELSE profiles.email END,
                address=CASE WHEN excluded.address != '' THEN excluded.address ELSE profiles.address END,
                followers=COALESCE(excluded.followers, profiles.followers),
                following=COALESCE(excluded.following, profiles.following),
                posts=COALESCE(excluded.posts, profiles.posts), private=excluded.private,
                business=excluded.business, verified=excluded.verified,
                follow_status=excluded.follow_status,
                source_account=excluded.source_account,
                updated_at=excluded.updated_at
            """,
            (
                update.username,
                update.full_name,
                update.biography,
                update.category,
                update.website,
                update.phone,
                update.email,
                update.address,
                update.followers,
                update.following,
                update.posts,
                int(update.is_private),
                int(update.is_business),
                int(update.is_verified),
                update.follow_status,
                update.source_account,
                utc_timestamp(update.discovered_at),
                utc_timestamp(update.discovered_at),
            ),
        )
