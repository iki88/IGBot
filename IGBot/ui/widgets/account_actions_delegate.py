from dataclasses import dataclass

from PySide6.QtCore import QEvent, QRect, Qt, Signal
from PySide6.QtGui import QColor, QHelpEvent, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QStyledItemDelegate, QToolTip

from IGBot.ui.icons import workspace_action_icon
from IGBot.ui.models.phone_accounts_model import PhoneAccountsModel


@dataclass(frozen=True)
class _AccountAction:
    name: str
    tooltip: str


class AccountActionsDelegate(QStyledItemDelegate):
    """Paint compact account actions without allocating widgets per row."""

    action_requested = Signal(str, object)
    ACTIONS = (
        _AccountAction("analytics", "Analytics"),
        _AccountAction("edit", "Edit Account"),
    )
    ARCHIVE_ACTION = _AccountAction("archive", "Archive Account")
    BUTTON_SIZE = 28
    GAP = 5

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._archive_visible = False

    def set_archive_visible(self, visible: bool) -> None:
        self._archive_visible = visible
        if self.parent() is not None:
            self.parent().viewport().update()

    def paint(self, painter: QPainter, option, index) -> None:
        account = index.data(PhoneAccountsModel.AccountRole)
        if account is None:
            return
        for action, rect in self._action_rects(option.rect):
            enabled = self._is_enabled(action.name, account)
            foreground = self._foreground(action.name, enabled)
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(QColor("#27272A" if enabled else "#202023"))
            painter.setPen(QPen(QColor("#3F3F46"), 1))
            painter.drawRoundedRect(rect.adjusted(0, 0, -1, -1), 5, 5)
            workspace_action_icon(action.name, foreground).paint(
                painter, rect.adjusted(5, 5, -5, -5), Qt.AlignCenter
            )
            painter.restore()

    def editorEvent(self, event, model, option, index) -> bool:
        if event.type() != QEvent.MouseButtonRelease:
            return False
        if not isinstance(event, QMouseEvent) or event.button() != Qt.LeftButton:
            return False
        account = index.data(PhoneAccountsModel.AccountRole)
        if account is None:
            return False
        for action, rect in self._action_rects(option.rect):
            if rect.contains(event.position().toPoint()):
                if self._is_enabled(action.name, account):
                    self.action_requested.emit(action.name, account)
                return True
        return False

    def helpEvent(self, event, view, option, index) -> bool:
        if not isinstance(event, QHelpEvent):
            return False
        for action, rect in self._action_rects(option.rect):
            if rect.contains(event.pos()):
                QToolTip.showText(event.globalPos(), action.tooltip, view)
                return True
        return False

    @staticmethod
    def _is_enabled(action: str, account) -> bool:
        return action != "analytics"

    @staticmethod
    def _foreground(action: str, enabled: bool) -> str:
        if not enabled:
            return "#52525B"
        if action == "edit":
            return "#F59E0B"
        if action == "archive":
            return "#EF4444"
        return "#3B82F6"

    def visible_actions(self) -> tuple[_AccountAction, ...]:
        if self._archive_visible:
            return (*self.ACTIONS, self.ARCHIVE_ACTION)
        return self.ACTIONS

    def _action_rects(self, cell_rect: QRect):
        actions = self.visible_actions()
        total = len(actions) * self.BUTTON_SIZE + (len(actions) - 1) * self.GAP
        left = cell_rect.left() + max(4, (cell_rect.width() - total) // 2)
        top = cell_rect.top() + (cell_rect.height() - self.BUTTON_SIZE) // 2
        for action in actions:
            rect = QRect(left, top, self.BUTTON_SIZE, self.BUTTON_SIZE)
            yield action, rect
            left = rect.right() + self.GAP + 1
