from PySide6.QtCore import QAbstractTableModel, QModelIndex, QRect, QSize, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from IGBot.notifications import Notification, NotificationService
from IGBot.ui.icons import workspace_action_icon
from IGBot.ui.widgets.empty_state import EmptyState
from IGBot.ui.widgets.page_header import PageHeader

_INVALID_INDEX = QModelIndex()


class NotificationsTableModel(QAbstractTableModel):
    """Read-only projection of persisted notifications."""

    HEADERS = ("Severity", "Username", "Tag", "Device", "Type", "Since", "Actions")

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.notifications: tuple[Notification, ...] = ()

    def set_notifications(self, notifications: tuple[Notification, ...]) -> None:
        self.beginResetModel()
        self.notifications = notifications
        self.endResetModel()

    def rowCount(self, parent=_INVALID_INDEX) -> int:
        return len(self.notifications) if not parent.isValid() else 0

    def columnCount(self, parent=_INVALID_INDEX) -> int:
        return len(self.HEADERS)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.notifications):
            return None
        notification = self.notifications[index.row()]
        if role == Qt.UserRole:
            return notification
        if role != Qt.DisplayRole:
            return None
        values = (
            notification.severity.value.title(),
            notification.username,
            notification.tag,
            notification.device,
            notification.type.value.replace("_", " ").title(),
            notification.detected_at,
            "",
        )
        return values[index.column()]

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if (
            role == Qt.DisplayRole
            and orientation == Qt.Horizontal
            and 0 <= section < len(self.HEADERS)
        ):
            return self.HEADERS[section]
        return None


class NotificationActionsDelegate(QStyledItemDelegate):
    """Reserve the future Open Phone and Account Settings row actions."""

    ACTIONS = (("view", "View Phone"), ("manage", "Open Phone Accounts"))

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        super().paint(painter, option, index)
        foreground = option.palette.text().color().name()
        for offset, (action, _tooltip) in enumerate(self.ACTIONS):
            rectangle = QRect(
                option.rect.left() + 12 + offset * 32,
                option.rect.center().y() - 9,
                18,
                18,
            )
            workspace_action_icon(action, foreground).paint(painter, rectangle)

    def sizeHint(self, option, index) -> QSize:
        return QSize(84, 36)


class NotificationSummaryCard(QFrame):
    """Clickable summary surface that applies one common notification filter."""

    clicked = Signal()

    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("notificationSummaryCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAttribute(Qt.WA_Hover, True)
        self.setProperty("selected", False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 13, 16, 13)
        layout.setSpacing(3)
        self.title = QLabel(label, self)
        self.title.setObjectName("notificationSummaryLabel")
        self.value = QLabel("0", self)
        self.value.setObjectName("notificationSummaryValue")
        layout.addWidget(self.title)
        layout.addWidget(self.value)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in {Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space}:
            self.clicked.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class NotificationsTableView(QTableView):
    """Table whose zero-row message occupies the body while headers stay visible."""

    def set_empty_state(self, empty_state: QWidget) -> None:
        self.empty_state = empty_state
        self.empty_state.setParent(self.viewport())
        self.empty_state.show()
        self.empty_state.raise_()
        self._position_empty_state()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_empty_state()

    def _position_empty_state(self) -> None:
        empty_state = getattr(self, "empty_state", None)
        if empty_state is not None:
            empty_state.setGeometry(self.viewport().rect())


class NotificationsPage(QWidget):
    """Workspace shell for current and historical operator notifications."""

    TYPE_OPTIONS = (
        "All",
        "Human Captcha",
        "Logged Out",
        "Username Changed",
        "2FA Required",
        "Account Disabled",
        "Try Again Later",
        "Zero Interactions",
    )

    def __init__(
        self,
        parent: QWidget | None = None,
        notification_service: NotificationService | None = None,
    ) -> None:
        super().__init__(parent)
        self.notification_service = notification_service
        self.setObjectName("notificationsPage")
        self.page_header = PageHeader(
            "Notifications",
            "Accounts requiring operator attention.",
            self,
        )

        summaries = QHBoxLayout()
        summaries.setContentsMargins(0, 0, 0, 0)
        summaries.setSpacing(12)
        self.critical_card = self._summary_card("Critical", summaries)
        self.warning_card = self._summary_card("Warning", summaries)
        self.total_active_card = self._summary_card("Total Active", summaries)
        self.critical_value = self.critical_card.value
        self.warning_value = self.warning_card.value
        self.total_active_value = self.total_active_card.value

        self.severity = self._filter(("All", "Critical", "Warning"))
        self.notification_type = self._filter(self.TYPE_OPTIONS)
        self.status = self._filter(("Active", "Resolved", "All"))
        filters = QHBoxLayout()
        filters.setContentsMargins(0, 0, 0, 0)
        filters.setSpacing(10)
        for label, control in (
            ("Severity", self.severity),
            ("Type", self.notification_type),
            ("Status", self.status),
        ):
            field = QVBoxLayout()
            field.setContentsMargins(0, 0, 0, 0)
            field.setSpacing(4)
            caption = QLabel(label, self)
            caption.setObjectName("filterLabel")
            field.addWidget(caption)
            field.addWidget(control)
            filters.addLayout(field)
        filters.addStretch()

        self.model = NotificationsTableModel(self)
        self.table = NotificationsTableView(self)
        self.table.setObjectName("notificationsTable")
        self.table.setModel(self.model)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(36)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(6, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 92)
        self.table.setColumnWidth(2, 120)
        self.table.setColumnWidth(3, 130)
        self.table.setColumnWidth(4, 160)
        self.table.setColumnWidth(5, 110)
        self.table.setColumnWidth(6, 92)
        self.actions_delegate = NotificationActionsDelegate(self.table)
        self.table.setItemDelegateForColumn(6, self.actions_delegate)

        self.empty_state = EmptyState(
            workspace_action_icon("view"),
            "No active notifications.",
            "Accounts requiring operator attention will appear here automatically.",
            self.table,
        )
        self.table.set_empty_state(self.empty_state)

        self.critical_card.clicked.connect(
            lambda: self.severity.setCurrentText("Critical")
        )
        self.critical_card.clicked.connect(
            lambda: self._select_summary_card(self.critical_card)
        )
        self.warning_card.clicked.connect(
            lambda: self.severity.setCurrentText("Warning")
        )
        self.warning_card.clicked.connect(
            lambda: self._select_summary_card(self.warning_card)
        )
        self.total_active_card.clicked.connect(self._show_all_active)
        self.total_active_card.clicked.connect(
            lambda: self._select_summary_card(self.total_active_card)
        )
        self.severity.currentTextChanged.connect(self.refresh)
        self.notification_type.currentTextChanged.connect(self.refresh)
        self.status.currentTextChanged.connect(self.refresh)
        self._select_summary_card(self.total_active_card)

        content = QFrame(self)
        content.setObjectName("contentCard")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(14, 14, 14, 14)
        content_layout.setSpacing(12)
        content_layout.addLayout(filters)
        content_layout.addWidget(self.table, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(14)
        layout.addWidget(self.page_header)
        layout.addLayout(summaries)
        layout.addWidget(content, 1)
        self.refresh()

    def refresh(self, *_args) -> None:
        if self.notification_service is None:
            notifications: tuple[Notification, ...] = ()
        else:
            active = self.notification_service.active()
            resolved = self.notification_service.resolved()
            self.critical_value.setText(
                str(sum(item.severity.value == "CRITICAL" for item in active))
            )
            self.warning_value.setText(
                str(sum(item.severity.value == "WARNING" for item in active))
            )
            self.total_active_value.setText(str(len(active)))
            status = self.status.currentText()
            notifications = (
                active
                if status == "Active"
                else resolved
                if status == "Resolved"
                else active + resolved
            )

        severity = self.severity.currentText().upper()
        if severity != "ALL":
            notifications = tuple(
                item for item in notifications if item.severity.value == severity
            )
        selected_type = self.notification_type.currentText()
        if selected_type != "All":
            type_value = selected_type.upper().replace(" ", "_")
            notifications = tuple(
                item for item in notifications if item.type.value == type_value
            )
        self.model.set_notifications(notifications)
        self.empty_state.setVisible(not notifications)

    def _summary_card(self, label: str, layout: QHBoxLayout) -> NotificationSummaryCard:
        card = NotificationSummaryCard(label, self)
        layout.addWidget(card, 1)
        return card

    def _filter(self, options: tuple[str, ...]) -> QComboBox:
        control = QComboBox(self)
        control.addItems(options)
        control.setMinimumWidth(170)
        return control

    def _show_all_active(self) -> None:
        self.severity.setCurrentText("All")
        self.status.setCurrentText("Active")

    def _select_summary_card(self, selected: NotificationSummaryCard) -> None:
        for card in (
            self.critical_card,
            self.warning_card,
            self.total_active_card,
        ):
            card.setProperty("selected", card is selected)
            card.style().unpolish(card)
            card.style().polish(card)
            card.update()
