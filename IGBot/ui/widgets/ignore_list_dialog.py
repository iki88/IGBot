"""Account-local Ignore List editor."""

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from IGBot.runtime.ignore import IgnoreService


class IgnoreListDialog(QDialog):
    """Edit normalized, account-local ignored usernames."""

    def __init__(self, entries=(), parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("inputDialog")
        self.setMinimumSize(620, 480)
        self.heading = QLabel("Ignored Accounts List", self)
        self.heading.setObjectName("dialogTitle")
        self.count = QLabel(self)
        self.count.setObjectName("dialogFieldLabel")
        self.guidance = QLabel(
            "One username per line.\n"
            "Usernames are automatically normalized to lowercase, trimmed, and "
            "deduplicated when saving.",
            self,
        )
        self.guidance.setObjectName("dialogFieldLabel")
        self.guidance.setWordWrap(True)
        self.editor = QPlainTextEdit(self)
        self.editor.setObjectName("dialogInput")
        self.editor.setPlainText("\n".join(IgnoreService.normalize_many(entries)))
        self.editor.textChanged.connect(self._update_count)

        self.cancel_button = QPushButton("Cancel", self)
        self.save_button = QPushButton("Save", self)
        self.cancel_button.setObjectName("secondaryButton")
        self.save_button.setObjectName("primaryButton")
        self.save_button.setDefault(True)

        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self._save)

        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.save_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 22)
        layout.setSpacing(11)
        layout.addWidget(self.heading)
        layout.addWidget(self.count)
        layout.addWidget(self.guidance)
        layout.addWidget(self.editor, 1)
        layout.addLayout(actions)
        self._update_count()

    def entries(self) -> list[str]:
        return list(
            IgnoreService.normalize_many(self.editor.toPlainText().splitlines())
        )

    def _update_count(self) -> None:
        total = len(self.entries())
        self.count.setText(f"{total} accounts")
        self.setWindowTitle(f"Ignored Accounts List — {total} accounts")

    def _save(self) -> None:
        self.editor.setPlainText("\n".join(self.entries()))
        self.accept()
