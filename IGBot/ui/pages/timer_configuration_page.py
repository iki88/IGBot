import re

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFormLayout, QLineEdit, QScrollArea, QVBoxLayout, QWidget

from IGBot.ui.widgets.configuration_widgets import ConfigurationSection


class TimerConfigurationPage(QScrollArea):
    """Operator-facing editor for engine-compatible account working hours."""

    changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 14, 12, 14)
        layout.setSpacing(12)

        timer = ConfigurationSection("Timer", container)
        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(10)
        self.start_hours = self._time_editor("10 or 10:30,15:15,20", timer)
        self.end_hours = self._time_editor("12 or 12:30,17,23:30", timer)
        form.addRow("Start Time", self.start_hours)
        form.addRow("End Time", self.end_hours)
        timer.body_layout.addLayout(form)
        layout.addWidget(timer)
        layout.addStretch()
        self.setWidget(container)

        self.start_hours.textChanged.connect(self._schedule_changed)
        self.end_hours.textChanged.connect(self._schedule_changed)

    @staticmethod
    def _time_editor(placeholder: str, parent: QWidget) -> QLineEdit:
        editor = QLineEdit(parent)
        editor.setObjectName("dialogInput")
        editor.setPlaceholderText(placeholder)
        editor.setMaximumWidth(460)
        return editor

    def _schedule_changed(self) -> None:
        editor = self.sender()
        if isinstance(editor, QLineEdit):
            editor.setStyleSheet("")
        self.changed.emit()

    def set_configuration(self, configuration: dict) -> None:
        windows = configuration.get("working-hours") or []
        if isinstance(windows, str):
            windows = [windows]
        starts, ends = [], []
        for window in windows:
            parts = str(window).split("-", 1)
            if len(parts) != 2:
                continue
            try:
                starts.append(self._engine_to_operator(parts[0]))
                ends.append(self._engine_to_operator(parts[1]))
            except ValueError:
                continue
        self.start_hours.setText(",".join(starts))
        self.end_hours.setText(",".join(ends))

    @classmethod
    def values_from_text(cls, value: str) -> list[str]:
        if not value.strip():
            return []
        return [cls._operator_to_engine(part.strip()) for part in value.split(",")]

    @staticmethod
    def _parse_time(value: str, separator: str) -> tuple[int, int]:
        pattern = rf"\d{{1,2}}(?:{re.escape(separator)}\d{{1,2}})?"
        if not re.fullmatch(pattern, value):
            raise ValueError("Enter a valid time using hours or hours:minutes.")
        hour_text, found, minute_text = value.partition(separator)
        hour = int(hour_text)
        minute = int(minute_text) if found else 0
        if not 0 <= hour <= 24 or not 0 <= minute <= 59:
            raise ValueError("Hours must be 0–24 and minutes must be 0–59.")
        if hour == 24 and minute != 0:
            raise ValueError("24 is only valid as 24:00.")
        return hour, minute

    @classmethod
    def _operator_to_engine(cls, value: str) -> str:
        hour, minute = cls._parse_time(value, ":")
        return f"{hour:02d}.{minute:02d}"

    @classmethod
    def _engine_to_operator(cls, value: str) -> str:
        hour, minute = cls._parse_time(value.strip(), ".")
        return f"{hour}:{minute:02d}"

    def values(self) -> dict:
        try:
            starts = self.values_from_text(self.start_hours.text())
        except ValueError as error:
            self.start_hours.setStyleSheet("border: 1px solid #EF4444;")
            self.start_hours.setFocus()
            raise ValueError(f"Invalid Start Time: {error}") from error
        try:
            ends = self.values_from_text(self.end_hours.text())
        except ValueError as error:
            self.end_hours.setStyleSheet("border: 1px solid #EF4444;")
            self.end_hours.setFocus()
            raise ValueError(f"Invalid End Time: {error}") from error
        if len(starts) != len(ends):
            self.start_hours.setStyleSheet("border: 1px solid #EF4444;")
            self.end_hours.setStyleSheet("border: 1px solid #EF4444;")
            self.start_hours.setFocus()
            raise ValueError(
                "Start Time and End Time must contain the same number of sessions."
            )
        return {"working-hours": [f"{start}-{end}" for start, end in zip(starts, ends)]}
