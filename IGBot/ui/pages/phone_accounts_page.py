from pathlib import Path

from PySide6.QtCore import QSortFilterProxyModel, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
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
from IGBot.ui.widgets.text_input_dialog import TextInputDialog


class PhoneAccountsPage(QWidget):
    """Workspace for real InstaAddict accounts assigned to one phone."""

    back_requested = Signal()
    rename_requested = Signal(str, str)
    folder_requested = Signal(str)
    delete_requested = Signal(str)
    transfer_requested = Signal(str, str)
    archive_requested = Signal(str, str)
    restore_requested = Signal(str)
    account_delete_requested = Signal(str)
    account_folder_requested = Signal(str)

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
        self._serial = ""
        self.options_button = QPushButton("Device Options", self)
        self.options_button.setObjectName("secondaryButton")
        self.options_menu = QMenu(self.options_button)
        self.options_menu.addAction("Rename Device", self._rename_device)
        self.options_menu.addAction("Open Device Folder", self._open_device_folder)
        self.options_menu.addSeparator()
        self.options_menu.addAction("Delete Device", self._delete_device)
        self.options_button.setMenu(self.options_menu)
        self.page_header.add_action_widget(self.options_button)

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
        self.proxy_model = QSortFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy_model.setFilterKeyColumn(
            PhoneAccountsModel.HEADERS.index("Instagram Account")
        )
        self.search = QLineEdit(self)
        self.search.setObjectName("deviceSearch")
        self.search.setPlaceholderText("Search by Instagram username")
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(350)
        self.search.textChanged.connect(self.proxy_model.setFilterFixedString)
        self.search.hide()
        self.table = QTableView(self)
        self.table.setObjectName("accountsTable")
        self.table.setModel(self.proxy_model)
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
        self.table.setColumnWidth(PhoneAccountsModel.HEADERS.index("Actions"), 140)
        self.table.clicked.connect(self._handle_account_action)

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
        card_layout.addWidget(self.search)
        card_layout.addWidget(self.table, 1)
        card_layout.addWidget(self.empty_state, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(12)
        layout.addWidget(self.page_header)
        layout.addWidget(self.device_context)
        layout.addWidget(card, 1)

    def set_phone(self, device: DeviceRecord, accounts: list[AssignedAccount]) -> None:
        self._serial = device.serial
        self.search.clear()
        self.search.hide()
        self.options_button.show()
        self.page_header.title.setText("Phone Accounts")
        self.page_header.subtitle.setText(
            "Accounts assigned through InstaAddict configuration."
        )
        self.connection_dot.show()
        self.empty_state.set_content(
            "No accounts assigned", "No Instagram accounts assigned to this phone."
        )
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

    def set_archived(self, accounts: list[AssignedAccount]) -> None:
        self._serial = ""
        self.search.clear()
        self.search.show()
        self.options_button.hide()
        self.page_header.title.setText("Archived Accounts")
        self.page_header.subtitle.setText("Accounts stored in the Archived container.")
        self.phone_name.setText("Archived")
        self.phone_serial.clear()
        self.connection_dot.hide()
        count = len(accounts)
        noun = "account" if count == 1 else "accounts"
        self.account_summary.setText(f"{count} {noun}")
        self.model.set_accounts(accounts)
        self.table.setVisible(bool(accounts))
        self.empty_state.set_content(
            "No archived accounts", "No Instagram accounts have been archived."
        )
        self.empty_state.setVisible(not accounts)

    def _rename_device(self) -> None:
        phone_name, accepted = TextInputDialog.get_text(
            "Rename Device", "CUSTOM PHONE NAME", self.phone_name.text(), self
        )
        if accepted and self._serial:
            self.rename_requested.emit(self._serial, phone_name)

    def _open_device_folder(self) -> None:
        if self._serial:
            self.folder_requested.emit(self._serial)

    def _delete_device(self) -> None:
        if self._serial:
            self.delete_requested.emit(self._serial)

    def _handle_account_action(self, index) -> None:
        if index.column() != PhoneAccountsModel.HEADERS.index("Actions"):
            return

        menu = self._build_account_options(index)
        position = self.table.visualRect(index).bottomLeft()
        menu.exec(self.table.viewport().mapToGlobal(position))

    def _build_account_options(self, index) -> QMenu:
        username = index.data(Qt.UserRole)
        configuration_column = PhoneAccountsModel.HEADERS.index("Configuration")
        config_path = index.siblingAtColumn(configuration_column).data(Qt.ToolTipRole)
        menu = QMenu(self.table)

        if self._serial:
            menu.addAction(
                "Transfer Account",
                lambda: self.transfer_requested.emit(username, self._serial),
            )
            menu.addAction(
                "Archive Account",
                lambda: self.archive_requested.emit(username, self._serial),
            )
        else:
            menu.addAction(
                "Restore Account", lambda: self.restore_requested.emit(username)
            )

        menu.addAction(
            "Open Account Folder",
            lambda: self.account_folder_requested.emit(str(Path(config_path).parent)),
        )

        if not self._serial:
            menu.addAction(
                "Delete Account", lambda: self.account_delete_requested.emit(username)
            )

        return menu
