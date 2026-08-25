from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class TextInputDialog(QDialog):
    """Application-styled text input for concise desktop workflows."""

    def __init__(
        self,
        title: str,
        label: str,
        value: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("inputDialog")
        self.setWindowTitle(title)
        self.setMinimumWidth(440)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

        heading = QLabel(title, self)
        heading.setObjectName("dialogTitle")
        field_label = QLabel(label, self)
        field_label.setObjectName("dialogFieldLabel")
        self.input = QLineEdit(value, self)
        self.input.setObjectName("dialogInput")
        self.input.selectAll()

        cancel = QPushButton("Cancel", self)
        cancel.setObjectName("secondaryButton")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save Changes", self)
        save.setObjectName("primaryButton")
        save.setDefault(True)
        save.clicked.connect(self.accept)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 12, 0, 0)
        actions.setSpacing(10)
        actions.addStretch()
        actions.addWidget(cancel)
        actions.addWidget(save)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 22)
        layout.setSpacing(11)
        layout.addWidget(heading)
        layout.addSpacing(5)
        layout.addWidget(field_label)
        layout.addWidget(self.input)
        layout.addLayout(actions)

    @classmethod
    def get_text(
        cls,
        title: str,
        label: str,
        value: str,
        parent: QWidget | None = None,
    ) -> tuple[str, bool]:
        dialog = cls(title, label, value, parent)
        accepted = dialog.exec() == QDialog.Accepted
        return dialog.input.text(), accepted
