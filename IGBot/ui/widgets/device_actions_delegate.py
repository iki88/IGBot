from dataclasses import dataclass

from PySide6.QtCore import QEvent, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QHelpEvent, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QStyledItemDelegate,
    QToolTip,
)

from IGBot.ui.icons import workspace_action_icon


@dataclass(frozen=True)
class _ActionButton:
    action: str
    width: int
    enabled: bool = True


class DeviceActionsDelegate(QStyledItemDelegate):
    """Draws scalable row actions without creating widgets per table row."""

    action_requested = Signal(str, str)
    _BUTTONS = (
        _ActionButton("start", 34),
        _ActionButton("manage", 34),
        _ActionButton("delete", 34),
    )
    _GAP = 6

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._armed_action: tuple[str, str] | None = None
        self._pressed_action: tuple[str, str] | None = None
        self._pressed_widget = None
        self._pressed_rect: QRect | None = None

    def paint(self, painter: QPainter, option, index) -> None:
        serial = index.data(Qt.UserRole)
        for button, rect in self._button_rects(option.rect):
            pressed = self._pressed_action == (serial, button.action)
            background, border, foreground = self._colors(button, pressed)

            painter.save()
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(background)
            painter.setPen(QPen(border, 1))
            painter.drawRoundedRect(rect.adjusted(0, 0, -1, -1), 5, 5)

            workspace_action_icon(button.action, foreground.name()).paint(
                painter, rect.adjusted(7, 7, -7, -7), Qt.AlignCenter
            )
            painter.restore()

    def editorEvent(self, event, model, option, index) -> bool:
        if event.type() not in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
            return False
        mouse_event = event
        if (
            not isinstance(mouse_event, QMouseEvent)
            or mouse_event.button() != Qt.LeftButton
        ):
            return False

        serial = index.data(Qt.UserRole)
        requested_action = None
        for button, rect in self._button_rects(option.rect):
            if button.enabled and rect.contains(mouse_event.position().toPoint()):
                requested_action = button.action
                break

        if event.type() == QEvent.MouseButtonPress:
            if requested_action is None:
                return False
            action_key = (serial, requested_action)
            self._armed_action = action_key
            self._reset_pressed()
            self._pressed_action = action_key
            self._pressed_widget = option.widget
            self._pressed_rect = QRect(option.rect)
            option.widget.update(option.rect)
            QTimer.singleShot(
                110,
                lambda: self._clear_pressed(action_key),
            )
            return True

        armed_action = self._armed_action
        self._armed_action = None
        self._reset_pressed()
        if requested_action is not None and armed_action == (serial, requested_action):
            self.action_requested.emit(requested_action, serial)
            return True
        return armed_action is not None

    def helpEvent(self, event, view, option, index) -> bool:
        if not isinstance(event, QHelpEvent):
            return False
        for button, rect in self._button_rects(option.rect):
            if rect.contains(event.pos()):
                tooltip = {
                    "manage": "Open phone accounts",
                    "start": "Start the persistent scheduler for this phone",
                    "delete": "Remove phone from IGBot",
                }[button.action]
                QToolTip.showText(event.globalPos(), tooltip, view)
                return True
        return False

    @staticmethod
    def _colors(button: _ActionButton, pressed: bool):
        if not button.enabled:
            return QColor("#202832"), QColor("#455261"), QColor("#9aa8b7")
        if button.action == "delete":
            return (
                QColor("#4a1f24" if pressed else "#21161a"),
                QColor("#f85149" if pressed else "#6e3035"),
                QColor("#ffb3ad"),
            )
        return (
            QColor("#173b66" if pressed else "#212d3b"),
            QColor("#388bfd" if pressed else "#3c526b"),
            QColor("#f0f6fc"),
        )

    def _clear_pressed(self, action_key: tuple[str, str]) -> None:
        if self._pressed_action == action_key:
            self._reset_pressed()

    def _reset_pressed(self) -> None:
        widget = self._pressed_widget
        rect = self._pressed_rect
        self._pressed_action = None
        self._pressed_widget = None
        self._pressed_rect = None
        if widget is not None and rect is not None:
            try:
                widget.update(rect)
            except RuntimeError:
                return

    def _button_rects(self, cell_rect: QRect):
        total_width = sum(button.width for button in self._BUTTONS) + self._GAP * 2
        left = cell_rect.left() + max(8, (cell_rect.width() - total_width) // 2)
        height = min(28, cell_rect.height() - 6)
        top = cell_rect.top() + (cell_rect.height() - height) // 2
        for button in self._BUTTONS:
            rect = QRect(left, top, button.width, height)
            yield button, rect
            left = rect.right() + self._GAP + 1
