"""Detector-independent notification persistence API."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from IGBot.notifications.database import NotificationsDatabase
from IGBot.notifications.models import (
    Notification,
    NotificationSeverity,
    NotificationType,
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


class NotificationService:
    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace)
        # Eagerly initialize the global schema.
        with NotificationsDatabase(self.workspace):
            pass

    def create(
        self,
        username: str,
        notification_type: NotificationType,
        severity: NotificationSeverity,
        *,
        device: str = "",
        tag: str = "",
        details: str = "",
    ) -> Notification:
        """Create or redetect the single active account/type notification."""
        now = _utc_now()
        with NotificationsDatabase(self.workspace) as database:
            row = database.connection.execute(
                "SELECT id FROM notifications WHERE username = ? AND type = ? AND active = 1",
                (username, notification_type.value),
            ).fetchone()
            if row is None:
                cursor = database.connection.execute(
                    """INSERT INTO notifications
                       (username, device, tag, severity, type, active, occurrences,
                        detected_at, last_detected_at, resolved_at, details)
                       VALUES (?, ?, ?, ?, ?, 1, 1, ?, ?, NULL, ?)""",
                    (
                        username,
                        device,
                        tag,
                        severity.value,
                        notification_type.value,
                        now,
                        now,
                        details,
                    ),
                )
                notification_id = int(cursor.lastrowid)
            else:
                notification_id = int(row["id"])
                database.connection.execute(
                    """UPDATE notifications
                       SET device = ?, tag = ?, severity = ?, details = ?,
                           occurrences = occurrences + 1, last_detected_at = ?
                       WHERE id = ?""",
                    (device, tag, severity.value, details, now, notification_id),
                )
            database.connection.commit()
            return self._by_id(database, notification_id)

    def update(self, notification_id: int, **changes: object) -> Notification:
        allowed = {"device", "tag", "severity", "details"}
        values = {key: value for key, value in changes.items() if key in allowed}
        if not values:
            raise ValueError("No supported notification changes were supplied.")
        if isinstance(values.get("severity"), NotificationSeverity):
            values["severity"] = values["severity"].value
        assignments = ", ".join(f"{key} = ?" for key in values)
        with NotificationsDatabase(self.workspace) as database:
            database.connection.execute(
                f"UPDATE notifications SET {assignments} WHERE id = ?",
                (*values.values(), notification_id),
            )
            database.connection.commit()
            return self._by_id(database, notification_id)

    def resolve(self, username: str, notification_type: NotificationType) -> bool:
        with NotificationsDatabase(self.workspace) as database:
            cursor = database.connection.execute(
                """UPDATE notifications SET active = 0, resolved_at = ?
                   WHERE username = ? AND type = ? AND active = 1""",
                (_utc_now(), username, notification_type.value),
            )
            database.connection.commit()
            return cursor.rowcount > 0

    def reconcile_zero_interactions_day(
        self,
        *,
        account_key: str,
        username: str,
        device: str,
        tag: str,
        evidence_date: date,
        total_interactions: int | None,
    ) -> str:
        """Atomically reconcile one recorded UTC analytics day exactly once."""

        evidence = evidence_date.isoformat()
        now = _utc_now()
        with NotificationsDatabase(self.workspace) as database:
            connection = database.connection
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT last_zero_interactions_evaluated_date FROM account_lifecycle "
                "WHERE account_key = ?",
                (account_key,),
            ).fetchone()
            if row is not None and row[0] == evidence:
                connection.rollback()
                return "already_evaluated"

            connection.execute(
                """INSERT INTO account_lifecycle
                   (account_key, username, device, tag, first_successful_session_at,
                    consecutive_zero_interaction_sessions,
                    last_zero_interactions_evaluated_date, updated_at)
                   VALUES (?, ?, ?, ?, ?, 0, ?, ?)
                   ON CONFLICT(account_key) DO UPDATE SET
                     username=excluded.username, device=excluded.device,
                     tag=excluded.tag,
                     first_successful_session_at=COALESCE(
                       account_lifecycle.first_successful_session_at,
                       excluded.first_successful_session_at),
                     consecutive_zero_interaction_sessions=0,
                     last_zero_interactions_evaluated_date=
                       excluded.last_zero_interactions_evaluated_date,
                     updated_at=excluded.updated_at""",
                (account_key, username, device, tag, now, evidence, now),
            )

            outcome = "unchanged"
            if total_interactions is None:
                outcome = "no_row"
            elif total_interactions > 0:
                cursor = connection.execute(
                    """UPDATE notifications SET active = 0, resolved_at = ?
                       WHERE username = ? AND type = ? AND active = 1""",
                    (now, username, NotificationType.ZERO_INTERACTIONS.value),
                )
                if cursor.rowcount:
                    outcome = "resolved"
            else:
                critical_types = (
                    NotificationType.HUMAN_CAPTCHA.value,
                    NotificationType.ACCOUNT_DISABLED.value,
                )
                critical = connection.execute(
                    """SELECT 1 FROM notifications
                       WHERE username = ? AND type IN (?, ?)
                         AND (substr(detected_at, 1, 10) = ?
                              OR substr(last_detected_at, 1, 10) = ?)
                       LIMIT 1""",
                    (username, *critical_types, evidence, evidence),
                ).fetchone()
                if critical is not None:
                    outcome = "suppressed_by_critical"
                else:
                    active = connection.execute(
                        """SELECT id FROM notifications
                           WHERE username = ? AND type = ? AND active = 1""",
                        (username, NotificationType.ZERO_INTERACTIONS.value),
                    ).fetchone()
                    if active is None:
                        connection.execute(
                            """INSERT INTO notifications
                               (username, device, tag, severity, type, active,
                                occurrences, detected_at, last_detected_at,
                                resolved_at, details)
                               VALUES (?, ?, ?, ?, ?, 1, 1, ?, ?, NULL, ?)""",
                            (
                                username,
                                device,
                                tag,
                                NotificationSeverity.WARNING.value,
                                NotificationType.ZERO_INTERACTIONS.value,
                                now,
                                now,
                                f"No verified interactions were recorded on {evidence}.",
                            ),
                        )
                        outcome = "created"
            connection.commit()
            return outcome

    def resolve_all_for_account(self, username: str) -> int:
        """Resolve every active notification owned by one account atomically."""

        with NotificationsDatabase(self.workspace) as database:
            cursor = database.connection.execute(
                """UPDATE notifications SET active = 0, resolved_at = ?
                   WHERE username = ? AND active = 1""",
                (_utc_now(), username),
            )
            database.connection.commit()
            return cursor.rowcount

    def resolve_blocking_for_account(self, username: str) -> int:
        """Resolve active native blocking-screen notifications."""

        types = (
            NotificationType.HUMAN_CAPTCHA.value,
            NotificationType.ACCOUNT_DISABLED.value,
        )
        with NotificationsDatabase(self.workspace) as database:
            cursor = database.connection.execute(
                """UPDATE notifications SET active = 0, resolved_at = ?
                   WHERE username = ? AND active = 1 AND type IN (?, ?)""",
                (_utc_now(), username, *types),
            )
            database.connection.commit()
            return cursor.rowcount

    def purge_account(
        self, username: str, account_directory: str | Path
    ) -> tuple[int, int]:
        """Permanently remove notification state owned by one deleted account."""

        normalized_username = username.strip()
        account_key = str(Path(account_directory).resolve()).casefold()
        with (
            NotificationsDatabase(self.workspace) as database,
            database.connection,
        ):
            notifications = database.connection.execute(
                "DELETE FROM notifications WHERE username = ?",
                (normalized_username,),
            ).rowcount
            lifecycle = database.connection.execute(
                "DELETE FROM account_lifecycle WHERE account_key = ?",
                (account_key,),
            ).rowcount
        return notifications, lifecycle

    def blocking_detected_on_local_date(
        self, username: str, local_date: date, *, timezone=None
    ) -> bool:
        """Return whether a persisted blocker was detected on ``local_date``."""

        types = (
            NotificationType.HUMAN_CAPTCHA.value,
            NotificationType.ACCOUNT_DISABLED.value,
        )
        with NotificationsDatabase(self.workspace) as database:
            row = database.connection.execute(
                """SELECT last_detected_at FROM notifications
                   WHERE username = ? AND type IN (?, ?)
                   ORDER BY last_detected_at DESC LIMIT 1""",
                (username, *types),
            ).fetchone()
        if row is None:
            return False
        detected = datetime.fromisoformat(str(row["last_detected_at"]))
        if detected.tzinfo is None or detected.utcoffset() is None:
            detected = detected.replace(tzinfo=UTC)
        zone = timezone or datetime.now().astimezone().tzinfo
        return detected.astimezone(zone).date() == local_date

    def active(self) -> tuple[Notification, ...]:
        return self._query("active = 1")

    def resolved(self) -> tuple[Notification, ...]:
        return self._query("active = 0")

    def all(self) -> tuple[Notification, ...]:
        return self._query("1 = 1")

    def history_for_account(self, username: str) -> tuple[Notification, ...]:
        """Return one account's complete history, active first and newest first."""

        normalized = username.strip()
        if not normalized:
            return ()
        with NotificationsDatabase(self.workspace) as database:
            rows = database.connection.execute(
                """SELECT * FROM notifications
                   WHERE username = ?
                   ORDER BY active DESC, last_detected_at DESC""",
                (normalized,),
            ).fetchall()
            return tuple(self._notification(row) for row in rows)

    def active_severity_by_username(self) -> dict[str, NotificationSeverity]:
        """Return one highest active badge severity per normalized username."""

        with NotificationsDatabase(self.workspace) as database:
            rows = database.connection.execute(
                """SELECT username,
                          MAX(CASE severity
                                WHEN 'CRITICAL' THEN 2
                                WHEN 'WARNING' THEN 1
                                ELSE 0 END) AS priority
                   FROM notifications
                   WHERE active = 1
                   GROUP BY username"""
            ).fetchall()
        severities = {
            2: NotificationSeverity.CRITICAL,
            1: NotificationSeverity.WARNING,
        }
        return {
            str(row["username"]).strip().casefold(): severities[int(row["priority"])]
            for row in rows
            if int(row["priority"]) in severities
        }

    def count_active(self, *, badge_only: bool = False) -> int:
        clause = "active = 1"
        parameters: tuple[str, ...] = ()
        if badge_only:
            clause += " AND severity IN (?, ?)"
            parameters = (
                NotificationSeverity.CRITICAL.value,
                NotificationSeverity.WARNING.value,
            )
        with NotificationsDatabase(self.workspace) as database:
            row = database.connection.execute(
                f"SELECT COUNT(*) AS total FROM notifications WHERE {clause}",
                parameters,
            ).fetchone()
            return int(row["total"])

    def _query(self, clause: str) -> tuple[Notification, ...]:
        with NotificationsDatabase(self.workspace) as database:
            rows = database.connection.execute(
                f"SELECT * FROM notifications WHERE {clause} ORDER BY last_detected_at DESC"
            ).fetchall()
            return tuple(self._notification(row) for row in rows)

    @classmethod
    def _by_id(
        cls, database: NotificationsDatabase, notification_id: int
    ) -> Notification:
        row = database.connection.execute(
            "SELECT * FROM notifications WHERE id = ?", (notification_id,)
        ).fetchone()
        if row is None:
            raise LookupError(f"Notification {notification_id} does not exist.")
        return cls._notification(row)

    @staticmethod
    def _notification(row) -> Notification:
        return Notification(
            id=int(row["id"]),
            username=str(row["username"]),
            device=str(row["device"]),
            tag=str(row["tag"]),
            severity=NotificationSeverity(row["severity"]),
            type=NotificationType(row["type"]),
            active=bool(row["active"]),
            occurrences=int(row["occurrences"]),
            detected_at=str(row["detected_at"]),
            last_detected_at=str(row["last_detected_at"]),
            resolved_at=row["resolved_at"],
            details=str(row["details"]),
        )
