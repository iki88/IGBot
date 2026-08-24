from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QStyle,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from IGBot.core.device import AssignedAccount, DeviceRecord
from IGBot.ui.models.phone_accounts_model import PhoneAccountsModel
from IGBot.ui.widgets.empty_state import EmptyState
from IGBot.ui.widgets.page_header import PageHeader


class PhoneAccountsPage(QWidget):
    """Workspace for real InstaAddict accounts assigned to one phone."""

    back_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("phoneAccountsPage")

        self.back_button = QPushButton("Devices", self)
        self.back_button.setObjectName("secondaryButton")
        self.back_button.setIcon(self.style().standardIcon(QStyle.SP_ArrowBack))
        self.back_button.clicked.connect(self.back_requested)

        self.page_header = PageHeader(
            "Phone Accounts",
            "Accounts assigned through InstaAddict configuration.",
            self,
        )
        self.page_header.add_action_widget(self.back_button)

        self.connection_dot = QLabel("●", self)
        self.connection_dot.setObjectName("connectionDot")
        self.phone_name = QLabel(self)
        self.phone_name.setObjectName("deviceContextTitle")
        self.phone_serial = QLabel(self)
        self.phone_serial.setObjectName("deviceContextSerial")
        self.account_summary = QLabel("0 accounts", self)
        self.account_summary.setObjectName("summaryText")

        self.device_context = self._build_device_context()

        self.model = PhoneAccountsModel(self)
        self.table = QTableView(self)
        self.table.setObjectName("accountsTable")
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSortingEnabled(False)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.horizontalHeader().setSectionsClickable(False)
        self.table.horizontalHeader().setSectionResizeMode(
            PhoneAccountsModel.HEADERS.index("Instagram Account"), QHeaderView.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            PhoneAccountsModel.HEADERS.index("Configuration"), QHeaderView.Stretch
        )
        self.table.setColumnWidth(
            PhoneAccountsModel.HEADERS.index("Application ID"), 210
        )

        self.empty_state = EmptyState(
            self.style().standardIcon(QStyle.SP_FileDialogListView),
            "No accounts assigned",
            "No Instagram accounts assigned to this phone.",
            self,
        )

        self._build_layout()

    def _build_device_context(self) -> QFrame:
        details = QVBoxLayout()
        details.setContentsMargins(0, 0, 0, 0)
        details.setSpacing(1)
        details.addWidget(self.phone_name)
        details.addWidget(self.phone_serial)

        layout = QHBoxLayout()
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)
        layout.addWidget(self.connection_dot)
        layout.addLayout(details)
        layout.addStretch()
        layout.addWidget(self.account_summary)

        context = QFrame(self)
        context.setObjectName("deviceContext")
        context.setLayout(layout)
        return context

    def _build_layout(self) -> None:
        card = QFrame(self)
        card.setObjectName("contentCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 14, 14, 14)
        card_layout.addWidget(self.table, 1)
        card_layout.addWidget(self.empty_state, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(12)
        layout.addWidget(self.page_header)
        layout.addWidget(self.device_context)
        layout.addWidget(card, 1)

    def set_phone(self, device: DeviceRecord, accounts: list[AssignedAccount]) -> None:
        self.phone_name.setText(device.phone_name or "Unnamed phone")
        self.phone_serial.setText(device.serial)
        self.connection_dot.setProperty("connected", device.connected)
        self.connection_dot.style().unpolish(self.connection_dot)
        self.connection_dot.style().polish(self.connection_dot)

        count = len(accounts)
        noun = "account" if count == 1 else "accounts"
        self.account_summary.setText(f"{count} {noun}")
        self.model.set_accounts(accounts)
        has_accounts = bool(accounts)
        self.table.setVisible(has_accounts)
        self.empty_state.setVisible(not has_accounts)
