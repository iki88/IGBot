from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class TemplateSelectionDialog(QDialog):
    """Select an existing behaviour template for one-time application."""

    def __init__(
        self, templates: tuple[str, ...], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("inputDialog")
        self.setWindowTitle("Apply Template")
        self.template = QComboBox(self)
        self.template.setObjectName("dialogInput")
        self.template.addItems(templates)
        cancel = QPushButton("Cancel", self)
        cancel.setObjectName("secondaryButton")
        cancel.clicked.connect(self.reject)
        apply_button = QPushButton("Apply", self)
        apply_button.setObjectName("primaryButton")
        apply_button.clicked.connect(self.accept)
        apply_button.setEnabled(bool(templates))
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(cancel)
        actions.addWidget(apply_button)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Template", self))
        layout.addWidget(self.template)
        layout.addLayout(actions)

    def selected_template(self) -> str:
        return self.template.currentText()
