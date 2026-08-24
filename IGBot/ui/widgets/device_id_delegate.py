from PySide6.QtCore import QEvent, QRect, QSize, Qt, Signal
from PySide6.QtGui import QHelpEvent, QMouseEvent, QPainter
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QToolTip

from IGBot.ui.icons import copy_icon


class DeviceIdDelegate(QStyledItemDelegate):
    """Paints a lightweight copy action beside each device identifier."""

    copy_requested = Signal(str)
    _ICON_SIZE = 16
    _ACTION_WIDTH = 30

    def paint(self, painter: QPainter, option, index) -> None:
        background_option = QStyleOptionViewItem(option)
        self.initStyleOption(background_option, index)
        background_option.text = ""
        super().paint(painter, background_option, index)

        text_option = QStyleOptionViewItem(option)
        text_option.rect = option.rect.adjusted(0, 0, -self._ACTION_WIDTH, 0)
        super().paint(painter, text_option, index)
        copy_icon().paint(painter, self._icon_rect(option.rect), Qt.AlignCenter)

    def editorEvent(self, event, model, option, index) -> bool:
        if event.type() != QEvent.MouseButtonRelease:
            return False
        if not isinstance(event, QMouseEvent) or event.button() != Qt.LeftButton:
            return False
        if not self._action_rect(option.rect).contains(event.position().toPoint()):
            return False
        self.copy_requested.emit(index.data(Qt.UserRole))
        return True

    def helpEvent(self, event, view, option, index) -> bool:
        if not isinstance(event, QHelpEvent):
            return False
        if self._action_rect(option.rect).contains(event.pos()):
            QToolTip.showText(event.globalPos(), "Copy Device ID", view)
            return True
        return False

    def _action_rect(self, cell_rect: QRect) -> QRect:
        return QRect(
            cell_rect.right() - self._ACTION_WIDTH + 1,
            cell_rect.top(),
            self._ACTION_WIDTH,
            cell_rect.height(),
        )

    def _icon_rect(self, cell_rect: QRect) -> QRect:
        action_rect = self._action_rect(cell_rect)
        size = QSize(self._ICON_SIZE, self._ICON_SIZE)
        return QRect(
            action_rect.center().x() - size.width() // 2,
            action_rect.center().y() - size.height() // 2,
            size.width(),
            size.height(),
        )
