from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from IGBot.core.device import DeviceRecord


class TransferAccountDialog(QDialog):
    """Choose a managed destination without performing an account transfer."""

    def __init__(
        self,
        username: str,
        devices: list[DeviceRecord],
        source_serial: str,
        parent: QWidget | None = None,
        action_text: str = "Transfer",
    ) -> None:
        super().__init__(parent)
        self.setObjectName("transferAccountDialog")
        self.setWindowTitle(f"{action_text} Account")
        self.setMinimumSize(500, 390)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self._devices = [device for device in devices if device.serial != source_serial]

        title = QLabel(f"{action_text} Account", self)
        title.setObjectName("dialogTitle")
        account = QLabel(username, self)
        account.setObjectName("dialogSubtitle")
        destination = QLabel("DESTINATION DEVICE", self)
        destination.setObjectName("dialogFieldLabel")
        self.search = QLineEdit(self)
        self.search.setObjectName("dialogInput")
        self.search.setPlaceholderText("Search by phone name or Device ID")
        self.matches = QListWidget(self)
        self.matches.setObjectName("dialogDeviceList")
        self.matches.setMinimumHeight(155)
        self.transfer_button = QPushButton(action_text, self)
        self.transfer_button.setObjectName("primaryButton")
        self.transfer_button.setEnabled(False)
        self.transfer_button.clicked.connect(self.accept)
        cancel = QPushButton("Cancel", self)
        cancel.setObjectName("secondaryButton")
        cancel.clicked.connect(self.reject)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 10, 0, 0)
        actions.addStretch()
        actions.addWidget(cancel)
        actions.addWidget(self.transfer_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 22)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(account)
        layout.addSpacing(7)
        layout.addWidget(destination)
        layout.addWidget(self.search)
        layout.addWidget(self.matches, 1)
        layout.addLayout(actions)

        self.search.textChanged.connect(self._filter_devices)
        self.matches.currentItemChanged.connect(
            lambda current, _: self.transfer_button.setEnabled(current is not None)
        )
        self._filter_devices("")

    @property
    def destination_serial(self) -> str:
        item = self.matches.currentItem()
        return str(item.data(Qt.UserRole)) if item else ""

    def _filter_devices(self, query: str) -> None:
        normalized = query.strip().casefold()
        self.matches.clear()
        for device in self._devices:
            if normalized not in device.serial.casefold() and normalized not in (
                device.phone_name.casefold()
            ):
                continue
            name = device.phone_name or "Unnamed phone"
            item = QListWidgetItem(f"{name}  ·  {device.serial}")
            item.setData(Qt.UserRole, device.serial)
            self.matches.addItem(item)
