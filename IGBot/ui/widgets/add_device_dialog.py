from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class AddDeviceDialog(QDialog):
    """Select one unmanaged connected phone and optionally provide its name."""

    def __init__(self, controller, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("addDeviceDialog")
        self.setWindowTitle("Add Device")
        self.setMinimumSize(520, 460)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        title = QLabel("Add Device", self)
        title.setObjectName("dialogTitle")
        subtitle = QLabel("Select a connected Android phone to manage.", self)
        subtitle.setObjectName("dialogSubtitle")
        devices_label = QLabel("CONNECTED ANDROID DEVICES", self)
        devices_label.setObjectName("dialogFieldLabel")
        self.devices = QListWidget(self)
        self.devices.setObjectName("dialogDeviceList")
        self.devices.setMinimumHeight(180)
        self.message = QLabel("Loading connected Android devices…", self)
        self.message.setObjectName("dialogHint")
        self.message.setWordWrap(True)
        phone_label = QLabel("CUSTOM PHONE NAME", self)
        phone_label.setObjectName("dialogFieldLabel")
        self.phone_name = QLineEdit(self)
        self.phone_name.setObjectName("dialogInput")
        self.phone_name.setPlaceholderText("For example: T1 or Office-02")
        self.add_button = QPushButton("Add Device", self)
        self.add_button.setObjectName("primaryButton")
        self.add_button.setEnabled(False)
        self.add_button.clicked.connect(self.accept)
        cancel = QPushButton("Cancel", self)
        cancel.setObjectName("secondaryButton")
        cancel.clicked.connect(self.reject)
        actions = QHBoxLayout()
        actions.setContentsMargins(0, 12, 0, 0)
        actions.setSpacing(10)
        actions.addStretch()
        actions.addWidget(cancel)
        actions.addWidget(self.add_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 25, 28, 24)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(9)
        layout.addWidget(devices_label)
        layout.addWidget(self.devices)
        layout.addWidget(self.message)
        layout.addSpacing(4)
        layout.addWidget(phone_label)
        layout.addWidget(self.phone_name)
        layout.addLayout(actions)
        self.devices.currentRowChanged.connect(
            lambda row: self.add_button.setEnabled(row >= 0)
        )
        controller.unmanaged_devices_ready.connect(self._set_devices)
        controller.operation_failed.connect(self._show_error)
        controller.load_unmanaged_devices()

    @property
    def serial(self) -> str:
        item = self.devices.currentItem()
        return item.text() if item else ""

    def _set_devices(self, devices: list[str]) -> None:
        self.devices.clear()
        self.devices.addItems(devices)
        if devices:
            self.message.setText("Select the phone you want to add.")
            self.devices.setCurrentRow(0)
        else:
            self.message.setText(
                "No unmanaged Android devices found.\n"
                "All connected devices are already managed."
            )

    def _show_error(self, message: str) -> None:
        self.message.setText(message)
