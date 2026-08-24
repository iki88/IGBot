from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QFont

from IGBot.core.device import AssignedAccount

_ROOT_INDEX = QModelIndex()


class PhoneAccountsModel(QAbstractTableModel):
    """Read-only model of real InstaAddict accounts assigned to one phone."""

    HEADERS = ("Instagram Account", "Application ID", "Configuration")

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._accounts: list[AssignedAccount] = []

    def rowCount(self, parent=_ROOT_INDEX) -> int:
        return 0 if parent.isValid() else len(self._accounts)

    def columnCount(self, parent=_ROOT_INDEX) -> int:
        return 0 if parent.isValid() else len(self.HEADERS)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        account = self._accounts[index.row()]
        if role == Qt.ToolTipRole and index.column() == 2:
            return str(account.config_path)
        if role == Qt.FontRole and index.column() in (1, 2):
            return QFont("Cascadia Mono", 9)
        if role != Qt.DisplayRole:
            return None
        return (
            account.username,
            account.app_id,
            f"{account.config_path.parent.name}/{account.config_path.name}",
        )[index.column()]

    def headerData(
        self, section: int, orientation: Qt.Orientation, role=Qt.DisplayRole
    ):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.HEADERS[section]
        return super().headerData(section, orientation, role)

    def set_accounts(self, accounts: list[AssignedAccount]) -> None:
        self.beginResetModel()
        self._accounts = list(accounts)
        self.endResetModel()
