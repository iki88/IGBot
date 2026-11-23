from __future__ import annotations

import ctypes
import sys
from datetime import UTC, datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from IGBot.notifications import Notification


def _local_time(value: str | None) -> str:
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return value
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone().strftime("%d %b %Y, %H:%M")


def _enable_native_dark_title_bar(dialog: QDialog) -> bool:
    """Request Windows' native dark title bar without replacing window chrome."""
    if sys.platform != "win32":
        return False
    try:
        enabled = ctypes.c_int(1)
        window_handle = int(dialog.winId())
        dwmapi = ctypes.windll.dwmapi
        for attribute in (20, 19):
            result = dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(window_handle),
                attribute,
                ctypes.byref(enabled),
                ctypes.sizeof(enabled),
            )
            if result == 0:
                return True
    except (AttributeError, OSError, TypeError, ValueError):
        pass
    return False


class AccountNotificationHistoryDialog(QDialog):
    """Compact, read-only history for one Instagram account."""

    _DIALOG_WIDTH = 570
    _MIN_DIALOG_WIDTH = 540
    _MAX_DIALOG_WIDTH = 600
    _MAX_DIALOG_HEIGHT = 600
    _MIN_HISTORY_HEIGHT = 88
    _MAX_HISTORY_HEIGHT = 430

    def __init__(
        self,
        username: str,
        notifications: tuple[Notification, ...],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("accountNotificationHistoryDialog")
        self.setWindowTitle("Account Notifications")
        self.setModal(True)
        self.setMinimumWidth(self._MIN_DIALOG_WIDTH)
        self.setMaximumWidth(self._MAX_DIALOG_WIDTH)
        self.setMinimumHeight(230)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.notifications = notifications
        self.entries: list[QFrame] = []
        self._native_dark_title_bar_applied = False

        title = QLabel("Account Notifications", self)
        title.setObjectName("dialogTitle")
        account = QLabel(username, self)
        account.setObjectName("notificationHistoryUsername")
        active_count = sum(item.active for item in notifications)
        active = QLabel(f"{active_count} active", self)
        active.setObjectName("notificationHistoryActiveCount")
        active.setVisible(active_count > 0)
        self.active_count_label = active

        heading_text = QVBoxLayout()
        heading_text.setContentsMargins(0, 0, 0, 0)
        heading_text.setSpacing(2)
        heading_text.addWidget(title)
        heading_text.addWidget(account)
        heading = QHBoxLayout()
        heading.setContentsMargins(0, 0, 0, 0)
        heading.addLayout(heading_text)
        heading.addStretch()
        heading.addWidget(active, 0, Qt.AlignTop)

        contents = QWidget(self)
        contents.setObjectName("notificationHistoryContents")
        self.history_layout = QVBoxLayout(contents)
        self.history_layout.setContentsMargins(0, 0, 0, 0)
        self.history_layout.setSpacing(8)
        if notifications:
            for notification in notifications:
                entry = self._entry(notification, contents)
                self.entries.append(entry)
                self.history_layout.addWidget(entry)
        else:
            empty_title = QLabel("No notification history.", contents)
            empty_title.setObjectName("notificationHistoryEmptyTitle")
            empty_title.setAlignment(Qt.AlignCenter)
            empty_detail = QLabel(
                "Notifications for this account will appear here.", contents
            )
            empty_detail.setObjectName("notificationHistoryEmptyDetail")
            empty_detail.setAlignment(Qt.AlignCenter)
            self.history_layout.addStretch()
            self.history_layout.addWidget(empty_title)
            self.history_layout.addWidget(empty_detail)
            self.history_layout.addStretch()
        self.history_contents = contents

        scroll = QScrollArea(self)
        scroll.setObjectName("notificationHistoryScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        scroll.setWidget(contents)
        self.scroll = scroll

        close = QPushButton("Close", self)
        close.setObjectName("secondaryButton")
        close.setMinimumWidth(88)
        close.clicked.connect(self.accept)
        close.setDefault(True)
        footer = QHBoxLayout()
        footer.setContentsMargins(0, 6, 0, 0)
        footer.addStretch()
        footer.addWidget(close)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(14)
        layout.addLayout(heading)
        layout.addWidget(scroll)
        layout.addLayout(footer)
        self._fit_to_content()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._native_dark_title_bar_applied = _enable_native_dark_title_bar(self)
        self._fit_to_content()
        self._center_over_parent()

    def _fit_to_content(self) -> None:
        """Size the history viewport to its entries, then cap it for scrolling."""
        width = self._DIALOG_WIDTH
        content_width = width - 64
        self.history_contents.setMinimumWidth(content_width)
        self.history_layout.activate()
        content_height = self.history_layout.heightForWidth(content_width)
        if content_height < 0:
            content_height = self.history_contents.sizeHint().height()
        history_height = max(
            self._MIN_HISTORY_HEIGHT,
            min(content_height + 2, self._MAX_HISTORY_HEIGHT),
        )
        self.scroll.setMinimumHeight(history_height)
        self.scroll.setMaximumHeight(history_height)

        layout = self.layout()
        if layout is not None:
            layout.activate()
            target_height = layout.sizeHint().height()
        else:
            target_height = history_height
        available_height = self._available_height()
        maximum_height = min(self._MAX_DIALOG_HEIGHT, available_height)
        if target_height > maximum_height:
            overflow = target_height - maximum_height
            history_height = max(self._MIN_HISTORY_HEIGHT, history_height - overflow)
            self.scroll.setMinimumHeight(history_height)
            self.scroll.setMaximumHeight(history_height)
            target_height = maximum_height
        self.setMaximumHeight(maximum_height)
        self.resize(width, target_height)

    def _available_height(self) -> int:
        parent = self.parentWidget()
        screen = parent.screen() if parent is not None else self.screen()
        if screen is None:
            screen = QApplication.primaryScreen()
        if screen is None:
            return self._MAX_DIALOG_HEIGHT
        return max(260, int(screen.availableGeometry().height() * 0.88))

    def _center_over_parent(self) -> None:
        parent = self.parentWidget()
        if parent is None or not parent.isVisible():
            return
        frame = self.frameGeometry()
        frame.moveCenter(parent.window().frameGeometry().center())
        self.move(frame.topLeft())

    @staticmethod
    def _entry(notification: Notification, parent: QWidget) -> QFrame:
        entry = QFrame(parent)
        entry.setObjectName("notificationHistoryEntry")
        entry.setProperty("severity", notification.severity.value.lower())

        severity = QLabel("⚠", entry)
        severity.setObjectName("notificationHistorySeverity")
        severity.setProperty("severity", notification.severity.value.lower())
        notification_type = QLabel(
            notification.type.value.replace("_", " ").title(), entry
        )
        notification_type.setObjectName("notificationHistoryType")
        status = QLabel("Active" if notification.active else "Resolved", entry)
        status.setObjectName("notificationHistoryStatus")
        status.setProperty("active", notification.active)
        status.setProperty("severity", notification.severity.value.lower())

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        header.addWidget(severity)
        header.addWidget(notification_type)
        header.addStretch()
        header.addWidget(status)

        metadata = [f"First detected: {_local_time(notification.detected_at)}"]
        if notification.last_detected_at != notification.detected_at:
            metadata.append(
                f"Latest detected: {_local_time(notification.last_detected_at)}"
            )
        if notification.occurrences > 1:
            metadata.append(f"Occurrences: {notification.occurrences}")
        if not notification.active and notification.resolved_at:
            metadata.append(f"Resolved: {_local_time(notification.resolved_at)}")
        facts = QLabel("\n".join(metadata), entry)
        facts.setObjectName("notificationHistoryMetadata")
        facts.setWordWrap(True)

        detail = QLabel(notification.details or "No additional details.", entry)
        detail.setObjectName("notificationHistoryDescription")
        detail.setWordWrap(True)
        detail.setTextInteractionFlags(Qt.TextSelectableByMouse)

        body = QVBoxLayout(entry)
        body.setContentsMargins(13, 12, 13, 12)
        body.setSpacing(6)
        body.addLayout(header)
        body.addWidget(facts)
        body.addWidget(detail)
        return entry
