"""Runtime condition detectors built on the generic notification service."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from IGBot.notifications.database import NotificationsDatabase
from IGBot.notifications.service import NotificationService


class ZeroInteractionsDetector:
    def __init__(self, service: NotificationService) -> None:
        self.service = service

    def register_account(
        self, *, account_directory: str | Path, username: str, device: str, tag: str
    ) -> None:
        """Ensure a new account has lifecycle state with a NULL first session."""
        now = datetime.now(UTC).isoformat()
        account_key = str(Path(account_directory).resolve()).casefold()
        with NotificationsDatabase(self.service.workspace) as database:
            database.connection.execute(
                """INSERT INTO account_lifecycle
                   (account_key, username, device, tag, first_successful_session_at,
                    consecutive_zero_interaction_sessions, updated_at)
                   VALUES (?, ?, ?, ?, NULL, 0, ?)
                   ON CONFLICT(account_key) DO UPDATE SET
                     username=excluded.username, device=excluded.device,
                     tag=excluded.tag, updated_at=excluded.updated_at""",
                (account_key, username, device, tag, now),
            )
            database.connection.commit()

    def evaluate_previous_day(
        self,
        *,
        account_directory: str | Path,
        username: str,
        device: str,
        tag: str,
        now: datetime | None = None,
    ) -> str:
        """Reconcile the previous recorded UTC analytics day once."""

        current = (now or datetime.now(UTC)).astimezone(UTC)
        previous_date = current.date() - timedelta(days=1)
        analytics_path = Path(account_directory) / "analytics.db"
        if not analytics_path.is_file():
            return "no_database"
        uri = f"{analytics_path.resolve().as_uri()}?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=5) as connection:
            row = connection.execute(
                """SELECT COALESCE(followed, 0), COALESCE(unfollowed, 0),
                          COALESCE(liked, 0), COALESCE(dm, 0)
                   FROM daily_summary WHERE date = ?""",
                (previous_date.isoformat(),),
            ).fetchone()
        account_key = str(Path(account_directory).resolve()).casefold()
        return self.service.reconcile_zero_interactions_day(
            account_key=account_key,
            username=username,
            device=device,
            tag=tag,
            evidence_date=previous_date,
            total_interactions=(
                None if row is None else sum(max(0, int(value or 0)) for value in row)
            ),
        )
