from pathlib import Path

from PySide6.QtWidgets import QFormLayout, QFrame, QLabel, QVBoxLayout, QWidget

from IGBot.ui.version import APPLICATION_VERSION
from IGBot.ui.widgets.page_header import PageHeader


class GlobalSettingsPage(QWidget):
    """Read-only application configuration available without backend changes."""

    def __init__(self, workspace: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("globalSettingsPage")
        header = PageHeader(
            "Global Settings",
            "Application configuration and workspace locations.",
            self,
        )
        card = QFrame(self)
        card.setObjectName("contentCard")
        fields = QFormLayout(card)
        fields.setContentsMargins(18, 18, 18, 18)
        fields.setSpacing(12)
        fields.addRow("Application version", QLabel(APPLICATION_VERSION, card))
        fields.addRow("Appearance", QLabel("Dark", card))
        fields.addRow("Workspace", QLabel(str(workspace), card))
        fields.addRow("Accounts directory", QLabel(str(workspace / "accounts"), card))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(12)
        layout.addWidget(header)
        layout.addWidget(card)
        layout.addStretch()
