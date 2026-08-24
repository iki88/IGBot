from dataclasses import dataclass

from PySide6.QtCore import QEvent, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QHelpEvent, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QStyle,
    QStyledItemDelegate,
    QToolTip,
)


@dataclass(frozen=True)
class _ActionButton:
    action: str
    text: str
    width: int
    icon: QStyle.StandardPixmap
    enabled: bool = True


class DeviceActionsDelegate(QStyledItemDelegate):
    """Draws scalable row actions without creating widgets per table row."""

    action_requested = Signal(str, str)
    _BUTTONS = (
        _ActionButton("manage", "Manage", 82, QStyle.SP_DirOpenIcon),
        _ActionButton("start", "Start", 70, QStyle.SP_MediaPlay, enabled=False),
        _ActionButton("delete", "", 42, QStyle.SP_TrashIcon),
    )
    _GAP = 6

    def paint(self, painter: QPainter, option, index) -> None:
        for button, rect in self._button_rects(option.rect):
            hovered = button.enabled and rect.contains(
                option.widget.mapFromGlobal(option.widget.cursor().pos())
            )
            background, border, foreground = self._colors(button, hovered)

            painter.save()
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(background)
            painter.setPen(QPen(border, 1))
            painter.drawRoundedRect(rect.adjusted(0, 0, -1, -1), 5, 5)

            icon = QApplication.style().standardIcon(button.icon)
            icon_size = QSize(13, 13)
            content_width = icon_size.width() + (5 if button.text else 0)
            if button.text:
                content_width += painter.fontMetrics().horizontalAdvance(button.text)
            content_left = rect.left() + (rect.width() - content_width) // 2
            icon_rect = QRect(
                content_left,
                rect.top() + (rect.height() - icon_size.height()) // 2,
                icon_size.width(),
                icon_size.height(),
            )
            icon.paint(painter, icon_rect, Qt.AlignCenter)
            if button.text:
                painter.setPen(foreground)
                text_rect = QRect(
                    icon_rect.right() + 5,
                    rect.top(),
                    rect.right() - icon_rect.right() - 5,
                    rect.height(),
                )
                painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, button.text)
            painter.restore()

    def editorEvent(self, event, model, option, index) -> bool:
        if event.type() != QEvent.MouseButtonRelease:
            return False
        mouse_event = event
        if (
            not isinstance(mouse_event, QMouseEvent)
            or mouse_event.button() != Qt.LeftButton
        ):
            return False

        serial = index.data(Qt.UserRole)
        for button, rect in self._button_rects(option.rect):
            if button.enabled and rect.contains(mouse_event.position().toPoint()):
                self.action_requested.emit(button.action, serial)
                return True
        return False

    def helpEvent(self, event, view, option, index) -> bool:
        if not isinstance(event, QHelpEvent):
            return False
        for button, rect in self._button_rects(option.rect):
            if rect.contains(event.pos()):
                tooltip = {
                    "manage": "Open phone accounts",
                    "start": "Available when session orchestration is implemented",
                    "delete": "Remove phone from IGBot",
                }[button.action]
                QToolTip.showText(event.globalPos(), tooltip, view)
                return True
        return False

    @staticmethod
    def _colors(button: _ActionButton, hovered: bool):
        if not button.enabled:
            return QColor("#161b22"), QColor("#30363d"), QColor("#6e7681")
        if button.action == "delete":
            return (
                QColor("#3d1f24" if hovered else "#21161a"),
                QColor("#f85149" if hovered else "#6e3035"),
                QColor("#ffb3ad"),
            )
        return (
            QColor("#1f6feb" if hovered else "#212d3b"),
            QColor("#388bfd" if hovered else "#3c526b"),
            QColor("#f0f6fc"),
        )

    def _button_rects(self, cell_rect: QRect):
        total_width = sum(button.width for button in self._BUTTONS) + self._GAP * 2
        left = cell_rect.left() + max(8, (cell_rect.width() - total_width) // 2)
        height = min(28, cell_rect.height() - 6)
        top = cell_rect.top() + (cell_rect.height() - height) // 2
        for button in self._BUTTONS:
            rect = QRect(left, top, button.width, height)
            yield button, rect
            left = rect.right() + self._GAP + 1
