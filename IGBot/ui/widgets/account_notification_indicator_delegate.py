from __future__ import annotations

import time

from PySide6.QtCore import QEvent, QRect, Qt, Signal
from PySide6.QtGui import QColor, QHelpEvent, QMouseEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolTip,
)

from IGBot.notifications import NotificationSeverity
from IGBot.ui.models.phone_accounts_model import PhoneAccountsModel


class AccountNotificationIndicatorDelegate(QStyledItemDelegate):
    """Paint and activate an account's warning indicator without database access."""

    history_requested = Signal(str)
    ICON_SIZE = 16
    HIT_SIZE = 24
    RIGHT_MARGIN = 7

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._visible = True
        self._last_activation: tuple[str, float] | None = None

    def set_indicators_visible(self, visible: bool) -> None:
        self._visible = visible
        if self.parent() is not None:
            self.parent().viewport().update()

    def indicator_rect(self, cell_rect: QRect) -> QRect:
        return QRect(
            cell_rect.right() - self.RIGHT_MARGIN - self.HIT_SIZE + 1,
            cell_rect.center().y() - self.HIT_SIZE // 2,
            self.HIT_SIZE,
            self.HIT_SIZE,
        )

    def paint(self, painter: QPainter, option, index) -> None:
        severity = self._severity(index)
        display = QStyleOptionViewItem(option)
        self.initStyleOption(display, index)
        if severity is not None:
            available = max(0, display.rect.width() - self.HIT_SIZE - 15)
            display.text = display.fontMetrics.elidedText(
                display.text, Qt.ElideRight, available
            )
        style = display.widget.style() if display.widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, display, painter, display.widget)
        if severity is None:
            return
        hit_rect = self.indicator_rect(option.rect)
        icon_rect = QRect(
            hit_rect.center().x() - self.ICON_SIZE // 2,
            hit_rect.center().y() - self.ICON_SIZE // 2,
            self.ICON_SIZE,
            self.ICON_SIZE,
        )
        self._paint_warning(painter, icon_rect, severity)

    def editorEvent(self, event, model, option, index) -> bool:
        if self._severity(index) is None or not isinstance(event, QMouseEvent):
            return False
        if event.button() != Qt.LeftButton or not self.indicator_rect(
            option.rect
        ).contains(event.position().toPoint()):
            return False
        if event.type() == QEvent.MouseButtonDblClick:
            return True
        if event.type() != QEvent.MouseButtonRelease:
            return event.type() == QEvent.MouseButtonPress
        username = str(index.data(Qt.UserRole) or "").strip()
        if not username:
            return True
        now = time.monotonic()
        if self._last_activation is not None:
            previous_username, previous_time = self._last_activation
            interval = QApplication.doubleClickInterval() / 1000 + 0.1
            if (
                previous_username.casefold() == username.casefold()
                and (now - previous_time) <= interval
            ):
                return True
        self._last_activation = (username, now)
        self.history_requested.emit(username)
        return True

    def helpEvent(self, event, view, option, index) -> bool:
        if (
            self._severity(index) is not None
            and isinstance(event, QHelpEvent)
            and self.indicator_rect(option.rect).contains(event.pos())
        ):
            QToolTip.showText(event.globalPos(), "View Account Notifications", view)
            return True
        QToolTip.hideText()
        return False

    def recently_activated(self, username: str) -> bool:
        if self._last_activation is None:
            return False
        previous_username, previous_time = self._last_activation
        interval = QApplication.doubleClickInterval() / 1000 + 0.1
        return (
            previous_username.casefold() == username.strip().casefold()
            and time.monotonic() - previous_time <= interval
        )

    def _severity(self, index) -> NotificationSeverity | None:
        if not self._visible:
            return None
        value = index.data(PhoneAccountsModel.ActiveNotificationSeverityRole)
        try:
            severity = NotificationSeverity(str(value))
        except ValueError:
            return None
        return severity if severity is not NotificationSeverity.INFO else None

    @staticmethod
    def _paint_warning(
        painter: QPainter, rectangle: QRect, severity: NotificationSeverity
    ) -> None:
        color = QColor(
            "#EF4444" if severity is NotificationSeverity.CRITICAL else "#F59E0B"
        )
        path = QPainterPath()
        path.moveTo(rectangle.center().x(), rectangle.top() + 1)
        path.lineTo(rectangle.right() - 1, rectangle.bottom() - 1)
        path.lineTo(rectangle.left() + 1, rectangle.bottom() - 1)
        path.closeSubpath()
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(color, 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPath(path)
        center_x = rectangle.center().x()
        painter.drawLine(center_x, rectangle.top() + 6, center_x, rectangle.top() + 10)
        painter.drawPoint(center_x, rectangle.top() + 13)
        painter.restore()
