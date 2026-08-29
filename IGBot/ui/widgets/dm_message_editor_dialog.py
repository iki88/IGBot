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


class DMMessageEditorDialog(QDialog):
    """Themed editor for one multiline engine-compatible DM template."""

    def __init__(self, message: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("inputDialog")
        self.setWindowTitle("Edit DM Message")
        self.setMinimumSize(560, 440)

        heading = QLabel("Edit DM Message", self)
        heading.setObjectName("dialogTitle")
        guidance = QLabel(
            "Write one message. Spintax, emoji, and multiple lines are supported.",
            self,
        )
        guidance.setObjectName("dialogFieldLabel")
        guidance.setWordWrap(True)
        self.editor = QPlainTextEdit(self)
        self.editor.setObjectName("dialogInput")
        self.editor.setPlaceholderText("Write the direct message here…")
        self.editor.setPlainText(message)
        self.error = QLabel(self)
        self.error.setObjectName("dialogError")
        self.error.hide()

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

    def message(self) -> str:
        return self.editor.toPlainText().strip()

    def _validate_and_accept(self) -> None:
        if not self.message():
            self.error.setText("Enter a direct message before saving.")
            self.error.show()
            self.editor.setFocus()
            return
        self.accept()
