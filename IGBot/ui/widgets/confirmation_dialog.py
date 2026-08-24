from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ConfirmationDialog(QDialog):
    """Application-styled confirmation dialog with a safe default action."""

    def __init__(
        self,
        title: str,
        message: str,
        detail: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("confirmationDialog")
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(440)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

        title_label = QLabel(title, self)
        title_label.setObjectName("dialogTitle")
        message_label = QLabel(message, self)
        message_label.setObjectName("dialogMessage")
        message_label.setWordWrap(True)
        detail_label = QLabel(detail, self)
        detail_label.setObjectName("dialogDetail")
        detail_label.setWordWrap(True)

        cancel_button = QPushButton("Cancel", self)
        cancel_button.setObjectName("secondaryButton")
        cancel_button.clicked.connect(self.reject)
        delete_button = QPushButton("Delete", self)
        delete_button.setObjectName("dangerButton")
        delete_button.clicked.connect(self.accept)
        cancel_button.setDefault(True)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 8, 0, 0)
        actions.setSpacing(8)
        actions.addStretch()
        actions.addWidget(cancel_button)
        actions.addWidget(delete_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(9)
        layout.addWidget(title_label)
        layout.addWidget(message_label)
        layout.addWidget(detail_label)
        layout.addLayout(actions)

    @classmethod
    def confirm(
        cls,
        title: str,
        message: str,
        detail: str,
        parent: QWidget | None = None,
    ) -> bool:
        return cls(title, message, detail, parent).exec() == QDialog.Accepted
