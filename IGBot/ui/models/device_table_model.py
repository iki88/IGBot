from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtGui import QColor, QFont

from IGBot.core.device import DeviceRecord

_ROOT_INDEX = QModelIndex()


class DeviceTableModel(QAbstractTableModel):
    """Ordered model of phones known to IGBot."""

    CONNECTION, DEVICE_ID, PHONE, ACCOUNTS, STATUS, ACTIONS = range(6)
    HEADERS = ("ADB", "Device ID", "Phone", "Accounts", "Status", "Actions")
    DeviceRole = Qt.UserRole + 1

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._devices: list[DeviceRecord] = []
        self._runtime_statuses: dict[str, str] = {}

    def rowCount(self, parent=_ROOT_INDEX) -> int:
        return 0 if parent.isValid() else len(self._devices)

    def columnCount(self, parent=_ROOT_INDEX) -> int:
        return 0 if parent.isValid() else len(self.HEADERS)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        device = self._devices[index.row()]
        if role == self.DeviceRole:
            return device
        if role == Qt.UserRole:
            return device.serial
        if role == Qt.ForegroundRole and index.column() == self.CONNECTION:
            return QColor("#3fb950" if device.connected else "#f85149")
        if role == Qt.ToolTipRole and index.column() == self.CONNECTION:
            return "Connected through ADB" if device.connected else "Offline"
        if role == Qt.FontRole and index.column() == self.DEVICE_ID:
            return QFont("Cascadia Mono", 9)
        if role == Qt.TextAlignmentRole and index.column() in (
            self.CONNECTION,
            self.ACCOUNTS,
            self.STATUS,
        ):
            return Qt.AlignCenter
        if role != Qt.DisplayRole:
            return None

        values = (
            "●",
            device.serial,
            device.phone_name or "—",
            len(device.accounts),
            self._runtime_statuses.get(device.serial, device.status or "Idle"),
            "",
        )
        return values[index.column()]

    def headerData(
        self, section: int, orientation: Qt.Orientation, role=Qt.DisplayRole
    ):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.HEADERS[section]
        return super().headerData(section, orientation, role)

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def set_devices(self, devices: list[DeviceRecord]) -> None:
        self.beginResetModel()
        self._devices = list(devices)
        self.endResetModel()

    def device_at(self, row: int) -> DeviceRecord | None:
        if 0 <= row < len(self._devices):
            return self._devices[row]
        return None

    def set_runtime_status(self, serial: str, status: str) -> None:
        self._runtime_statuses[serial] = status
        for row, device in enumerate(self._devices):
            if device.serial == serial:
                first = self.index(row, self.STATUS)
                last = self.index(row, self.ACTIONS)
                self.dataChanged.emit(first, last, [Qt.DisplayRole])
                break


class DeviceFilterProxyModel(QSortFilterProxyModel):
    """Filters phones by serial number or user-defined phone name."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._query = ""
        self.setDynamicSortFilter(True)

    def set_query(self, query: str) -> None:
        normalized = query.strip().casefold()
        if normalized == self._query:
            return
        supports_scoped_change = hasattr(self, "beginFilterChange")
        if supports_scoped_change:
            self.beginFilterChange()
        self._query = normalized
        if supports_scoped_change:
            self.endFilterChange(QSortFilterProxyModel.Direction.Rows)
        else:
            self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        if not self._query:
            return True
        model = self.sourceModel()
        device = model.device_at(source_row)
        if device is None:
            return False
        return self._query in device.serial.casefold() or self._query in (
            device.phone_name.casefold()
        )
