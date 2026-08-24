from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from IGBot.ui.controllers.device_controller import DeviceController


class DevicesPage(QWidget):
    """Displays Android devices reported by ADB."""

    def __init__(
        self, controller: DeviceController, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("devicesPage")
        self._controller = controller

        self.title = QLabel("Devices", self)
        self.title.setObjectName("pageTitle")
        self.subtitle = QLabel(
            "Android devices connected through ADB and ready for IGBot.", self
        )
        self.subtitle.setObjectName("pageSubtitle")

        self.refresh_button = QPushButton("Refresh devices", self)
        self.refresh_button.setObjectName("primaryButton")
        self.refresh_button.clicked.connect(self._controller.refresh)

        self.device_list = QListWidget(self)
        self.device_list.setObjectName("deviceList")
        self.device_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.device_list.hide()

        self.empty_state = QLabel("No connected Android devices", self)
        self.empty_state.setObjectName("emptyState")
        self.empty_state.setAlignment(Qt.AlignCenter)
        self.empty_state.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.error_banner = QLabel(self)
        self.error_banner.setObjectName("errorBanner")
        self.error_banner.setWordWrap(True)
        self.error_banner.hide()

        self._build_layout()
        self._connect_signals()

    def _build_layout(self) -> None:
        header = QHBoxLayout()
        heading = QVBoxLayout()
        heading.setSpacing(4)
        heading.addWidget(self.title)
        heading.addWidget(self.subtitle)
        header.addLayout(heading)
        header.addStretch()
        header.addWidget(self.refresh_button)

        card = QFrame(self)
        card.setObjectName("contentCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(12)
        card_layout.addWidget(self.error_banner)
        card_layout.addWidget(self.device_list)
        card_layout.addWidget(self.empty_state)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(20)
        layout.addLayout(header)
        layout.addWidget(card, 1)

    def _connect_signals(self) -> None:
        self._controller.refresh_started.connect(self._on_refresh_started)
        self._controller.devices_changed.connect(self._set_devices)
        self._controller.discovery_failed.connect(self._show_error)

    def _on_refresh_started(self) -> None:
        self.refresh_button.setEnabled(False)
        self.refresh_button.setText("Refreshing…")
        self.error_banner.hide()

    def _set_devices(self, devices: list[str]) -> None:
        self._finish_refresh()
        self.device_list.clear()
        for serial in devices:
            item = QListWidgetItem(serial)
            item.setData(Qt.UserRole, serial)
            item.setToolTip(serial)
            self.device_list.addItem(item)

        has_devices = bool(devices)
        self.device_list.setVisible(has_devices)
        self.empty_state.setVisible(not has_devices)

    def _show_error(self, message: str) -> None:
        self._finish_refresh()
        self.device_list.clear()
        self.device_list.hide()
        self.empty_state.hide()
        self.error_banner.setText(message)
        self.error_banner.show()

    def _finish_refresh(self) -> None:
        self.refresh_button.setEnabled(True)
        self.refresh_button.setText("Refresh devices")
