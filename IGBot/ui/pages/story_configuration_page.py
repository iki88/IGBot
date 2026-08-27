from typing import ClassVar

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from IGBot.ui.pages.audience_sources_page import AudienceSourcesPage
from IGBot.ui.widgets.configuration_widgets import (
    CheckboxGroup,
    ConfigurationSection,
    RangeSettings,
)


class StoryConfigurationPage(QScrollArea):
    """Configuration-only interface for documented engine Story settings."""

    changed = Signal()
    SESSION_KEYS: ClassVar[dict[str, str]] = {
        "stories-count": "Stories per Profile",
        "stories-percentage": "Story Percentage",
    }
    LIMIT_KEYS: ClassVar[dict[str, str]] = {
        "total-watches-limit": "Total Story Watches Limit",
    }
    BEHAVIOUR_KEYS: ClassVar[dict[str, str]] = {
        "end-if-watches-limit-reached": "End Session when Watch Limit is Reached",
    }

    def __init__(self, parent=None, include_sources: bool = True) -> None:
        super().__init__(parent)
        self._present_keys: set[str] = set()
        self._syncing_enabled = False
        self._enabled_count = "1"
        self.setWidgetResizable(True)
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 14, 12, 14)
        layout.setSpacing(12)

        overview = ConfigurationSection("Enable / Disable", container)
        row = QHBoxLayout()
        self.enabled = QCheckBox("Enable Story", overview)
        self.enabled.setObjectName("configurationSwitch")
        self.status = QLabel("● Disabled", overview)
        row.addWidget(self.enabled)
        row.addStretch()
        row.addWidget(self.status)
        overview.body_layout.addLayout(row)
        layout.addWidget(overview)

        self.sources = AudienceSourcesPage(container)
        self.sources.setVisible(include_sources)
        layout.addWidget(self.sources)

        self.session = RangeSettings(self.SESSION_KEYS, container)
        self.limits = RangeSettings(self.LIMIT_KEYS, container)
        settings = ConfigurationSection("Settings", container)
        settings.body_layout.addWidget(self.session)
        settings.body_layout.addWidget(self.limits)
        layout.addWidget(settings)

        self.limit_behaviour = CheckboxGroup(self.BEHAVIOUR_KEYS, container)
        self._add_section(
            layout, "Additional Settings", self.limit_behaviour, container
        )
        layout.addStretch()
        self.setWidget(container)

        self.enabled.toggled.connect(self._enabled_changed)
        self.session.changed.connect(self._session_changed)
        self.limits.changed.connect(self._changed)
        self.limit_behaviour.changed.connect(self._changed)
        self.sources.changed.connect(self._changed)

    @staticmethod
    def _add_section(layout, title, widget, parent) -> None:
        section = ConfigurationSection(title, parent)
        section.body_layout.addWidget(widget)
        layout.addWidget(section)

    @classmethod
    def supported_keys(cls) -> set[str]:
        return set(cls.SESSION_KEYS) | set(cls.LIMIT_KEYS) | set(cls.BEHAVIOUR_KEYS)

    def set_configuration(self, configuration: dict) -> None:
        self._syncing_enabled = True
        try:
            self._present_keys = self.supported_keys() & set(configuration)
            self.session.set_values(configuration)
            self.limits.set_values(configuration)
            self.limit_behaviour.set_values(configuration)
            self.sources.set_configuration(configuration)
            count = self.session.controls["stories-count"].text().strip()
            if count not in {"", "0"}:
                self._enabled_count = count
            self.enabled.setChecked(count not in {"", "0"})
            self._update_status()
        finally:
            self._syncing_enabled = False

    def values(self) -> dict:
        values = self.session.values()
        values.update(self.limits.values())
        values.update(self.limit_behaviour.values())
        percentage = str(values.get("stories-percentage") or "")
        if percentage and max(int(part) for part in percentage.split("-")) > 100:
            control = self.session.controls["stories-percentage"]
            control.setStyleSheet("border: 1px solid #EF4444;")
            control.setFocus()
            raise ValueError("Story Percentage cannot exceed 100.")
        result = {}
        for key, value in values.items():
            populated = value not in {"", "0", 0}
            if key in self._present_keys or populated:
                result[key] = value
        return result

    def _enabled_changed(self, enabled: bool) -> None:
        if self._syncing_enabled:
            return
        count = self.session.controls["stories-count"]
        self._syncing_enabled = True
        try:
            if enabled:
                if count.text().strip() in {"", "0"}:
                    count.setText(self._enabled_count)
            else:
                if count.text().strip() not in {"", "0"}:
                    self._enabled_count = count.text().strip()
                count.setText("0")
        finally:
            self._syncing_enabled = False
        self._changed()

    def _session_changed(self) -> None:
        if self._syncing_enabled:
            return
        count = self.session.controls["stories-count"].text().strip()
        self._syncing_enabled = True
        try:
            self.enabled.setChecked(count not in {"", "0"})
            if count not in {"", "0"}:
                self._enabled_count = count
        finally:
            self._syncing_enabled = False
        self._changed()

    def _changed(self) -> None:
        self._update_status()
        self.changed.emit()

    def _update_status(self) -> None:
        enabled = self.enabled.isChecked()
        self.status.setText("● Enabled" if enabled else "● Disabled")
        self.status.setStyleSheet(f"color: {'#22C55E' if enabled else '#A1A1AA'}")
