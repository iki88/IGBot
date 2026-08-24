from dataclasses import dataclass

from PySide6.QtCore import QEvent, QRect, QSize, Qt, Signal
from PySide6.QtGui import QMouseEvent, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionButton,
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
        _ActionButton("manage", "Manage", 92, QStyle.SP_DirOpenIcon),
        _ActionButton("start", "Start", 78, QStyle.SP_MediaPlay, enabled=False),
        _ActionButton("delete", "Delete", 82, QStyle.SP_TrashIcon),
    )
    _GAP = 6

    def paint(self, painter: QPainter, option, index) -> None:
        for button, rect in self._button_rects(option.rect):
            button_option = QStyleOptionButton()
            button_option.rect = rect
            button_option.text = button.text
            button_option.icon = QApplication.style().standardIcon(button.icon)
            button_option.iconSize = QSize(14, 14)
            button_option.state = (
                QStyle.State_Enabled if button.enabled else QStyle.State_None
            )
            if button.enabled and rect.contains(
                option.widget.mapFromGlobal(option.widget.cursor().pos())
            ):
                button_option.state |= QStyle.State_MouseOver
            QApplication.style().drawControl(
                QStyle.CE_PushButton, button_option, painter, option.widget
            )

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

    def _button_rects(self, cell_rect: QRect):
        total_width = sum(button.width for button in self._BUTTONS) + self._GAP * 2
        left = cell_rect.left() + max(8, (cell_rect.width() - total_width) // 2)
        height = min(30, cell_rect.height() - 8)
        top = cell_rect.top() + (cell_rect.height() - height) // 2
        for button in self._BUTTONS:
            rect = QRect(left, top, button.width, height)
            yield button, rect
            left = rect.right() + self._GAP + 1
