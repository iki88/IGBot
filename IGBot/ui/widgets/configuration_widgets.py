from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QLabel,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class CollapsibleSection(QFrame):
    """Compact reusable section used by account configuration modules."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("contentCard")
        self.toggle = QToolButton(self)
        self.toggle.setObjectName("configurationSectionHeader")
        self.toggle.setText(title)
        self.toggle.setCheckable(True)
        self.toggle.setChecked(True)
        self.toggle.setArrowType(Qt.DownArrow)
        self.toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.body = QWidget(self)
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(10, 4, 10, 10)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.addWidget(self.toggle)
        layout.addWidget(self.body)
        self.toggle.toggled.connect(self._set_expanded)

    def _set_expanded(self, expanded: bool) -> None:
        self.body.setVisible(expanded)
        self.toggle.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)


class CheckboxGroup(QWidget):
    changed = Signal()

    def __init__(self, options: dict[str, str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controls = {}
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(24)
        layout.setVerticalSpacing(8)
        for index, (key, label) in enumerate(options.items()):
            control = QCheckBox(label, self)
            control.toggled.connect(self.changed)
            self.controls[key] = control
            layout.addWidget(control, index // 2, index % 2)

    def values(self) -> dict[str, bool]:
        return {key: control.isChecked() for key, control in self.controls.items()}

    def set_values(self, values: dict) -> None:
        for key, control in self.controls.items():
            control.setChecked(bool(values.get(key, False)))


class NumericSettings(QWidget):
    changed = Signal()

    def __init__(self, options: dict[str, str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controls = {}
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(8)
        for index, (key, label) in enumerate(options.items()):
            row, column = divmod(index, 2)
            heading = QLabel(label, self)
            control = QSpinBox(self)
            control.setRange(0, 100000)
            control.valueChanged.connect(self.changed)
            self.controls[key] = control
            layout.addWidget(heading, row, column * 2)
            layout.addWidget(control, row, column * 2 + 1)

    def values(self) -> dict[str, int]:
        return {key: control.value() for key, control in self.controls.items()}

    def set_values(self, values: dict) -> None:
        for key, control in self.controls.items():
            control.setValue(int(values.get(key, 0) or 0))
