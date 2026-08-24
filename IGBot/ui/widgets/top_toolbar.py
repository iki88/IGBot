from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QLabel, QSizePolicy, QStyle, QToolBar, QWidget


class TopToolbar(QToolBar):
    """Application toolbar containing global actions."""

    refresh_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Application", parent)
        self.setObjectName("topToolbar")
        self.setMovable(False)
        self.setFloatable(False)
        self.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

        self.title = QLabel("Device management", self)
        self.title.setObjectName("toolbarTitle")
        self.addWidget(self.title)

        spacer = QWidget(self)
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.addWidget(spacer)

        self.refresh_action = QAction("Refresh", self)
        self.refresh_action.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        self.refresh_action.setShortcut("F5")
        self.refresh_action.setStatusTip("Refresh connected Android devices")
        self.refresh_action.triggered.connect(self.refresh_requested)
        self.addAction(self.refresh_action)

    def set_context_title(self, title: str) -> None:
        self.title.setText(title)

    def set_refreshing(self, refreshing: bool) -> None:
        self.refresh_action.setEnabled(not refreshing)
        self.refresh_action.setText("Refreshing…" if refreshing else "Refresh")
