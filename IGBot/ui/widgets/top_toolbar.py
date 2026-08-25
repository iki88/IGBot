from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QLabel,
    QMenu,
    QSizePolicy,
    QStyle,
    QToolBar,
    QToolButton,
    QWidget,
)

from IGBot.ui.icons import eye_icon


class TopToolbar(QToolBar):
    """Application toolbar containing global actions."""

    refresh_requested = Signal()
    add_device_requested = Signal()
    add_account_requested = Signal()
    save_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Application", parent)
        self.setObjectName("topToolbar")
        self.setMovable(False)
        self.setFloatable(False)
        self.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.setIconSize(QSize(16, 16))

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

        self.add_device_action = QAction("Add Device", self)
        self.add_device_action.setIcon(
            self.style().standardIcon(QStyle.SP_FileDialogNewFolder)
        )
        self.add_device_action.triggered.connect(self.add_device_requested)
        self.addAction(self.add_device_action)

        self.add_account_action = QAction("Add Account", self)
        self.add_account_action.setIcon(
            self.style().standardIcon(QStyle.SP_FileDialogNewFolder)
        )
        self.add_account_action.triggered.connect(self.add_account_requested)
        self.today_action = QAction("Today", self)
        self.today_action.setIcon(
            self.style().standardIcon(QStyle.SP_FileDialogDetailedView)
        )
        self.start_action = QAction("Start", self)
        self.start_action.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.stop_action = QAction("Stop", self)
        self.stop_action.setIcon(self.style().standardIcon(QStyle.SP_MediaStop))
        self.view_phone_action = QAction("View Phone", self)
        self.view_phone_action.setIcon(eye_icon())
        self.view_phone_action.setToolTip("Phone viewing requires scrcpy integration.")
        self.view_phone_action.setStatusTip(
            "Phone viewing is unavailable until scrcpy is integrated."
        )
        self.save_action = QAction("Save Changes", self)
        self.save_action.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton))
        self.save_action.triggered.connect(self.save_requested)
        self._future_actions = (
            self.add_account_action,
            self.today_action,
            self.start_action,
            self.stop_action,
            self.view_phone_action,
            self.save_action,
        )
        for action in self._future_actions:
            action.setEnabled(False)
            self.addAction(action)

        self.options_button = QToolButton(self)
        self.options_button.setIcon(
            self.style().standardIcon(QStyle.SP_FileDialogDetailedView)
        )
        self.options_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.options_button.setPopupMode(QToolButton.InstantPopup)
        self.options_action = self.addWidget(self.options_button)
        self.set_context("devices")

    def set_context_title(self, title: str) -> None:
        self.title.setText(title)

    def set_refreshing(self, refreshing: bool) -> None:
        self.refresh_action.setEnabled(not refreshing)
        self.refresh_action.setText("Refreshing…" if refreshing else "Refresh")

    def set_context(self, context: str, options_menu: QMenu | None = None) -> None:
        self.refresh_action.setVisible(context == "devices")
        self.add_device_action.setVisible(context == "devices")
        self.add_account_action.setEnabled(context == "phone")
        self.save_action.setEnabled(context == "account")
        for action in self._future_actions:
            action.setVisible(False)

        if context == "phone":
            for action in (
                self.add_account_action,
                self.today_action,
                self.start_action,
                self.stop_action,
                self.view_phone_action,
            ):
                action.setVisible(True)
            self.options_button.setText("Device Options")
        elif context == "account":
            self.save_action.setVisible(True)
            self.options_button.setText("Account Options")

        self.options_button.setMenu(options_menu)
        self.options_action.setVisible(
            context in {"phone", "account"} and options_menu is not None
        )
