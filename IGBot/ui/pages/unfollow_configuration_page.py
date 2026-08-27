from typing import ClassVar

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from IGBot.ui.widgets.configuration_widgets import (
    CheckboxGroup,
    ConfigurationSection,
    NumericSettings,
    RangeSettings,
    TextListSettings,
)


class UnfollowConfigurationPage(QScrollArea):
    """Configuration-only interface for documented engine unfollow settings."""

    changed = Signal()
    RANGE_KEYS: ClassVar[dict[str, str]] = {
        "unfollow": "Bot-followed users",
        "unfollow-non-followers": "Bot-followed non-followers",
        "unfollow-any-non-followers": "Any non-followers",
        "unfollow-any-followers": "Any followers",
        "unfollow-any": "Any account",
    }

    def __init__(self, parent=None, include_file_targets: bool = True) -> None:
        super().__init__(parent)
        self.include_file_targets = include_file_targets
        self._present_keys: set[str] = set()
        self.setWidgetResizable(True)
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 14, 12, 14)
        layout.setSpacing(12)

        overview = ConfigurationSection("Enable / Disable", container)
        row = QHBoxLayout()
        heading = QLabel("Engine configuration status", overview)
        self.status = QLabel("● Disabled", overview)
        row.addWidget(heading)
        row.addStretch()
        row.addWidget(self.status)
        overview.body_layout.addLayout(row)
        layout.addWidget(overview)

        self.modes = RangeSettings(self.RANGE_KEYS, container)
        self.files = TextListSettings(
            {
                "unfollow-from-file": "Unfollow from Files",
                "remove-followers-from-file": "Remove Followers from Files",
            },
            container,
        )
        method = ConfigurationSection("Method", container)
        method.body_layout.addWidget(self.modes)
        method.body_layout.addWidget(self.files)
        self.files_section = self.files
        self.files.setVisible(include_file_targets)
        layout.addWidget(method)

        self.limits = RangeSettings(
            {"total-unfollows-limit": "Total Unfollows Limit"}, container
        )
        self.numeric = NumericSettings(
            {
                "min-following": "Minimum Following",
                "unfollow-delay": "Unfollow Delay (days)",
            },
            container,
        )
        limits = ConfigurationSection("Settings", container)
        limits.body_layout.addWidget(self.limits)
        limits.body_layout.addWidget(self.numeric)
        layout.addWidget(limits)

        self.behaviour = CheckboxGroup(
            {
                "sort-followers-newest-to-oldest": "Sort Followers Newest to Oldest",
                "delete-removed-followers": "Delete Removed Followers from File",
            },
            container,
        )
        self._add_section(layout, "Additional Settings", self.behaviour, container)
        layout.addStretch()
        self.setWidget(container)

        for widget in (
            self.modes,
            self.limits,
            self.numeric,
            self.behaviour,
            self.files,
        ):
            widget.changed.connect(self._changed)

    @staticmethod
    def _add_section(layout, title, widget, parent) -> None:
        section = ConfigurationSection(title, parent)
        section.body_layout.addWidget(widget)
        layout.addWidget(section)
        return section

    def set_configuration(self, configuration: dict) -> None:
        keys = set(self.RANGE_KEYS) | {
            "total-unfollows-limit",
            "min-following",
            "unfollow-delay",
            "sort-followers-newest-to-oldest",
            "delete-removed-followers",
            "unfollow-from-file",
            "remove-followers-from-file",
        }
        self._present_keys = keys & set(configuration)
        self.modes.set_values(configuration)
        self.limits.set_values(configuration)
        self.numeric.set_values(configuration)
        self.behaviour.set_values(configuration)
        self.files.set_values(configuration)
        self._update_status()

    def values(self) -> dict:
        values = self.modes.values()
        values.update(self.limits.values())
        values.update(self.numeric.values())
        values.update(self.behaviour.values())
        if self.include_file_targets:
            values.update(self.files.values())
        result = {}
        numeric_keys = set(self.numeric.controls)
        for key, value in values.items():
            if key in numeric_keys and key == "unfollow-delay":
                value = str(value)
            populated = (
                bool(value) if isinstance(value, list) else value not in {"", "0", 0}
            )
            if (key in self._present_keys or populated) and (
                not isinstance(value, list) or value
            ):
                result[key] = value
        return result

    def _changed(self) -> None:
        self._update_status()
        self.changed.emit()

    def _update_status(self) -> None:
        enabled = any(
            control.text().strip() not in {"", "0"}
            for control in self.modes.controls.values()
        )
        enabled = enabled or any(
            control.toPlainText().strip() for control in self.files.controls.values()
        )
        self.status.setText("● Enabled" if enabled else "● Disabled")
        self.status.setStyleSheet(f"color: {'#22C55E' if enabled else '#A1A1AA'}")
