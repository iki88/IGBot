from PySide6.QtWidgets import QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from IGBot.ui.widgets.live_log_panel import LiveLogPanel
from IGBot.ui.widgets.page_header import PageHeader


class ActivityLogPage(QWidget):
    """Full-size view of the existing application activity log."""

    def __init__(self, live_log: LiveLogPanel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("activityLogPage")
        self.page_header = PageHeader(
            "Activity Log", "Application events and account operations.", self
        )
        clear = QPushButton("Clear", self)
        clear.setObjectName("secondaryButton")
        clear.clicked.connect(live_log.output.clear)
        self.page_header.add_action_widget(clear)

        self.output = QPlainTextEdit(self)
        self.output.setObjectName("liveLogOutput")
        self.output.setReadOnly(True)
        self.output.setDocument(live_log.output.document())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(12)
        layout.addWidget(self.page_header)
        layout.addWidget(self.output, 1)
