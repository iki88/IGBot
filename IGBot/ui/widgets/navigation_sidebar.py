from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from IGBot.ui.icons import archive_icon, phone_icon
from IGBot.ui.version import APPLICATION_VERSION


class NavigationSidebar(QWidget):
    """Primary application navigation."""

    page_selected = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("navigationSidebar")
        self.setMinimumWidth(172)
        self.setMaximumWidth(230)

        brand = QLabel("IGBot", self)
        brand.setObjectName("brandLabel")
        product = QLabel(f"Version {APPLICATION_VERSION}", self)
        product.setObjectName("brandCaption")

        workspace = QLabel("WORKSPACE", self)
        workspace.setObjectName("navigationSection")

        self.navigation = QListWidget(self)
        self.navigation.setObjectName("navigationList")
        self.navigation.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        devices = QListWidgetItem(phone_icon(), "Devices")
        self.navigation.addItem(devices)
        accounts = QListWidgetItem(
            self.style().standardIcon(QStyle.SP_FileDialogDetailedView), "Accounts"
        )
        self.navigation.addItem(accounts)
        self.navigation.addItem(QListWidgetItem(archive_icon(), "Archived"))
        self.navigation.addItem(
            QListWidgetItem(
                self.style().standardIcon(QStyle.SP_FileDialogContentsView),
                "Activity Log",
            )
        )
        self.navigation.setMaximumHeight(168)
        self.navigation.setCurrentRow(0)
        self.navigation.itemClicked.connect(self._select_workspace)

        settings = QLabel("SETTINGS", self)
        settings.setObjectName("navigationSection")
        self.settings_navigation = QListWidget(self)
        self.settings_navigation.setObjectName("navigationList")
        self.settings_navigation.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.settings_navigation.setMaximumHeight(44)
        self.settings_navigation.addItem(
            QListWidgetItem(
                self.style().standardIcon(QStyle.SP_FileDialogInfoView),
                "Global Settings",
            )
        )
        self.settings_navigation.itemClicked.connect(self._select_settings)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 18, 12, 12)
        layout.setSpacing(3)
        layout.addWidget(brand)
        layout.addWidget(product)
        layout.addSpacing(22)
        layout.addWidget(workspace)
        layout.addSpacing(6)
        layout.addWidget(self.navigation)
        layout.addSpacing(18)
        layout.addWidget(settings)
        layout.addSpacing(6)
        layout.addWidget(self.settings_navigation)
        layout.addStretch(1)

    def _select_workspace(self, item: QListWidgetItem) -> None:
        self.settings_navigation.clearSelection()
        self.page_selected.emit(self.navigation.row(item))

    def _select_settings(self, item: QListWidgetItem) -> None:
        self.navigation.clearSelection()
        self.page_selected.emit(4 + self.settings_navigation.row(item))
