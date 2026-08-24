from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from IGBot.core.device import AssignedAccount, DeviceRecord
from IGBot.ui.models.phone_accounts_model import PhoneAccountsModel


class PhoneAccountsPage(QWidget):
    """Workspace for real InstaAddict accounts assigned to one phone."""

    back_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("phoneAccountsPage")

        self.back_button = QPushButton("Back to devices", self)
        self.back_button.setObjectName("secondaryButton")
        self.back_button.clicked.connect(self.back_requested)

        self.title = QLabel("Phone Accounts", self)
        self.title.setObjectName("pageTitle")
        self.phone_details = QLabel(self)
        self.phone_details.setObjectName("pageSubtitle")

        self.model = PhoneAccountsModel(self)
        self.table = QTableView(self)
        self.table.setObjectName("accountsTable")
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSortingEnabled(False)
        self.table.setShowGrid(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(44)
        self.table.horizontalHeader().setSectionsClickable(False)
        self.table.horizontalHeader().setSectionResizeMode(
            PhoneAccountsModel.HEADERS.index("Instagram Account"), QHeaderView.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            PhoneAccountsModel.HEADERS.index("Configuration"), QHeaderView.Stretch
        )

        self.empty_state = QLabel("No Instagram accounts assigned to this phone.", self)
        self.empty_state.setObjectName("emptyState")
        self.empty_state.setAlignment(Qt.AlignCenter)

        self._build_layout()

    def _build_layout(self) -> None:
        heading = QVBoxLayout()
        heading.setSpacing(4)
        heading.addWidget(self.title)
        heading.addWidget(self.phone_details)

        header = QHBoxLayout()
        header.addWidget(self.back_button)
        header.addSpacing(12)
        header.addLayout(heading)
        header.addStretch()

        card = QFrame(self)
        card.setObjectName("contentCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.addWidget(self.table, 1)
        card_layout.addWidget(self.empty_state, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(20)
        layout.addLayout(header)
        layout.addWidget(card, 1)

    def set_phone(self, device: DeviceRecord, accounts: list[AssignedAccount]) -> None:
        name = f"{device.phone_name} · " if device.phone_name else ""
        connection = "Connected" if device.connected else "Offline"
        self.phone_details.setText(f"{name}{device.serial} · {connection}")
        self.model.set_accounts(accounts)
        has_accounts = bool(accounts)
        self.table.setVisible(has_accounts)
        self.empty_state.setVisible(not has_accounts)
