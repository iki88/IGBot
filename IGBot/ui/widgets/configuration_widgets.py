import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
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
        self.toggle.setCheckable(False)
        self.toggle.setArrowType(Qt.NoArrow)
        self.toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.body = QWidget(self)
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(10, 4, 10, 10)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.addWidget(self.toggle)
        layout.addWidget(self.body)


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


class RangeSettings(QWidget):
    """Reusable engine integer/range editors with inline validation."""

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
            control = QLineEdit(self)
            control.setObjectName("dialogInput")
            control.setPlaceholderText("0 or 10-20")
            control.textChanged.connect(self.changed)
            self.controls[key] = control
            layout.addWidget(heading, row, column * 2)
            layout.addWidget(control, row, column * 2 + 1)

    def set_values(self, values: dict) -> None:
        for key, control in self.controls.items():
            value = values.get(key)
            control.setText("" if value is None else str(value))
            control.setStyleSheet("")

    def values(self) -> dict[str, str]:
        values = {}
        for key, control in self.controls.items():
            value = control.text().strip()
            valid = not value or bool(re.fullmatch(r"\d+(?:-\d+)?", value))
            if valid and "-" in value:
                minimum, maximum = (int(part) for part in value.split("-", 1))
                valid = minimum <= maximum
            control.setStyleSheet("" if valid else "border: 1px solid #EF4444;")
            if not valid:
                control.setFocus()
                raise ValueError(f"{key} must be a number or ascending range.")
            values[key] = value
        return values


class TextListSettings(QWidget):
    """Reusable one-entry-per-line editors for engine list settings."""

    changed = Signal()

    def __init__(self, options: dict[str, str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controls = {}
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(8)
        for column, (key, label) in enumerate(options.items()):
            heading = QLabel(label, self)
            control = QPlainTextEdit(self)
            control.setObjectName("dialogInput")
            control.setPlaceholderText("One file entry per line")
            control.setMaximumHeight(92)
            control.textChanged.connect(self.changed)
            self.controls[key] = control
            layout.addWidget(heading, 0, column)
            layout.addWidget(control, 1, column)

    def set_values(self, values: dict) -> None:
        for key, control in self.controls.items():
            value = values.get(key) or []
            control.setPlainText("\n".join(str(item) for item in value))

    def values(self) -> dict[str, list[str]]:
        return {
            key: [
                line.strip()
                for line in control.toPlainText().splitlines()
                if line.strip()
            ]
            for key, control in self.controls.items()
        }


class TextResourceEditor(QWidget):
    """Reusable editor for engine-owned free-form account text resources."""

    changed = Signal()

    def __init__(
        self, label: str, placeholder: str = "", parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(QLabel(label, self))
        self.editor = QPlainTextEdit(self)
        self.editor.setObjectName("dialogInput")
        self.editor.setPlaceholderText(placeholder)
        self.editor.setMinimumHeight(180)
        self.editor.textChanged.connect(self.changed)
        layout.addWidget(self.editor)

    def set_text(self, value: str) -> None:
        self.editor.setPlainText(value)

    def text(self) -> str:
        return self.editor.toPlainText()
