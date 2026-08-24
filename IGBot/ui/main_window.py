from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMainWindow, QSplitter, QStackedWidget

from IGBot.ui.controllers.device_controller import DeviceController
from IGBot.ui.pages.devices_page import DevicesPage
from IGBot.ui.widgets.live_log_panel import LiveLogPanel
from IGBot.ui.widgets.navigation_sidebar import NavigationSidebar
from IGBot.ui.widgets.top_toolbar import TopToolbar


class MainWindow(QMainWindow):
    """Top-level application shell for IGBot desktop."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("mainWindow")
        self.setWindowTitle("IGBot")
        self.resize(1440, 900)
        self.setMinimumSize(960, 640)

        self.device_controller = DeviceController(self)
        self.sidebar = NavigationSidebar(self)
        self.toolbar = TopToolbar(self)
        self.pages = QStackedWidget(self)
        self.devices_page = DevicesPage(self.device_controller, self)
        self.live_log = LiveLogPanel(self)

        self._build_shell()
        self._connect_signals()
        self.device_controller.refresh()

    def _build_shell(self) -> None:
        self.addToolBar(Qt.TopToolBarArea, self.toolbar)

        self.pages.addWidget(self.devices_page)

        content_splitter = QSplitter(Qt.Vertical, self)
        content_splitter.setObjectName("contentSplitter")
        content_splitter.addWidget(self.pages)
        content_splitter.addWidget(self.live_log)
        content_splitter.setSizes([650, 220])
        content_splitter.setStretchFactor(0, 4)
        content_splitter.setStretchFactor(1, 1)
        content_splitter.setChildrenCollapsible(False)

        shell = QSplitter(Qt.Horizontal, self)
        shell.setObjectName("shellSplitter")
        shell.addWidget(self.sidebar)
        shell.addWidget(content_splitter)
        shell.setSizes([230, 1210])
        shell.setStretchFactor(0, 0)
        shell.setStretchFactor(1, 1)
        shell.setCollapsible(0, False)
        shell.setChildrenCollapsible(False)
        self.setCentralWidget(shell)

        self.statusBar().showMessage("Ready")

    def _connect_signals(self) -> None:
        self.sidebar.page_selected.connect(self.pages.setCurrentIndex)
        self.toolbar.refresh_requested.connect(self.device_controller.refresh)
        self.device_controller.refresh_started.connect(
            lambda: self.statusBar().showMessage("Discovering Android devices…")
        )
        self.device_controller.devices_changed.connect(self._show_device_count)
        self.device_controller.discovery_failed.connect(
            lambda message: self.statusBar().showMessage(message)
        )

    def _show_device_count(self, devices: list[str]) -> None:
        count = len(devices)
        noun = "device" if count == 1 else "devices"
        self.statusBar().showMessage(f"{count} connected {noun}")

    def closeEvent(self, event) -> None:
        self.live_log.detach_logging()
        super().closeEvent(event)
