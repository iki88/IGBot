"""SQLite storage for global notifications and account lifecycle state."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Self


class NotificationsDatabase:
    def __init__(self, workspace: str | Path) -> None:
        self.path = Path(workspace) / "Notifications" / "notifications.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, timeout=30)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self._initialize()

    def _initialize(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL COLLATE NOCASE,
                device TEXT NOT NULL DEFAULT '',
                tag TEXT NOT NULL DEFAULT '',
                severity TEXT NOT NULL,
                type TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
                occurrences INTEGER NOT NULL DEFAULT 1 CHECK (occurrences > 0),
                detected_at TEXT NOT NULL,
                last_detected_at TEXT NOT NULL,
                resolved_at TEXT,
                details TEXT NOT NULL DEFAULT ''
            );
            CREATE UNIQUE INDEX IF NOT EXISTS uq_active_notification
                ON notifications(username, type) WHERE active = 1;
            CREATE INDEX IF NOT EXISTS ix_notifications_active
                ON notifications(active, severity, last_detected_at DESC);

            CREATE TABLE IF NOT EXISTS account_lifecycle (
                account_key TEXT PRIMARY KEY,
                username TEXT NOT NULL COLLATE NOCASE,
                device TEXT NOT NULL DEFAULT '',
                tag TEXT NOT NULL DEFAULT '',
                first_successful_session_at TEXT,
                consecutive_zero_interaction_sessions INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            );
            """
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args) -> None:
        self.close()
