from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget


class PageHeader(QWidget):
    """Compact, reusable heading for IGBot workspaces."""

    def __init__(
        self,
        title: str,
        subtitle: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("pageHeader")

        self.title = QLabel(title, self)
        self.title.setObjectName("pageTitle")
        self.subtitle = QLabel(subtitle, self)
        self.subtitle.setObjectName("pageSubtitle")

        self.actions = QHBoxLayout()
        self.actions.setContentsMargins(0, 0, 0, 0)
        self.actions.setSpacing(8)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        text_layout.addWidget(self.title)
        text_layout.addWidget(self.subtitle)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        layout.addLayout(text_layout, 1)
        layout.addLayout(self.actions)

    def add_action_widget(self, widget: QWidget) -> None:
        self.actions.addWidget(widget)
