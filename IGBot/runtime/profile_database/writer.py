"""Single asynchronous writer for the shared Global Profile Database."""

from __future__ import annotations

import queue
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from IGBot.runtime.database.timestamps import utc_timestamp
from IGBot.runtime.profile_database.models import ProfileUpdate


class _DiagnosticLogger(Protocol):
    def error(self, message: str, **fields: object) -> None: ...


@dataclass(frozen=True, slots=True)
class _WriteRequest:
    update: ProfileUpdate
    account: str
    operation: str


class GlobalProfileWriterError(RuntimeError):
    """A diagnostic failure for one asynchronous global-profile operation."""

    def __init__(
        self,
        *,
        database: Path,
        account: str,
        operation: str,
        profile: str,
        cause: BaseException,
    ) -> None:
        self.database = Path(database)
        self.account = account
        self.operation = operation
        self.profile = profile
        self.cause = cause
        self.reported = False
        super().__init__(
            "Global profile writer failed: "
            f"account={account or '<unknown>'}; operation={operation}; "
            f"profile={profile or '<none>'}; database={self.database}; "
            f"exception={type(cause).__name__}: {cause}"
        )


class GlobalDatabaseWriter:
    """Persist shared profile facts without blocking Android automation."""

    _STOP = object()

    def __init__(
        self,
        workspace: Path,
        *,
        account: str = "",
        diagnostic_logger: _DiagnosticLogger | None = None,
    ) -> None:
        self.path = Path(workspace) / "global_profiles.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._account = account
        self._logger = diagnostic_logger
        self._queue: queue.Queue[_WriteRequest | object] = queue.Queue()
        self._error: GlobalProfileWriterError | None = None
        self._active_request: _WriteRequest | None = None
        self._thread = threading.Thread(
            target=self._run, name="global-profile-writer", daemon=True
        )
        self._thread.start()

    def submit(
        self,
        update: ProfileUpdate,
        *,
        operation: str = "Update profile observation",
        account: str | None = None,
    ) -> None:
        """Queue one immutable update and return immediately."""
        self._raise_if_failed()
        self._queue.put_nowait(
            _WriteRequest(update, account if account is not None else self._account, operation)
        )

    def flush(self) -> None:
        self._queue.join()
        self._raise_if_failed()

    def close(self) -> None:
        self.flush()
        self._queue.put(self._STOP)
        self._thread.join(timeout=5)
        if self._thread.is_alive():
            raise RuntimeError("Global profile writer did not stop")
        # Initialization may fail before the queue has contained any work. Recheck
        # after joining so that this race cannot hide the real exception.
        self._raise_if_failed()

    @property
    def failure(self) -> GlobalProfileWriterError | None:
        return self._error

    def _raise_if_failed(self) -> None:
        if self._error is not None:
            raise self._error from self._error.cause

    def _run(self) -> None:
        try:
            with sqlite3.connect(self.path, timeout=30.0) as connection:
                connection.execute("PRAGMA busy_timeout = 30000")
                # Account sessions may start concurrently. Serialize schema
                # inspection/migration so two writers cannot race an ALTER.
                connection.execute("BEGIN IMMEDIATE")
                try:
                    self._initialize(connection)
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
                while True:
                    item = self._queue.get()
                    try:
                        if item is self._STOP:
                            return
                        assert isinstance(item, _WriteRequest)
                        self._active_request = item
                        self._save_with_retry(connection, item.update)
                        self._active_request = None
                    finally:
                        self._queue.task_done()
        except Exception as error:  # noqa: BLE001
            request = self._active_request
            failure = GlobalProfileWriterError(
                database=self.path,
                account=request.account if request is not None else self._account,
                operation=(
                    request.operation
                    if request is not None
                    else "Initialize global profile database"
                ),
                profile=request.update.username if request is not None else "",
                cause=error,
            )
            self._error = failure
            if self._logger is not None:
                self._logger.error(
                    "Global profile writer failed",
                    account=failure.account or "<unknown>",
                    operation=failure.operation,
                    profile=failure.profile or "<none>",
                    database=str(failure.database),
                    exception=f"{type(error).__name__}: {error}",
                )
                failure.reported = True
            while True:
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    break
                else:
                    self._queue.task_done()

    @classmethod
    def _save_with_retry(
        cls, connection: sqlite3.Connection, update: ProfileUpdate
    ) -> None:
        """Commit one update, tolerating brief contention from other sessions."""

        for attempt in range(5):
            try:
                cls._save(connection, update)
                connection.commit()
                return
            except sqlite3.OperationalError as error:
                connection.rollback()
                if not cls._is_contention(error) or attempt == 4:
                    raise
                time.sleep(0.1 * (attempt + 1))

    @staticmethod
    def _is_contention(error: sqlite3.OperationalError) -> bool:
        message = str(error).casefold()
        return "locked" in message or "busy" in message

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
        # Older databases may contain only a subset of the profile columns.
        # CREATE TABLE IF NOT EXISTS does not upgrade such tables, so migrate
        # every additive field explicitly before running data updates.
        existing_columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(profiles)").fetchall()
        }
        additions = {
            "full_name": "TEXT NOT NULL DEFAULT ''",
            "biography": "TEXT NOT NULL DEFAULT ''",
            "business_category": "TEXT NOT NULL DEFAULT ''",
            "website": "TEXT NOT NULL DEFAULT ''",
            "phone": "TEXT NOT NULL DEFAULT ''",
            "email": "TEXT NOT NULL DEFAULT ''",
            "address": "TEXT NOT NULL DEFAULT ''",
            "followers": "INTEGER",
            "following": "INTEGER",
            "posts": "INTEGER",
            "private": "INTEGER NOT NULL DEFAULT 0 CHECK (private IN (0, 1))",
            "business": "INTEGER NOT NULL DEFAULT 0 CHECK (business IN (0, 1))",
            "verified": "INTEGER NOT NULL DEFAULT 0 CHECK (verified IN (0, 1))",
            "follow_status": "TEXT NOT NULL DEFAULT ''",
            "source_account": "TEXT NOT NULL DEFAULT ''",
            "discovered_at": "TEXT NOT NULL DEFAULT ''",
            "updated_at": "TEXT NOT NULL DEFAULT ''",
        }
        for name, declaration in additions.items():
            if name not in existing_columns:
                connection.execute(
                    f'ALTER TABLE profiles ADD COLUMN "{name}" {declaration}'
                )
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
