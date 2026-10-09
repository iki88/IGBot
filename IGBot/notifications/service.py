"""Detector-independent notification persistence API."""

from __future__ import annotations

from datetime import UTC, datetime
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

    def active(self) -> tuple[Notification, ...]:
        return self._query("active = 1")

    def resolved(self) -> tuple[Notification, ...]:
        return self._query("active = 0")

    def all(self) -> tuple[Notification, ...]:
        return self._query("1 = 1")

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
