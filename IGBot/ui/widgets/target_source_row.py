from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QPushButton, QWidget


class TargetSourceRow(QWidget):
    """Reusable source switch and editor launcher with a compact target count."""

    changed = Signal()
    edit_requested = Signal()

    def __init__(
        self,
        label: str,
        parent: QWidget | None = None,
        item_noun: str = "target",
        switch_style: bool = True,
    ) -> None:
        super().__init__(parent)
        self._entries: list[str] = []
        self._item_noun = item_noun
        self.enabled = QCheckBox(self)
        if switch_style:
            self.enabled.setObjectName("configurationSwitch")
        self.name = QPushButton(label, self)
        self.name.setObjectName("linkButton" if switch_style else "checkboxLinkButton")
        self.name.setCursor(Qt.PointingHandCursor)
        self.count = QLabel(f"0 {item_noun}s", self)
        self.count.setObjectName("mutedLabel")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.enabled)
        layout.addWidget(self.name)
        layout.addStretch()
        layout.addWidget(self.count)
        self.enabled.toggled.connect(self.changed)
        self.name.clicked.connect(self.edit_requested)

    def set_entries(self, entries: list[str] | tuple[str, ...]) -> None:
        self._entries = list(entries)
        count = len(self._entries)
        noun = self._item_noun if count == 1 else f"{self._item_noun}s"
        self.count.setText(f"{count} {noun}")

    def entries(self) -> list[str]:
        return list(self._entries)
