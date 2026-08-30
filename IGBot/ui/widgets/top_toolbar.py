from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QLabel,
    QMenu,
    QSizePolicy,
    QStyle,
    QToolBar,
    QToolButton,
    QWidget,
)

from IGBot.ui.icons import eye_icon, workspace_action_icon


class TopToolbar(QToolBar):
    """Application toolbar containing global actions."""

    refresh_requested = Signal()
    add_device_requested = Signal()
    add_account_requested = Signal()
    save_requested = Signal()
    view_phone_requested = Signal()
    start_requested = Signal()
    stop_requested = Signal()
    start_all_requested = Signal()
    stop_all_requested = Signal()

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

        self.start_all_action = QAction("Start All", self)
        self.start_all_action.setIcon(workspace_action_icon("start", "#22C55E"))
        self.start_all_action.setToolTip("Start all phone schedulers")
        self.start_all_action.triggered.connect(self.start_all_requested)
        self.addAction(self.start_all_action)
        self.stop_all_action = QAction("Stop All", self)
        self.stop_all_action.setIcon(workspace_action_icon("stop", "#EF4444"))
        self.stop_all_action.setToolTip("Stop all phone schedulers")
        self.stop_all_action.triggered.connect(self.stop_all_requested)
        self.addAction(self.stop_all_action)
        self.fleet_separator = self.addSeparator()

        self.add_account_action = QAction("Add Account", self)
        self.add_account_action.setIcon(
            self.style().standardIcon(QStyle.SP_FileDialogNewFolder)
        )
        self.add_account_action.triggered.connect(self.add_account_requested)
        self.today_action = QAction("Today", self)
        self.today_action.setIcon(
            self.style().standardIcon(QStyle.SP_FileDialogDetailedView)
        )
        self.runtime_action = QAction("Start", self)
        self.runtime_action.setIcon(workspace_action_icon("start", "#22C55E"))
        self.runtime_action.setToolTip("Start this phone's scheduler")
        self.runtime_action.setStatusTip(
            "Start the persistent scheduler for this phone"
        )
        self.runtime_action.triggered.connect(self._request_runtime_action)
        self._runtime_running = False
        self.view_phone_action = QAction("View Phone", self)
        self.view_phone_action.setIcon(eye_icon())
        self.view_phone_action.setToolTip("Open the selected Android phone with scrcpy")
        self.view_phone_action.setStatusTip("View the selected Android phone")
        self.view_phone_action.triggered.connect(self.view_phone_requested)
        self.save_action = QAction("Save Changes", self)
        self.save_action.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton))
        self.save_action.setShortcut(QKeySequence.Save)
        self.save_action.triggered.connect(self.save_requested)
        self._future_actions = (
            self.add_account_action,
            self.today_action,
            self.runtime_action,
            self.view_phone_action,
            self.save_action,
        )
        for action in self._future_actions:
            action.setEnabled(False)
            self.addAction(action)

        self.widgetForAction(self.start_all_action).setObjectName("fleetStartButton")
        self.widgetForAction(self.stop_all_action).setObjectName("fleetStopButton")
        runtime_button = self.widgetForAction(self.runtime_action)
        runtime_button.setObjectName("runtimeButton")
        runtime_button.setProperty("runtimeState", "start")

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
        self.start_all_action.setVisible(context == "devices")
        self.stop_all_action.setVisible(context == "devices")
        self.fleet_separator.setVisible(context == "devices")
        self.view_phone_action.setEnabled(context in {"devices", "phone"})
        self.add_account_action.setEnabled(context == "phone")
        self.save_action.setEnabled(context == "account")
        for action in self._future_actions:
            action.setVisible(False)

        if context == "phone":
            for action in (
                self.add_account_action,
                self.today_action,
                self.runtime_action,
                self.view_phone_action,
            ):
                action.setVisible(True)
            self.options_button.setText("Device Options")
        elif context == "devices":
            self.view_phone_action.setVisible(True)
        elif context == "account":
            self.save_action.setVisible(True)
            self.options_button.setText("Account Options")

        self.options_button.setMenu(options_menu)
        self.options_action.setVisible(
            context in {"phone", "account"} and options_menu is not None
        )

    def set_runtime_controls(self, can_start: bool, can_stop: bool) -> None:
        self._runtime_running = can_stop
        self.runtime_action.setText("Stop" if can_stop else "Start")
        self.runtime_action.setIcon(
            workspace_action_icon(
                "stop" if can_stop else "start", "#EF4444" if can_stop else "#22C55E"
            )
        )
        self.runtime_action.setToolTip(
            "Stop this phone's scheduler"
            if can_stop
            else "Start this phone's scheduler"
        )
        self.runtime_action.setEnabled(can_start or can_stop)
        runtime_button = self.widgetForAction(self.runtime_action)
        runtime_button.setProperty("runtimeState", "stop" if can_stop else "start")
        runtime_button.style().unpolish(runtime_button)
        runtime_button.style().polish(runtime_button)

    def _request_runtime_action(self) -> None:
        if self._runtime_running:
            self.stop_requested.emit()
        else:
            self.start_requested.emit()
