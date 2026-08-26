from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QVBoxLayout,
)


class PackageSelectionDialog(QDialog):
    def __init__(self, packages: list[str], parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("confirmationDialog")
        self.setWindowTitle("Select Application ID")
        self.resize(540, 440)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Installed application packages", self))
        self.packages = QListWidget(self)
        self.packages.addItems(packages)
        self.packages.itemDoubleClicked.connect(lambda _: self.accept())
        layout.addWidget(self.packages)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.Ok).setEnabled(False)
        self.packages.currentItemChanged.connect(
            lambda item: buttons.button(QDialogButtonBox.Ok).setEnabled(
                item is not None
            )
        )
        layout.addWidget(buttons)

    @property
    def selected_package(self) -> str:
        item = self.packages.currentItem()
        return item.text() if item else ""
