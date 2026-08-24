from PySide6.QtCore import Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QLabel, QSizePolicy, QToolBar, QWidget


class TopToolbar(QToolBar):
    """Application toolbar containing global actions."""

    refresh_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Application", parent)
        self.setObjectName("topToolbar")
        self.setMovable(False)
        self.setFloatable(False)

        self.title = QLabel("Device management", self)
        self.title.setObjectName("toolbarTitle")
        self.addWidget(self.title)

        spacer = QWidget(self)
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.addWidget(spacer)

        refresh_action = QAction("Refresh", self)
        refresh_action.setShortcut("F5")
        refresh_action.setStatusTip("Refresh connected Android devices")
        refresh_action.triggered.connect(self.refresh_requested)
        self.addAction(refresh_action)

    def set_context_title(self, title: str) -> None:
        self.title.setText(title)
