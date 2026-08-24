from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QStyle,
    QVBoxLayout,
    QWidget,
)


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
        devices = QListWidgetItem(
            self.style().standardIcon(QStyle.SP_ComputerIcon), "Devices"
        )
        self.navigation.addItem(devices)
        self.navigation.setCurrentRow(0)
        self.navigation.currentRowChanged.connect(self.page_selected)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 18, 12, 12)
        layout.setSpacing(3)
        layout.addWidget(brand)
        layout.addWidget(product)
        layout.addSpacing(22)
        layout.addWidget(workspace)
        layout.addSpacing(6)
        layout.addWidget(self.navigation, 1)
