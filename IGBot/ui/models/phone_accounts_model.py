from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor, QFont

from IGBot.core.device import AssignedAccount

_ROOT_INDEX = QModelIndex()


class PhoneAccountsModel(QAbstractTableModel):
    """Read-only model of real InstaAddict accounts assigned to one phone."""

    HEADERS = (
        "Start Hour",
        "End Hour",
        "Username",
        "Followers",
        "Following",
        "Followed",
        "Unfollowed",
        "Story",
        "Like",
        "Comment",
        "DM",
        "Posted",
        "Status",
        "Actions",
    )
    USERNAME = HEADERS.index("Username")
    STATUS = HEADERS.index("Status")
    ACTIONS = HEADERS.index("Actions")
    AccountRole = Qt.UserRole + 2

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._accounts: list[AssignedAccount] = []
        self._statuses: dict[str, str] = {}

    def rowCount(self, parent=_ROOT_INDEX) -> int:
        return 0 if parent.isValid() else len(self._accounts)

    def columnCount(self, parent=_ROOT_INDEX) -> int:
        return 0 if parent.isValid() else len(self.HEADERS)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        account = self._accounts[index.row()]
        if role == Qt.ToolTipRole and index.column() == self.USERNAME:
            return str(account.config_path)
        if role == Qt.FontRole and index.column() not in (self.USERNAME, self.ACTIONS):
            return QFont("Cascadia Mono", 9)
        if role == Qt.TextAlignmentRole:
            return (
                Qt.AlignLeft | Qt.AlignVCenter
                if index.column() == self.USERNAME
                else Qt.AlignCenter
            )
        if role == Qt.ForegroundRole and index.column() != self.USERNAME:
            return QColor("#8694a4")
        if role == Qt.UserRole:
            return account.username
        if role == Qt.UserRole + 1:
            return account.device_id
        if role == self.AccountRole:
            return account
        if role != Qt.DisplayRole:
            return None
        if index.column() == self.USERNAME:
            return account.username
        if index.column() == self.STATUS:
            return self._statuses.get(str(account.config_path.resolve()), "Idle")
        if index.column() == self.ACTIONS:
            return ""
        return "—"

    def headerData(
        self, section: int, orientation: Qt.Orientation, role=Qt.DisplayRole
    ):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.HEADERS[section]
        if orientation == Qt.Horizontal and role == Qt.TextAlignmentRole:
            return (
                Qt.AlignLeft | Qt.AlignVCenter
                if section == self.USERNAME
                else Qt.AlignCenter
            )
        return super().headerData(section, orientation, role)

    def set_accounts(self, accounts: list[AssignedAccount]) -> None:
        self.beginResetModel()
        self._accounts = list(accounts)
        self.endResetModel()

    def account_at(self, row: int) -> AssignedAccount | None:
        if 0 <= row < len(self._accounts):
            return self._accounts[row]
        return None

    def set_runtime_status(self, username: str, status: str) -> None:
        for row, account in enumerate(self._accounts):
            if account.username == username:
                self._statuses[str(account.config_path.resolve())] = status
                index = self.index(row, self.STATUS)
                self.dataChanged.emit(index, index, [Qt.DisplayRole])
