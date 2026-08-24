from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class EmptyState(QWidget):
    """Consistent empty result presentation for application workspaces."""

    def __init__(
        self,
        icon: QIcon,
        title: str,
        description: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("emptyState")

        self.icon = QLabel(self)
        self.icon.setObjectName("emptyStateIcon")
        self.icon.setAlignment(Qt.AlignCenter)
        self.icon.setPixmap(icon.pixmap(32, 32))

        self.title = QLabel(title, self)
        self.title.setObjectName("emptyStateTitle")
        self.title.setAlignment(Qt.AlignCenter)

        self.description = QLabel(description, self)
        self.description.setObjectName("emptyStateDescription")
        self.description.setAlignment(Qt.AlignCenter)
        self.description.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(7)
        layout.addStretch()
        layout.addWidget(self.icon)
        layout.addWidget(self.title)
        layout.addWidget(self.description)
        layout.addStretch()

    def set_content(self, title: str, description: str) -> None:
        self.title.setText(title)
        self.description.setText(description)
