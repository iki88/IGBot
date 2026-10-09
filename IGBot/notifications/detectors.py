"""Runtime condition detectors built on the generic notification service."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from IGBot.notifications.database import NotificationsDatabase
from IGBot.notifications.models import NotificationSeverity, NotificationType
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

    def record_completed_session(
        self,
        *,
        account_directory: str | Path,
        username: str,
        device: str,
        tag: str,
        verified_interactions: int,
    ) -> None:
        """Persist lifecycle state and reconcile the zero-interaction warning."""
        now = datetime.now(UTC).isoformat()
        account_key = str(Path(account_directory).resolve()).casefold()
        with NotificationsDatabase(self.service.workspace) as database:
            row = database.connection.execute(
                "SELECT * FROM account_lifecycle WHERE account_key = ?", (account_key,)
            ).fetchone()
            first_success = row["first_successful_session_at"] if row else None
            streak = int(row["consecutive_zero_interaction_sessions"]) if row else 0
            if first_success is None:
                first_success = now
            streak = streak + 1 if verified_interactions == 0 else 0
            database.connection.execute(
                """INSERT INTO account_lifecycle
                   (account_key, username, device, tag, first_successful_session_at,
                    consecutive_zero_interaction_sessions, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(account_key) DO UPDATE SET
                     username=excluded.username, device=excluded.device, tag=excluded.tag,
                     first_successful_session_at=COALESCE(account_lifecycle.first_successful_session_at,
                                                          excluded.first_successful_session_at),
                     consecutive_zero_interaction_sessions=excluded.consecutive_zero_interaction_sessions,
                     updated_at=excluded.updated_at""",
                (account_key, username, device, tag, first_success, streak, now),
            )
            database.connection.commit()

        if verified_interactions > 0:
            self.service.resolve(username, NotificationType.ZERO_INTERACTIONS)
        elif streak >= 2:
            self.service.create(
                username,
                NotificationType.ZERO_INTERACTIONS,
                NotificationSeverity.WARNING,
                device=device,
                tag=tag,
                details="Two or more consecutive completed sessions produced no verified interactions.",
            )
