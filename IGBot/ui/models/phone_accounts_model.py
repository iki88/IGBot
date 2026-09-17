import re

import yaml
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
    START_HOUR = HEADERS.index("Start Hour")
    END_HOUR = HEADERS.index("End Hour")
    USERNAME = HEADERS.index("Username")
    STATUS = HEADERS.index("Status")
    ACTIONS = HEADERS.index("Actions")
    AccountRole = Qt.UserRole + 2

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._accounts: list[AssignedAccount] = []
        self._statuses: dict[str, str] = {}
        self._schedules: dict[str, tuple[str, str]] = {}

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
        if index.column() in {self.START_HOUR, self.END_HOUR}:
            schedule = self._schedules.get(
                str(account.config_path.resolve()), ("—", "—")
            )
            return schedule[index.column()]
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
        self._schedules = {
            str(account.config_path.resolve()): self._load_schedule(account)
            for account in self._accounts
        }
        self.endResetModel()

    @classmethod
    def _load_schedule(cls, account: AssignedAccount) -> tuple[str, str]:
        try:
            configuration = yaml.safe_load(account.config_path.read_bytes())
        except (OSError, yaml.YAMLError):
            return "—", "—"
        if not isinstance(configuration, dict):
            return "—", "—"
        windows = configuration.get("working-hours") or []
        if isinstance(windows, str):
            windows = [windows]
        if not isinstance(windows, list):
            return "—", "—"
        starts: list[str] = []
        ends: list[str] = []
        for window in windows:
            parts = str(window).split("-", 1)
            if len(parts) != 2:
                continue
            start = cls._display_time(parts[0])
            end = cls._display_time(parts[1])
            if start is None or end is None:
                continue
            starts.append(start)
            ends.append(end)
        if not starts:
            return "—", "—"
        return ",".join(starts), ",".join(ends)

    @staticmethod
    def _display_time(value: str) -> str | None:
        match = re.fullmatch(r"\s*(\d{1,2})(?:[.:](\d{1,2}))?\s*", value)
        if match is None:
            return None
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        if hour > 24 or minute > 59 or (hour == 24 and minute != 0):
            return None
        return f"{hour}:{minute:02d}"

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
