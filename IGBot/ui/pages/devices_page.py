import logging

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QStyle,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from IGBot.core.device import DeviceRecord
from IGBot.ui.controllers.device_controller import DeviceController
from IGBot.ui.models.device_table_model import (
    DeviceFilterProxyModel,
    DeviceTableModel,
)
from IGBot.ui.widgets.confirmation_dialog import ConfirmationDialog
from IGBot.ui.widgets.device_actions_delegate import DeviceActionsDelegate
from IGBot.ui.widgets.empty_state import EmptyState
from IGBot.ui.widgets.page_header import PageHeader

logger = logging.getLogger(__name__)


class DevicesPage(QWidget):
    """Fleet management workspace backed by the persistent device inventory."""

    def __init__(
        self, controller: DeviceController, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("devicesPage")
        self._controller = controller
        self._devices: list[DeviceRecord] = []

        self.page_header = PageHeader(
            "Devices",
            "Monitor connectivity and manage phone account assignments.",
            self,
        )

        self.search = QLineEdit(self)
        self.search.setObjectName("deviceSearch")
        self.search.setPlaceholderText("Search by Device ID or Phone")
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(460)

        self.fleet_summary = QLabel("0 phones", self)
        self.fleet_summary.setObjectName("summaryText")
        self.connection_summary = QLabel("0 connected", self)
        self.connection_summary.setObjectName("connectedSummary")

        self.model = DeviceTableModel(self)
        self.proxy_model = DeviceFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.model)
        self.search.textChanged.connect(self._on_search_changed)

        self.table = QTableView(self)
        self.table.setObjectName("deviceTable")
        self.table.setModel(self.proxy_model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSortingEnabled(False)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.horizontalHeader().setSectionsClickable(False)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)

        self.actions_delegate = DeviceActionsDelegate(self.table)
        self.table.setItemDelegateForColumn(
            DeviceTableModel.ACTIONS, self.actions_delegate
        )
        self._configure_columns()

        self.empty_state = EmptyState(
            self.style().standardIcon(QStyle.SP_ComputerIcon),
            "No phones discovered",
            "Connect an Android phone through ADB, then refresh the workspace.",
            self,
        )

        self.error_banner = QLabel(self)
        self.error_banner.setObjectName("errorBanner")
        self.error_banner.setWordWrap(True)
        self.error_banner.hide()

        self._build_layout()
        self._connect_signals()
        self._update_content_visibility()

    def _configure_columns(self) -> None:
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionResizeMode(DeviceTableModel.PHONE, QHeaderView.Stretch)
        header.setSectionResizeMode(DeviceTableModel.ACTIONS, QHeaderView.Fixed)
        self.table.setColumnWidth(DeviceTableModel.CONNECTION, 54)
        self.table.setColumnWidth(DeviceTableModel.DEVICE_ID, 180)
        self.table.setColumnWidth(DeviceTableModel.PHONE, 175)
        self.table.setColumnWidth(DeviceTableModel.ACCOUNTS, 82)
        self.table.setColumnWidth(DeviceTableModel.STATUS, 86)
        self.table.setColumnWidth(DeviceTableModel.ACTIONS, 244)

    def _build_layout(self) -> None:
        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(12)
        controls.addWidget(self.search, 1)
        controls.addStretch()
        controls.addWidget(self.fleet_summary)
        controls.addWidget(self.connection_summary)

        card = QFrame(self)
        card.setObjectName("contentCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 14, 14, 14)
        card_layout.setSpacing(10)
        card_layout.addLayout(controls)
        card_layout.addWidget(self.error_banner)
        card_layout.addWidget(self.table, 1)
        card_layout.addWidget(self.empty_state, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(14)
        layout.addWidget(self.page_header)
        layout.addWidget(card, 1)

    def _connect_signals(self) -> None:
        self._controller.refresh_started.connect(self._on_refresh_started)
        self._controller.devices_changed.connect(self._set_devices)
        self._controller.discovery_failed.connect(self._show_error)
        self._controller.deletion_started.connect(self._on_deletion_started)
        self._controller.operation_failed.connect(self._show_operation_error)
        self.table.doubleClicked.connect(self._manage_index)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.actions_delegate.action_requested.connect(self._handle_row_action)

    def _on_refresh_started(self) -> None:
        self.error_banner.hide()

    def _set_devices(self, devices: list[DeviceRecord]) -> None:
        self.table.setEnabled(True)
        self._devices = devices
        self.model.set_devices(devices)
        self._update_summaries()
        self._update_content_visibility()

    def _show_error(self, message: str) -> None:
        self._show_operation_error(message)

    def _show_operation_error(self, message: str) -> None:
        self.table.setEnabled(True)
        self.error_banner.setText(message)
        self.error_banner.show()

    def _on_deletion_started(self, serial: str) -> None:
        self.table.setEnabled(False)
        self.error_banner.hide()

    def _on_search_changed(self, query: str) -> None:
        self.proxy_model.set_query(query)
        self._update_summaries()
        self._update_content_visibility()

    def _update_summaries(self) -> None:
        total = len(self._devices)
        visible = self.proxy_model.rowCount()
        connected = sum(device.connected for device in self._devices)
        self.fleet_summary.setText(
            f"{visible} of {total} phones" if self.search.text() else f"{total} phones"
        )
        self.connection_summary.setText(f"{connected} connected")

    def _update_content_visibility(self) -> None:
        visible_rows = self.proxy_model.rowCount()
        self.table.setVisible(visible_rows > 0)
        self.empty_state.setVisible(visible_rows == 0)
        if self.model.rowCount() > 0 and visible_rows == 0:
            self.empty_state.set_content(
                "No matching phones",
                "Try a different Device ID or phone name.",
            )
        else:
            self.empty_state.set_content(
                "No phones discovered",
                "Connect an Android phone through ADB, then refresh the workspace.",
            )

    def _manage_index(self, proxy_index) -> None:
        if proxy_index.isValid():
            self._controller.open_phone_accounts(proxy_index.data(Qt.UserRole))

    def _handle_row_action(self, action: str, serial: str) -> None:
        if action == "manage":
            self._controller.open_phone_accounts(serial)
        elif action == "delete" and self._confirm_delete(serial):
            self._controller.delete_device(serial)

    def _show_context_menu(self, position: QPoint) -> None:
        index = self.table.indexAt(position)
        if not index.isValid() or index.column() != DeviceTableModel.DEVICE_ID:
            return

        menu = QMenu(self.table)
        copy_action = QAction("Copy Device ID", menu)
        copy_action.triggered.connect(
            lambda: self._copy_device_id(index.data(Qt.UserRole))
        )
        menu.addAction(copy_action)
        menu.exec(self.table.viewport().mapToGlobal(position))

    def _copy_device_id(self, serial: str) -> None:
        QApplication.clipboard().setText(serial)
        logger.info("Copied device ID to the clipboard")

    def _confirm_delete(self, serial: str) -> bool:
        if not self._show_delete_dialog(
            title="Delete Device?",
            text=f"Remove {serial} from IGBot?",
        ):
            return False
        return self._show_delete_dialog(
            title="Are you sure?",
            text="This action cannot be undone.",
        )

    def _show_delete_dialog(self, title: str, text: str) -> bool:
        detail = (
            "The phone will remain hidden until it disconnects from ADB."
            if title == "Delete Device?"
            else "Device-specific IGBot metadata will be removed."
        )
        return ConfirmationDialog.confirm(title, text, detail, self)
