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
    TextResourceEditor,
)


class DMConfigurationPage(QScrollArea):
    """Configuration editor for the engine's Direct Message settings."""

    changed = Signal()
    CONFIG_RANGE_KEYS: ClassVar[dict[str, str]] = {
        "pm-percentage": "Direct Message Percentage",
        "total-pm-limit": "Total Direct Message Limit",
    }
    CONFIG_BOOLEAN_KEYS: ClassVar[dict[str, str]] = {
        "end-if-pm-limit-reached": "End Session when DM Limit is Reached",
    }
    FILTER_KEYS: ClassVar[dict[str, str]] = {
        "pm_to_private_or_empty": "Message Private or Empty Profiles",
    }
    MESSAGE_RESOURCE = "pm_list.txt"

    def __init__(
        self, parent=None, include_messages: bool = True, include_sources: bool = True
    ) -> None:
        super().__init__(parent)
        self.include_messages = include_messages
        self._present_keys: set[str] = set()
        self._message_file_present = False
        self._syncing_enabled = False
        self._enabled_percentage = "1"
        self.setWidgetResizable(True)
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 14, 12, 14)
        layout.setSpacing(12)

        overview = ConfigurationSection("Enable / Disable", container)
        row = QHBoxLayout()
        self.enabled = QCheckBox("Enable Direct Messages", overview)
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

        self.delivery = RangeSettings(self.CONFIG_RANGE_KEYS, container)
        self._add_section(layout, "Settings", self.delivery, container)

        self.limit_behaviour = CheckboxGroup(self.CONFIG_BOOLEAN_KEYS, container)
        self.messages = TextResourceEditor(
            "Message List",
            "Enter one message per line. Engine spintax and emoji are supported.",
            container,
        )
        additional = ConfigurationSection("Additional Settings", container)
        additional.body_layout.addWidget(self.limit_behaviour)
        additional.body_layout.addWidget(self.messages)
        self.messages_section = self.messages
        self.messages.setVisible(include_messages)
        layout.addWidget(additional)

        self.recipients = CheckboxGroup(self.FILTER_KEYS, container)
        self._add_section(layout, "Filters", self.recipients, container)
        layout.addStretch()
        self.setWidget(container)

        self.enabled.toggled.connect(self._enabled_changed)
        self.delivery.changed.connect(self._delivery_changed)
        self.limit_behaviour.changed.connect(self._changed)
        self.recipients.changed.connect(self._changed)
        self.messages.changed.connect(self._changed)
        self.sources.changed.connect(self._changed)

    @staticmethod
    def _add_section(layout, title, widget, parent) -> None:
        section = ConfigurationSection(title, parent)
        section.body_layout.addWidget(widget)
        layout.addWidget(section)
        return section

    @classmethod
    def supported_keys(cls) -> set[str]:
        return (
            set(cls.CONFIG_RANGE_KEYS)
            | set(cls.CONFIG_BOOLEAN_KEYS)
            | set(cls.FILTER_KEYS)
            | {cls.MESSAGE_RESOURCE}
        )

    def set_configuration(self, configuration: dict) -> None:
        self._syncing_enabled = True
        try:
            self._present_keys = self.supported_keys() & set(configuration)
            self._message_file_present = self.MESSAGE_RESOURCE in configuration
            self.delivery.set_values(configuration)
            self.limit_behaviour.set_values(configuration)
            self.recipients.set_values(configuration)
            self.messages.set_text(str(configuration.get(self.MESSAGE_RESOURCE) or ""))
            self.sources.set_configuration(configuration)
            percentage = self.delivery.controls["pm-percentage"].text().strip()
            if percentage not in {"", "0"}:
                self._enabled_percentage = percentage
            self.enabled.setChecked(percentage not in {"", "0"})
            self._update_status()
        finally:
            self._syncing_enabled = False

    def values(self) -> dict:
        values = self.delivery.values()
        values.update(self.limit_behaviour.values())
        values.update(self.recipients.values())
        percentage = str(values.get("pm-percentage") or "")
        if percentage and max(int(part) for part in percentage.split("-")) > 100:
            control = self.delivery.controls["pm-percentage"]
            control.setStyleSheet("border: 1px solid #EF4444;")
            control.setFocus()
            raise ValueError("Direct Message Percentage cannot exceed 100.")
        messages = self.messages.text()
        if self.include_messages and self.enabled.isChecked() and not messages.strip():
            self.messages.editor.setStyleSheet("border: 1px solid #EF4444;")
            self.messages.editor.setFocus()
            raise ValueError("Add at least one direct message before enabling DM.")
        self.messages.editor.setStyleSheet("")

        result = {}
        for key, value in values.items():
            populated = value not in {"", "0", 0}
            if key in self._present_keys or populated:
                result[key] = value
        if self.include_messages and (self._message_file_present or messages):
            result[self.MESSAGE_RESOURCE] = messages
        return result

    def _enabled_changed(self, enabled: bool) -> None:
        if self._syncing_enabled:
            return
        percentage = self.delivery.controls["pm-percentage"]
        self._syncing_enabled = True
        try:
            if enabled:
                if percentage.text().strip() in {"", "0"}:
                    percentage.setText(self._enabled_percentage)
            else:
                if percentage.text().strip() not in {"", "0"}:
                    self._enabled_percentage = percentage.text().strip()
                percentage.setText("0")
        finally:
            self._syncing_enabled = False
        self._changed()

    def _delivery_changed(self) -> None:
        if self._syncing_enabled:
            return
        percentage = self.delivery.controls["pm-percentage"].text().strip()
        self._syncing_enabled = True
        try:
            self.enabled.setChecked(percentage not in {"", "0"})
            if percentage not in {"", "0"}:
                self._enabled_percentage = percentage
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
