from datetime import UTC, datetime, timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel

from IGBot.notifications import Notification, NotificationSeverity, NotificationType
from IGBot.ui.widgets.account_notification_history_dialog import (
    AccountNotificationHistoryDialog,
    _local_time,
)


def _notification(
    notification_id: int,
    *,
    active: bool,
    severity: NotificationSeverity,
    notification_type: NotificationType,
    detected_at: str,
    last_detected_at: str | None = None,
    resolved_at: str | None = None,
    occurrences: int = 1,
    details: str | None = None,
) -> Notification:
    return Notification(
        id=notification_id,
        username="example",
        device="phone-1",
        tag="tag",
        severity=severity,
        type=notification_type,
        active=active,
        occurrences=occurrences,
        detected_at=detected_at,
        last_detected_at=last_detected_at or detected_at,
        resolved_at=resolved_at,
        details=details or f"Details for {notification_type.value}",
    )


def test_history_dialog_renders_complete_scrollable_history_in_local_time():
    application = QApplication.instance() or QApplication([])
    first = datetime(2026, 11, 18, 8, 5, tzinfo=UTC)
    latest = first + timedelta(hours=2)
    resolved_time = first + timedelta(days=1)
    notifications = (
        _notification(
            1,
            active=True,
            severity=NotificationSeverity.WARNING,
            notification_type=NotificationType.ZERO_INTERACTIONS,
            detected_at=first.isoformat(),
            last_detected_at=latest.isoformat(),
            occurrences=3,
        ),
        _notification(
            2,
            active=False,
            severity=NotificationSeverity.CRITICAL,
            notification_type=NotificationType.HUMAN_CAPTCHA,
            detected_at=first.isoformat(),
            resolved_at=resolved_time.isoformat(),
        ),
    )

    dialog = AccountNotificationHistoryDialog("example", notifications)
    labels = [label.text() for label in dialog.findChildren(QLabel)]

    assert dialog.isModal()
    assert dialog.scroll.widgetResizable()
    assert 540 <= dialog.width() <= 600
    assert dialog.height() <= 600
    assert len(dialog.entries) == 2
    assert "1 active" in labels
    assert "Zero Interactions" in labels
    assert "Human Captcha" in labels
    assert any("Occurrences: 3" in text for text in labels)
    assert any(
        f"First detected: {_local_time(first.isoformat())}" in text for text in labels
    )
    assert any(
        f"Resolved: {_local_time(resolved_time.isoformat())}" in text for text in labels
    )
    assert application is not None


def test_history_dialog_handles_empty_history():
    QApplication.instance() or QApplication([])
    dialog = AccountNotificationHistoryDialog("example", ())
    labels = [label.text() for label in dialog.findChildren(QLabel)]

    assert dialog.entries == []
    assert not dialog.active_count_label.isVisible()
    assert "No notification history." in labels


def test_history_dialog_is_compact_for_one_notification():
    QApplication.instance() or QApplication([])
    now = datetime(2026, 11, 18, 8, 5, tzinfo=UTC).isoformat()
    dialog = AccountNotificationHistoryDialog(
        "example",
        (
            _notification(
                1,
                active=True,
                severity=NotificationSeverity.WARNING,
                notification_type=NotificationType.ZERO_INTERACTIONS,
                detected_at=now,
            ),
        ),
    )

    assert 230 <= dialog.height() <= 300
    assert dialog.scroll.maximumHeight() < dialog._MAX_HISTORY_HEIGHT


def test_history_dialog_caps_long_history_and_keeps_descriptions_wrapped():
    QApplication.instance() or QApplication([])
    now = datetime(2026, 11, 18, 8, 5, tzinfo=UTC).isoformat()
    notifications = tuple(
        _notification(
            index,
            active=index == 1,
            severity=(
                NotificationSeverity.CRITICAL
                if index % 2
                else NotificationSeverity.WARNING
            ),
            notification_type=(
                NotificationType.HUMAN_CAPTCHA
                if index % 2
                else NotificationType.ZERO_INTERACTIONS
            ),
            detected_at=now,
            details=("A longer notification description that must wrap cleanly. " * 5),
        )
        for index in range(1, 13)
    )
    dialog = AccountNotificationHistoryDialog("example", notifications)

    descriptions = [
        label
        for label in dialog.findChildren(QLabel)
        if label.objectName() == "notificationHistoryDescription"
    ]
    assert dialog.height() <= 600
    assert dialog.scroll.maximumHeight() == dialog._MAX_HISTORY_HEIGHT
    assert dialog.scroll.verticalScrollBarPolicy() != Qt.ScrollBarAlwaysOff
    assert dialog.history_contents.sizeHint().height() > dialog.scroll.maximumHeight()
    assert all(label.wordWrap() for label in descriptions)
