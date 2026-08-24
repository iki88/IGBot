from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget


class NavigationSidebar(QWidget):
    """Primary application navigation."""

    page_selected = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("navigationSidebar")
        self.setMinimumWidth(190)
        self.setMaximumWidth(280)

        brand = QLabel("IGBot", self)
        brand.setObjectName("brandLabel")

        self.navigation = QListWidget(self)
        self.navigation.setObjectName("navigationList")
        self.navigation.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.navigation.addItem(QListWidgetItem("Devices"))
        self.navigation.setCurrentRow(0)
        self.navigation.currentRowChanged.connect(self.page_selected)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 22, 16, 16)
        layout.setSpacing(22)
        layout.addWidget(brand)
        layout.addWidget(self.navigation, 1)
