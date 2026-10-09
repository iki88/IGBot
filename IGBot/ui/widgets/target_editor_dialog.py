from collections.abc import Callable

from PySide6.QtGui import QKeySequence, QShortcut
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


class TargetEditorDialog(QDialog):
    """Reusable themed one-entry-per-line editor for operator-managed targets."""

    def __init__(
        self,
        title: str,
        entries: list[str] | tuple[str, ...] = (),
        validator: Callable[[str], bool] | None = None,
        parent: QWidget | None = None,
        *,
        specific_users: bool = False,
    ) -> None:
        super().__init__(parent)
        self._validator = validator
        self._specific_users = specific_users
        self.setObjectName("inputDialog")
        self.setWindowTitle(title)
        self.setMinimumSize(620, 480 if specific_users else 440)

        self.heading = QLabel(title, self)
        self.heading.setObjectName("dialogTitle")
        self.count = QLabel(self)
        self.count.setObjectName("dialogFieldLabel")
        guidance_text = (
            "One username per line.\n"
            "Usernames are automatically normalized to lowercase, trimmed, and "
            "deduplicated when saving."
            if specific_users
            else "Enter one target per line."
        )
        self.guidance = QLabel(guidance_text, self)
        self.guidance.setObjectName("dialogFieldLabel")
        self.guidance.setWordWrap(True)
        self.editor = QPlainTextEdit(self)
        self.editor.setObjectName("dialogInput")
        initial_entries = (
            IgnoreService.normalize_many(entries) if specific_users else entries
        )
        self.editor.setPlainText("\n".join(initial_entries))
        if specific_users:
            self.editor.textChanged.connect(self._update_count)
        self.error = QLabel(self)
        self.error.setObjectName("dialogError")
        self.error.hide()

        self.deduplicate_button = None
        if not specific_users:
            self.deduplicate_button = QPushButton("Remove Duplicates", self)
            self.deduplicate_button.setObjectName("secondaryButton")
            self.deduplicate_button.clicked.connect(self.remove_duplicates)
        self.cancel_button = QPushButton("Cancel", self)
        self.cancel_button.setObjectName("secondaryButton")
        self.cancel_button.clicked.connect(self.reject)
        self.save_button = QPushButton("Save", self)
        self.save_button.setObjectName("primaryButton")
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self._validate_and_accept)
        self.save_shortcut = QShortcut(QKeySequence.Save, self)
        self.save_shortcut.activated.connect(self._validate_and_accept)

        actions = QHBoxLayout()
        if self.deduplicate_button is not None:
            actions.addWidget(self.deduplicate_button)
        actions.addStretch()
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.save_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 22)
        layout.setSpacing(11)
        layout.addWidget(self.heading)
        if specific_users:
            layout.addWidget(self.count)
        layout.addWidget(self.guidance)
        layout.addWidget(self.editor, 1)
        layout.addWidget(self.error)
        layout.addLayout(actions)
        if specific_users:
            self._update_count()

    def entries(self) -> list[str]:
        entries = [
            line.strip()
            for line in self.editor.toPlainText().splitlines()
            if line.strip()
        ]
        if self._specific_users:
            return list(IgnoreService.normalize_many(entries))
        return entries

    def _update_count(self) -> None:
        self.count.setText(f"{len(self.entries())} accounts")

    def remove_duplicates(self) -> None:
        unique = []
        seen = set()
        for entry in self.entries():
            identity = entry.casefold()
            if identity not in seen:
                seen.add(identity)
                unique.append(entry)
        self.editor.setPlainText("\n".join(unique))

    def _validate_and_accept(self) -> None:
        entries = self.entries()
        invalid = [
            entry for entry in entries if self._validator and not self._validator(entry)
        ]
        if invalid:
            self.error.setText(f"Invalid target: {invalid[0]}")
            self.error.show()
            self.editor.setFocus()
            return
        self.editor.setPlainText("\n".join(entries))
        self.accept()
