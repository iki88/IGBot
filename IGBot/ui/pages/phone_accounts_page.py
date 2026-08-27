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
from IGBot.services.archive_service import ARCHIVED_ACCOUNTS
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
    apply_template_requested = Signal(object)
    account_open_requested = Signal(object)
    active_account_changed = Signal(object)

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
        self.proxy_model.setFilterKeyColumn(PhoneAccountsModel.USERNAME)
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
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self._configure_columns()
        self.table.doubleClicked.connect(self._open_account)
        self.table.selectionModel().selectionChanged.connect(self._selection_changed)

        self.empty_state = EmptyState(
            self.style().standardIcon(QStyle.SP_FileDialogListView),
            "No accounts assigned",
            "No Instagram accounts assigned to this phone.",
            self,
        )

        self._build_layout()

    def _configure_columns(self) -> None:
        header = self.table.horizontalHeader()
        header.setSectionsClickable(True)
        header.setMinimumSectionSize(55)
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionResizeMode(PhoneAccountsModel.USERNAME, QHeaderView.Stretch)
        widths = {
            "Start Hour": 84,
            "End Hour": 78,
            "Followers": 82,
            "Following": 84,
            "Followed": 80,
            "Unfollowed": 90,
            "Story": 65,
            "Like": 60,
            "Comment": 82,
            "DM": 58,
            "Posted": 72,
            "Status": 96,
        }
        for column, title in enumerate(PhoneAccountsModel.HEADERS):
            if column != PhoneAccountsModel.USERNAME:
                self.table.setColumnWidth(column, widths[title])

    def _build_device_context(self) -> QFrame:
        details = QVBoxLayout()
        details.setContentsMargins(0, 0, 0, 0)
        details.setSpacing(1)
        details.addWidget(self.phone_name)
        details.addWidget(self.phone_serial)

        layout = QHBoxLayout()
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)
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
        card_layout.setContentsMargins(11, 10, 11, 11)
        card_layout.setSpacing(8)
        card_layout.addWidget(self.search)
        card_layout.addWidget(self.table, 1)
        card_layout.addWidget(self.empty_state, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 15, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(self.page_header)
        layout.addWidget(self.device_context)
        layout.addWidget(card, 1)

    def set_phone(self, device: DeviceRecord, accounts: list[AssignedAccount]) -> None:
        selected = self.selected_account()
        selected_path = (
            selected.config_path.resolve()
            if selected is not None and self._serial == device.serial
            else None
        )
        self._serial = device.serial
        self.device_context.show()
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
        if selected_path is not None:
            for row, account in enumerate(accounts):
                if account.config_path.resolve() == selected_path:
                    source_index = self.model.index(row, 0)
                    self.table.selectRow(
                        self.proxy_model.mapFromSource(source_index).row()
                    )
                    break
        has_accounts = bool(accounts)
        self.table.setVisible(has_accounts)
        self.empty_state.setVisible(not has_accounts)

    def set_archived(self, accounts: list[AssignedAccount]) -> None:
        self._serial = ""
        self.device_context.show()
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

    def set_all_accounts(self, accounts: list[AssignedAccount]) -> None:
        self._serial = ""
        self.search.clear()
        self.search.show()
        self.options_button.hide()
        self.device_context.hide()
        self.page_header.title.setText("Accounts")
        self.page_header.subtitle.setText("Accounts assigned across managed phones.")
        self.model.set_accounts(accounts)
        self.table.setVisible(bool(accounts))
        self.empty_state.set_content(
            "No active accounts",
            "No Instagram accounts are assigned to managed phones.",
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

    def _open_account(self, index) -> None:
        source_index = self.proxy_model.mapToSource(index)
        account = self.model.account_at(source_index.row())
        if account is not None:
            self.account_open_requested.emit(account)

    def selected_account(self) -> AssignedAccount | None:
        rows = self.table.selectionModel().selectedRows()
        if len(rows) != 1:
            return None
        return self.model.account_at(self.proxy_model.mapToSource(rows[0]).row())

    def _selection_changed(self) -> None:
        self.active_account_changed.emit(self.selected_account())

    def set_runtime_status(self, username: str, status: str) -> None:
        self.model.set_runtime_status(username, status)

    def build_account_options(self, account: AssignedAccount) -> QMenu:
        username = account.username
        config_path = account.config_path
        menu = QMenu(self.table)

        archived = account.device_id == ARCHIVED_ACCOUNTS
        if not archived:
            menu.addAction(
                "Transfer Account",
                lambda: self.transfer_requested.emit(username, account.device_id),
            )
            menu.addAction(
                "Archive Account",
                lambda: self.archive_requested.emit(username, account.device_id),
            )
            menu.addAction(
                "Apply Template...",
                lambda: self.apply_template_requested.emit(account),
            )
        else:
            menu.addAction(
                "Restore Account", lambda: self.restore_requested.emit(username)
            )

        menu.addAction(
            "Open Account Folder",
            lambda: self.account_folder_requested.emit(str(Path(config_path).parent)),
        )

        if archived:
            menu.addAction(
                "Delete Account", lambda: self.account_delete_requested.emit(username)
            )

        return menu
