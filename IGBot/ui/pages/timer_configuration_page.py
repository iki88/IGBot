import re
from typing import ClassVar

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from IGBot.ui.widgets.configuration_widgets import CollapsibleSection, NumericSettings


class TimerConfigurationPage(QScrollArea):
    """Configuration-only account schedule editor."""

    changed = Signal()
    KEYS: ClassVar[dict[str, str]] = {
        "start": "start-hours",
        "end": "end-hours",
        "random_order": "random-action-order",
        "minimum_pause": "minimum-pause",
        "maximum_pause": "maximum-pause",
        "start_offset": "random-start-offset",
        "stop_offset": "random-stop-offset",
        "respect_limits": "respect-module-limits",
        "stop_at_limits": "stop-when-all-limits-reached",
        "warmup": "enable-warmup",
        "warmup_day": "current-warmup-day",
        "daily_increment": "daily-increment",
    }

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 14, 12, 14)
        layout.setSpacing(12)

        schedule = CollapsibleSection("Account Schedule", container)
        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(10)
        self.start_hours = QLineEdit(schedule)
        self.start_hours.setObjectName("dialogInput")
        self.start_hours.setPlaceholderText("8 or 8,16,20")
        self.end_hours = QLineEdit(schedule)
        self.end_hours.setObjectName("dialogInput")
        self.end_hours.setPlaceholderText("12 or 12,20,24")
        form.addRow("Start Hour", self.start_hours)
        form.addRow("End Hour", self.end_hours)
        schedule.body_layout.addLayout(form)
        layout.addWidget(schedule)

        randomization = CollapsibleSection("Randomization", container)
        self.random_action_order = self._switch("Random Action Order", randomization)
        randomization.body_layout.addWidget(self.random_action_order)
        self.randomization = NumericSettings(
            {
                self.KEYS["minimum_pause"]: "Minimum Pause",
                self.KEYS["maximum_pause"]: "Maximum Pause",
                self.KEYS["start_offset"]: "Random Start Offset",
                self.KEYS["stop_offset"]: "Random Stop Offset",
            },
            randomization,
        )
        randomization.body_layout.addWidget(self.randomization)
        layout.addWidget(randomization)

        daily = CollapsibleSection("Daily Behaviour", container)
        self.respect_limits = self._switch("Respect Module Limits", daily)
        self.stop_at_limits = self._switch("Stop When All Limits Reached", daily)
        daily.body_layout.addWidget(self.respect_limits)
        daily.body_layout.addWidget(self.stop_at_limits)
        layout.addWidget(daily)

        warmup = CollapsibleSection("Warmup", container)
        self.enable_warmup = self._switch("Enable Warmup", warmup)
        warmup.body_layout.addWidget(self.enable_warmup)
        self.warmup_values = NumericSettings(
            {
                self.KEYS["warmup_day"]: "Current Warmup Day",
                self.KEYS["daily_increment"]: "Daily Increment",
            },
            warmup,
        )
        warmup.body_layout.addWidget(self.warmup_values)
        layout.addWidget(warmup)
        layout.addStretch()
        self.setWidget(container)

        for editor in (self.start_hours, self.end_hours):
            editor.textChanged.connect(self._schedule_changed)
        for switch in (
            self.random_action_order,
            self.respect_limits,
            self.stop_at_limits,
            self.enable_warmup,
        ):
            switch.toggled.connect(self.changed)
        self.randomization.changed.connect(self.changed)
        self.warmup_values.changed.connect(self.changed)

    @staticmethod
    def _switch(label: str, parent: QWidget) -> QCheckBox:
        switch = QCheckBox(label, parent)
        switch.setObjectName("configurationSwitch")
        return switch

    def _schedule_changed(self) -> None:
        editor = self.sender()
        if isinstance(editor, QLineEdit):
            editor.setStyleSheet("")
        self.changed.emit()

    def set_configuration(self, configuration: dict) -> None:
        self.randomization.set_values({})
        self.respect_limits.setChecked(False)
        self.stop_at_limits.setChecked(False)
        self.enable_warmup.setChecked(False)
        self.warmup_values.set_values({})
        windows = configuration.get("working-hours") or []
        if isinstance(windows, str):
            windows = [windows]
        starts, ends = [], []
        for window in windows:
            parts = str(window).split("-", 1)
            if len(parts) == 2:
                starts.append(parts[0])
                ends.append(parts[1])
        self.start_hours.setText(",".join(starts))
        self.end_hours.setText(",".join(ends))
        self.random_action_order.setChecked(
            bool(configuration.get("shuffle-jobs", False))
        )

    @staticmethod
    def _valid_hours(value: str) -> bool:
        if not value:
            return True
        if not re.fullmatch(
            r"\s*\d{1,2}(?:\.\d{1,2})?\s*(?:,\s*\d{1,2}(?:\.\d{1,2})?\s*)*", value
        ):
            return False
        for part in value.split(","):
            hour, _, minute = part.strip().partition(".")
            if not 0 <= int(hour) <= 24 or (minute and not 0 <= int(minute) <= 59):
                return False
        return True

    def values(self) -> dict:
        invalid = []
        for editor in (self.start_hours, self.end_hours):
            valid = self._valid_hours(editor.text())
            editor.setStyleSheet("" if valid else "border: 1px solid #D9534F;")
            if not valid:
                invalid.append(editor)
        if invalid:
            invalid[0].setFocus()
            raise ValueError(
                "Start Hour and End Hour must be empty or contain hours from 0 to 24, separated by commas."
            )
        starts = [
            value.strip()
            for value in self.start_hours.text().split(",")
            if value.strip()
        ]
        ends = [
            value.strip() for value in self.end_hours.text().split(",") if value.strip()
        ]
        if len(starts) != len(ends):
            self.start_hours.setStyleSheet("border: 1px solid #D9534F;")
            self.end_hours.setStyleSheet("border: 1px solid #D9534F;")
            raise ValueError(
                "Start Hour and End Hour must contain the same number of values."
            )
        values = {
            "working-hours": [f"{start}-{end}" for start, end in zip(starts, ends)],
            "shuffle-jobs": self.random_action_order.isChecked(),
        }
        minimum_pause = self.randomization.controls[self.KEYS["minimum_pause"]]
        maximum_pause = self.randomization.controls[self.KEYS["maximum_pause"]]
        minimum_pause.setStyleSheet("")
        maximum_pause.setStyleSheet("")
        if minimum_pause.value() > maximum_pause.value():
            minimum_pause.setStyleSheet("border: 1px solid #D9534F;")
            maximum_pause.setStyleSheet("border: 1px solid #D9534F;")
            minimum_pause.setFocus()
            raise ValueError("Minimum Pause cannot exceed Maximum Pause.")
        return values
