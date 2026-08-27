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


class TargetEditorDialog(QDialog):
    """Reusable themed one-entry-per-line editor for operator-managed targets."""

    def __init__(
        self,
        title: str,
        entries: list[str] | tuple[str, ...] = (),
        validator: Callable[[str], bool] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._validator = validator
        self.setObjectName("inputDialog")
        self.setWindowTitle(title)
        self.setMinimumSize(560, 440)

        heading = QLabel(title, self)
        heading.setObjectName("dialogTitle")
        guidance = QLabel("Enter one target per line.", self)
        guidance.setObjectName("dialogFieldLabel")
        self.editor = QPlainTextEdit(self)
        self.editor.setObjectName("dialogInput")
        self.editor.setPlainText("\n".join(entries))
        self.error = QLabel(self)
        self.error.setObjectName("dialogError")
        self.error.hide()

        deduplicate = QPushButton("Remove Duplicates", self)
        deduplicate.setObjectName("secondaryButton")
        deduplicate.clicked.connect(self.remove_duplicates)
        cancel = QPushButton("Cancel", self)
        cancel.setObjectName("secondaryButton")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save", self)
        save.setObjectName("primaryButton")
        save.setDefault(True)
        save.clicked.connect(self._validate_and_accept)
        self.save_shortcut = QShortcut(QKeySequence.Save, self)
        self.save_shortcut.activated.connect(self._validate_and_accept)

        actions = QHBoxLayout()
        actions.addWidget(deduplicate)
        actions.addStretch()
        actions.addWidget(cancel)
        actions.addWidget(save)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 22)
        layout.setSpacing(11)
        layout.addWidget(heading)
        layout.addWidget(guidance)
        layout.addWidget(self.editor, 1)
        layout.addWidget(self.error)
        layout.addLayout(actions)

    def entries(self) -> list[str]:
        return [
            line.strip()
            for line in self.editor.toPlainText().splitlines()
            if line.strip()
        ]

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
