from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QPushButton, QWidget


class TargetSourceRow(QWidget):
    """Reusable source switch and editor launcher with a compact target count."""

    changed = Signal()
    edit_requested = Signal()

    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._entries: list[str] = []
        self.enabled = QCheckBox(self)
        self.enabled.setObjectName("configurationSwitch")
        self.name = QPushButton(label, self)
        self.name.setObjectName("linkButton")
        self.count = QLabel("0 targets", self)
        self.count.setObjectName("mutedLabel")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.enabled)
        layout.addWidget(self.name)
        layout.addStretch()
        layout.addWidget(self.count)
        self.enabled.toggled.connect(self.changed)
        self.name.clicked.connect(self.edit_requested)

    def set_entries(self, entries: list[str] | tuple[str, ...]) -> None:
        self._entries = list(entries)
        count = len(self._entries)
        self.count.setText(f"{count} {'target' if count == 1 else 'targets'}")

    def entries(self) -> list[str]:
        return list(self._entries)
