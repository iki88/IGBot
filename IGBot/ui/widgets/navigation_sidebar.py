from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from IGBot.ui.icons import phone_icon


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
        product = QLabel("OPERATIONS CONSOLE", self)
        product.setObjectName("brandCaption")

        workspace = QLabel("WORKSPACE", self)
        workspace.setObjectName("navigationSection")

        self.navigation = QListWidget(self)
        self.navigation.setObjectName("navigationList")
        self.navigation.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        devices = QListWidgetItem(phone_icon(), "Devices")
        self.navigation.addItem(devices)
        self.navigation.setCurrentRow(0)
        self.navigation.itemClicked.connect(
            lambda item: self.page_selected.emit(self.navigation.row(item))
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 18, 12, 12)
        layout.setSpacing(3)
        layout.addWidget(brand)
        layout.addWidget(product)
        layout.addSpacing(22)
        layout.addWidget(workspace)
        layout.addSpacing(6)
        layout.addWidget(self.navigation, 1)
