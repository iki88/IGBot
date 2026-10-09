from PySide6.QtCore import Qt
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

    MAX_CHARACTERS = 1000

    def __init__(self, message: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("inputDialog")
        self.setWindowTitle("Edit DM Message")
        self.setMinimumSize(560, 440)

        heading = QLabel("Edit DM Message", self)
        heading.setObjectName("dialogTitle")
        guidance = QLabel(
            "Write one message.\n\n"
            "Supports multiple lines, Unicode emoji and Spintax.\n\n"
            "The same rendered message is sent to every recipient.",
            self,
        )
        guidance.setObjectName("dialogFieldLabel")
        guidance.setWordWrap(True)
        self.editor = QPlainTextEdit(self)
        self.editor.setObjectName("dialogInput")
        self.editor.setPlaceholderText("Write the direct message here…")
        self.counter = QLabel(self)
        self.counter.setObjectName("mutedLabel")
        self.counter.setAlignment(Qt.AlignRight)
        clean_label_style = "background: transparent; border: none; padding: 0;"
        heading.setStyleSheet(clean_label_style)
        guidance.setStyleSheet(clean_label_style)
        self.counter.setStyleSheet(clean_label_style)
        self.editor.textChanged.connect(self._enforce_limit)
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
        layout.addWidget(self.counter)
        layout.addWidget(self.error)
        layout.addLayout(actions)

    def message(self) -> str:
        return self.editor.toPlainText()

    def _enforce_limit(self) -> None:
        text = self.editor.toPlainText()
        if len(text) > self.MAX_CHARACTERS:
            position = min(self.editor.textCursor().position(), self.MAX_CHARACTERS)
            self.editor.blockSignals(True)
            self.editor.setPlainText(text[: self.MAX_CHARACTERS])
            cursor = self.editor.textCursor()
            cursor.setPosition(position)
            self.editor.setTextCursor(cursor)
            self.editor.blockSignals(False)
        self._update_counter()

    def _update_counter(self) -> None:
        self.counter.setText(
            f"{len(self.editor.toPlainText())} / {self.MAX_CHARACTERS} characters"
        )

    def _validate_and_accept(self) -> None:
        self.accept()
