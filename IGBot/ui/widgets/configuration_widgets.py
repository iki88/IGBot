import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
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


class WheelSafeSpinBox(QSpinBox):
    """Integer editor that ignores incidental mouse-wheel input."""

    def wheelEvent(self, event) -> None:
        event.ignore()


class WheelSafeDoubleSpinBox(QDoubleSpinBox):
    """Decimal editor that ignores incidental mouse-wheel input."""

    def wheelEvent(self, event) -> None:
        event.ignore()


class CollapsibleSection(QFrame):
    """Compact reusable section used by account configuration modules."""

    def __init__(
        self,
        title: str,
        parent: QWidget | None = None,
        collapsible: bool = False,
        collapsed: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("contentCard")
        self.toggle = QToolButton(self)
        self.toggle.setObjectName("configurationSectionHeader")
        self.toggle.setText(title)
        self.toggle.setCheckable(collapsible)
        self.toggle.setChecked(collapsible and not collapsed)
        self.toggle.setArrowType(
            Qt.RightArrow
            if collapsible and collapsed
            else Qt.DownArrow if collapsible else Qt.NoArrow
        )
        self.toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.body = QWidget(self)
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(10, 4, 10, 10)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.addWidget(self.toggle)
        layout.addWidget(self.body)
        if collapsible:
            self.body.setVisible(not collapsed)
            self.toggle.toggled.connect(self._set_expanded)

    def _set_expanded(self, expanded: bool) -> None:
        self.body.setVisible(expanded)
        self.toggle.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)


class ConfigurationSection(QFrame):
    """Static section for continuously scrollable configuration pages."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("contentCard")
        self.title = QLabel(title, self)
        self.title.setObjectName("configurationSectionTitle")
        self.body_layout = QVBoxLayout()
        self.body_layout.setContentsMargins(10, 4, 10, 10)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)
        layout.addWidget(self.title)
        layout.addLayout(self.body_layout)


class CheckboxGroup(QWidget):
    changed = Signal()

    def __init__(
        self,
        options: dict[str, str],
        parent: QWidget | None = None,
        columns: int = 2,
    ) -> None:
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
            layout.addWidget(control, index // columns, index % columns)

    def values(self) -> dict[str, bool]:
        return {key: control.isChecked() for key, control in self.controls.items()}

    def set_values(self, values: dict) -> None:
        for key, control in self.controls.items():
            control.setChecked(bool(values.get(key, False)))


class NumericSettings(QWidget):
    changed = Signal()

    def __init__(
        self,
        options: dict[str, str],
        parent: QWidget | None = None,
        columns: int = 2,
    ) -> None:
        super().__init__(parent)
        self.controls = {}
        self.labels = {}
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(8)
        for index, (key, label) in enumerate(options.items()):
            row, column = divmod(index, columns)
            heading = QLabel(label, self)
            control = WheelSafeSpinBox(self)
            control.setRange(0, 100000)
            control.valueChanged.connect(self.changed)
            self.controls[key] = control
            self.labels[key] = heading
            layout.addWidget(heading, row, column * 2)
            layout.addWidget(control, row, column * 2 + 1)

    def values(self) -> dict[str, int]:
        return {key: control.value() for key, control in self.controls.items()}

    def set_values(self, values: dict) -> None:
        for key, control in self.controls.items():
            control.setValue(int(values.get(key, 0) or 0))


class DecimalSettings(QWidget):
    """Reusable decimal editors for engine filter thresholds."""

    changed = Signal()

    def __init__(
        self,
        options: dict[str, str],
        parent: QWidget | None = None,
        columns: int = 2,
    ) -> None:
        super().__init__(parent)
        self.controls = {}
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(8)
        for index, (key, label) in enumerate(options.items()):
            row, column = divmod(index, columns)
            heading = QLabel(label, self)
            control = WheelSafeDoubleSpinBox(self)
            control.setRange(0, 1000000)
            control.setDecimals(2)
            control.valueChanged.connect(self.changed)
            self.controls[key] = control
            layout.addWidget(heading, row, column * 2)
            layout.addWidget(control, row, column * 2 + 1)

    def values(self) -> dict[str, float]:
        return {key: control.value() for key, control in self.controls.items()}

    def set_values(self, values: dict) -> None:
        for key, control in self.controls.items():
            control.setValue(float(values.get(key, 0) or 0))


class InlineListSettings(QWidget):
    """Compact comma-separated editors for short engine string lists."""

    changed = Signal()

    def __init__(
        self,
        options: dict[str, str],
        parent: QWidget | None = None,
        columns: int = 2,
    ) -> None:
        super().__init__(parent)
        self.controls = {}
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(8)
        for index, (key, label) in enumerate(options.items()):
            row, column = divmod(index, columns)
            heading = QLabel(label, self)
            control = QLineEdit(self)
            control.setObjectName("dialogInput")
            control.setPlaceholderText("Comma-separated values")
            control.textChanged.connect(self.changed)
            self.controls[key] = control
            layout.addWidget(heading, row, column * 2)
            layout.addWidget(control, row, column * 2 + 1)

    def values(self) -> dict[str, list[str]]:
        return {
            key: [item.strip() for item in control.text().split(",") if item.strip()]
            for key, control in self.controls.items()
        }

    def set_values(self, values: dict) -> None:
        for key, control in self.controls.items():
            value = values.get(key)
            control.setText(", ".join(str(item) for item in value or []))


class RangeSettings(QWidget):
    """Reusable engine integer/range editors with inline validation."""

    changed = Signal()

    def __init__(self, options: dict[str, str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controls = {}
        self.labels = {}
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
            self.labels[key] = heading
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


class RangePairSettings(QWidget):
    """Two-field editor for one engine integer/range value."""

    changed = Signal()

    def __init__(
        self,
        minimum_label: str,
        maximum_label: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(8)
        self.minimum_label = QLabel(minimum_label, self)
        self.maximum_label = QLabel(maximum_label, self)
        self.minimum = WheelSafeSpinBox(self)
        self.maximum = WheelSafeSpinBox(self)
        for control in (self.minimum, self.maximum):
            control.setRange(0, 100000)
            control.valueChanged.connect(self.changed)
        layout.addWidget(self.minimum_label, 0, 0)
        layout.addWidget(self.minimum, 0, 1)
        layout.addWidget(self.maximum_label, 0, 2)
        layout.addWidget(self.maximum, 0, 3)

    def set_value(self, value: object) -> None:
        text = str(value or "0")
        parts = text.split("-", 1)
        try:
            minimum = int(parts[0])
            maximum = int(parts[-1])
        except ValueError:
            minimum = maximum = 0
        self.minimum.setValue(minimum)
        self.maximum.setValue(maximum)

    def value(self) -> str:
        minimum = self.minimum.value()
        maximum = self.maximum.value()
        if minimum > maximum:
            self.minimum.setFocus()
            raise ValueError("Minimum users to follow cannot exceed maximum users.")
        return str(minimum) if minimum == maximum else f"{minimum}-{maximum}"


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
