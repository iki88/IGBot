from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ErrorDialog(QDialog):
    """Present an actionable failure using the established application theme."""

    def __init__(self, title: str, message: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("confirmationDialog")
        self.setWindowTitle(title)
        self.setMinimumWidth(440)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        heading = QLabel(title, self)
        heading.setObjectName("dialogTitle")
        detail = QLabel(message, self)
        detail.setObjectName("dialogDetail")
        detail.setWordWrap(True)
        close = QPushButton("Close", self)
        close.setObjectName("secondaryButton")
        close.clicked.connect(self.accept)
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(close)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)
        layout.addWidget(heading)
        layout.addWidget(detail)
        layout.addLayout(actions)
