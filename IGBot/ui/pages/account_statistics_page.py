import sqlite3

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHeaderView,
    QLabel,
    QPushButton,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from IGBot.core.device import AssignedAccount
from IGBot.runtime.analytics import AnalyticsDatabase
from IGBot.ui.widgets.empty_state import EmptyState
from IGBot.ui.widgets.page_header import PageHeader
from IGBot.ui.widgets.trend_indicator_delegate import TrendIndicatorDelegate


class AccountStatisticsPage(QWidget):
    """Full-workspace, read-only historical account statistics."""

    back_requested = Signal()
    HEADERS = (
        "Date",
        "Username",
        "Posts",
        "Followers",
        "Following",
        "Followed",
        "Unfollowed",
        "Liked",
        "Commented",
        "Story",
        "DM",
        "Posted",
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("accountStatisticsPage")
        self.account: AssignedAccount | None = None

        self.back_button = QPushButton("Back", self)
        self.back_button.setObjectName("secondaryButton")
        self.back_button.setIcon(self.style().standardIcon(QStyle.SP_ArrowBack))
        self.back_button.clicked.connect(self.back_requested)
        self.range_label = QLabel("Statistics range:", self)
        self.range_label.setObjectName("summaryText")
        self.window = QComboBox(self)
        self.window.addItem("Last 30 Days", 30)
        self.window.addItem("Last 90 Days", 90)
        self.window.addItem("Last 180 Days", 180)
        self.window.addItem("All", None)
        self.window.currentIndexChanged.connect(self._load)

        self.page_header = PageHeader(
            "Statistics",
            "Historical account analytics.",
            self,
        )
        self.page_header.add_action_widget(self.range_label)
        self.page_header.add_action_widget(self.window)
        self.page_header.add_action_widget(self.back_button)

        self.table = QTableWidget(self)
        self.table.setObjectName("statisticsTable")
        self.table.setColumnCount(len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setSortingEnabled(True)
        self.trend_delegate = TrendIndicatorDelegate(self.table)
        self.table.setItemDelegate(self.trend_delegate)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(34)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)

        self.empty = EmptyState(
            self.style().standardIcon(QStyle.SP_FileDialogInfoView),
            "No analytics available yet",
            "Analytics will appear after the first successful account session.",
            self,
        )

        card = QFrame(self)
        card.setObjectName("contentCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(11, 10, 11, 11)
        card_layout.setSpacing(8)
        card_layout.addSpacing(12)
        card_layout.addWidget(self.table, 1)
        card_layout.addWidget(self.empty, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 15, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(self.page_header)
        layout.addWidget(card, 1)

    def set_account(self, account: AssignedAccount) -> None:
        self.account = account
        self.page_header.title.setText(f"Statistics — {account.username}")
        self._load()

    def _load(self) -> None:
        history = ()
        if self.account is not None:
            path = self.account.config_path.parent / "analytics.db"
            if path.is_file():
                try:
                    with AnalyticsDatabase(self.account.config_path.parent) as database:
                        history = database.history(self.window.currentData())
                except (OSError, sqlite3.Error):
                    history = ()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(history))
        for row, summary in enumerate(history):
            for column, value in enumerate(
                (
                    summary.date,
                    summary.username,
                    summary.posts,
                    summary.followers,
                    summary.following,
                    summary.followed,
                    summary.unfollowed,
                    summary.liked,
                    summary.commented,
                    summary.story,
                    summary.dm,
                    summary.posted,
                )
            ):
                item = QTableWidgetItem(str(value))
                if column >= 2:
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, column, item)
        self.table.setSortingEnabled(True)
        self.empty.setVisible(not history)
        self.table.setVisible(bool(history))
