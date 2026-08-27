from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from IGBot.core.device import DeviceRecord


class AddAccountDialog(QDialog):
    """Collect credentials for the phone already open in the current workspace."""

    def __init__(
        self,
        device: DeviceRecord,
        templates: tuple[str, ...] = (),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("addAccountDialog")
        self.setWindowTitle("Add Account")
        self.setMinimumWidth(480)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

        title = QLabel("Add Account", self)
        title.setObjectName("dialogTitle")
        self.phone_name = QLabel(device.phone_name or "Unnamed phone", self)
        self.phone_name.setObjectName("dialogSubtitle")
        self.device_id = QLabel(device.serial, self)
        self.device_id.setObjectName("dialogHint")

        username_label = QLabel("USERNAME", self)
        username_label.setObjectName("dialogFieldLabel")
        self.username = QLineEdit(self)
        self.username.setObjectName("dialogInput")
        self.username.setPlaceholderText("Instagram username")

        password_label = QLabel("PASSWORD", self)
        password_label.setObjectName("dialogFieldLabel")
        self.password = QLineEdit(self)
        self.password.setObjectName("dialogInput")
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setPlaceholderText("Instagram password")

        template_label = QLabel("TEMPLATE (OPTIONAL)", self)
        template_label.setObjectName("dialogFieldLabel")
        self.template = QComboBox(self)
        self.template.setObjectName("dialogInput")
        self.template.addItem("None", "")
        for name in templates:
            self.template.addItem(name, name)

        self.add_button = QPushButton("Add Account", self)
        self.add_button.setObjectName("primaryButton")
        self.add_button.setEnabled(False)
        self.add_button.clicked.connect(self.accept)
        cancel = QPushButton("Cancel", self)
        cancel.setObjectName("secondaryButton")
        cancel.clicked.connect(self.reject)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 12, 0, 0)
        actions.setSpacing(9)
        actions.addStretch()
        actions.addWidget(cancel)
        actions.addWidget(self.add_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 22)
        layout.setSpacing(9)
        layout.addWidget(title)
        layout.addWidget(self.phone_name)
        layout.addWidget(self.device_id)
        layout.addSpacing(8)
        layout.addWidget(username_label)
        layout.addWidget(self.username)
        layout.addSpacing(5)
        layout.addWidget(password_label)
        layout.addWidget(self.password)
        layout.addSpacing(5)
        layout.addWidget(template_label)
        layout.addWidget(self.template)
        layout.addLayout(actions)

        self.username.textChanged.connect(self._update_submit)
        self.password.textChanged.connect(self._update_submit)

    def _update_submit(self) -> None:
        self.add_button.setEnabled(
            bool(self.username.text().strip()) and bool(self.password.text())
        )

    def selected_template(self) -> str:
        return str(self.template.currentData() or "")
