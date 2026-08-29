from typing import ClassVar

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from IGBot.ui.pages.audience_sources_page import AudienceSourcesPage
from IGBot.ui.widgets.configuration_widgets import (
    CheckboxGroup,
    CollapsibleSection,
    ConfigurationSection,
    NumericSettings,
    RangePairSettings,
    RangeSettings,
    TextResourceEditor,
)
from IGBot.ui.widgets.dm_message_editor_dialog import DMMessageEditorDialog


class DMConfigurationPage(QScrollArea):
    """Operator-focused editor for engine-compatible Direct Message settings."""

    changed = Signal()
    CONFIG_RANGE_KEYS: ClassVar[dict[str, str]] = {
        "pm-percentage": "Direct Message Percentage",
        "total-pm-limit": "Daily DM Limit",
    }
    CONFIG_BOOLEAN_KEYS: ClassVar[dict[str, str]] = {
        "end-if-pm-limit-reached": "End Session when DM Limit is Reached",
    }
    FILTER_KEYS: ClassVar[dict[str, str]] = {
        "pm_to_private_or_empty": "Message Private or Empty Profiles",
    }
    MESSAGE_RESOURCE = "pm_list.txt"
    WEEKDAYS = (
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    )

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

        enable = ConfigurationSection("Enable DM", container)
        enable_row = QHBoxLayout()
        self.enabled = QCheckBox("Enable DM", enable)
        self.enabled.setObjectName("configurationSwitch")
        self.status = QLabel("● Disabled", enable)
        enable_row.addWidget(self.enabled)
        enable_row.addStretch()
        enable_row.addWidget(self.status)
        enable.body_layout.addLayout(enable_row)
        layout.addWidget(enable)

        self.sources = AudienceSourcesPage(
            container, include_advanced=False, section_title="DM Method"
        )
        self.sources.setVisible(include_sources)
        self.sources.rows["blogger-followers"].hide()
        self.sources.rows["blogger-following"].hide()
        self.specific_accounts = self.sources.rows["blogger"]
        self.specific_accounts.name.setText("Send DMs to Specific Accounts")
        self.specific_accounts.enabled.setObjectName("")
        self.specific_accounts.name.setObjectName("checkboxLinkButton")
        method = self.sources.findChild(ConfigurationSection)
        self.new_followers = QCheckBox("Send DMs to New Followers", method)
        self.new_followers.setChecked(True)
        method.body_layout.insertWidget(0, self.new_followers)
        layout.addWidget(self.sources)

        self.messages_section = ConfigurationSection("Message", container)
        message_actions = QHBoxLayout()
        self.edit_messages_button = QPushButton(
            "Edit DM Message", self.messages_section
        )
        self.edit_messages_button.setObjectName("secondaryButton")
        self.edit_ai_prompt_button = QPushButton(
            "Edit AI Prompt", self.messages_section
        )
        self.edit_ai_prompt_button.setObjectName("secondaryButton")
        self.edit_ai_prompt_button.setEnabled(False)
        self.edit_ai_prompt_button.setToolTip("Coming in a future IGBot version")
        message_actions.addWidget(self.edit_messages_button)
        message_actions.addWidget(self.edit_ai_prompt_button)
        message_actions.addStretch()
        self.messages_section.body_layout.addLayout(message_actions)
        self.messages_section.setVisible(include_messages)
        layout.addWidget(self.messages_section)
        self.messages = TextResourceEditor(
            "DM Message",
            "Write one message. Engine spintax, emoji, and multiline text are supported.",
            container,
        )
        self.messages.hide()

        actions = ConfigurationSection("DM Actions", container)
        action_fields = QWidget(actions)
        self.action_grid = QGridLayout(action_fields)
        self.action_grid.setContentsMargins(0, 0, 0, 0)
        self.action_grid.setHorizontalSpacing(12)
        self.action_grid.setVerticalSpacing(8)
        self.message_amount = RangePairSettings(
            "Minimum users to message", "Maximum users to message", action_fields
        )
        self.delay = RangePairSettings(
            "Minimum delay after sending DM",
            "Maximum delay after sending DM",
            action_fields,
        )
        self.check_interval = NumericSettings(
            {"check-new-followers-every": "Check for New Followers Every (minutes)"},
            action_fields,
            columns=1,
        )
        self.delivery = RangeSettings(self.CONFIG_RANGE_KEYS, action_fields)
        width = 180
        for control in (
            self.message_amount.minimum,
            self.message_amount.maximum,
            self.delay.minimum,
            self.delay.maximum,
            self.check_interval.controls["check-new-followers-every"],
            self.delivery.controls["total-pm-limit"],
        ):
            control.setFixedWidth(width)
        self._place_pair(self.action_grid, 0, self.message_amount)
        self._place_pair(self.action_grid, 1, self.delay)
        self._place_field(self.action_grid, 2, self.delivery, "total-pm-limit")
        self._place_field(
            self.action_grid,
            3,
            self.check_interval,
            "check-new-followers-every",
        )
        self.delivery.labels["pm-percentage"].hide()
        self.delivery.controls["pm-percentage"].hide()
        self.action_grid.setColumnStretch(4, 1)
        actions.body_layout.addWidget(action_fields)
        layout.addWidget(actions)

        additional = ConfigurationSection("Additional Settings", container)
        self.dm_all_new_followers = QCheckBox("DM All New Followers", additional)
        self.dm_all_new_followers.setToolTip(
            "Includes followers gained outside IGBot interactions"
        )
        self.dm_all_new_followers_description = QLabel(
            "Includes followers gained outside IGBot interactions.", additional
        )
        self.dm_all_new_followers_description.setObjectName("mutedLabel")
        self.reply_to_incoming = QCheckBox("Reply to Incoming DM Messages", additional)
        additional.body_layout.addWidget(self.dm_all_new_followers)
        additional.body_layout.addWidget(self.dm_all_new_followers_description)
        additional.body_layout.addWidget(self.reply_to_incoming)
        layout.addWidget(additional)

        # Preserve existing engine values without exposing behavior that does not
        # match the product workflow. These controls are compatibility-only.
        self.recipients = CheckboxGroup(self.FILTER_KEYS, additional, columns=1)
        self.recipients.hide()
        self.limit_behaviour = CheckboxGroup(
            self.CONFIG_BOOLEAN_KEYS, container, columns=1
        )
        self.limit_behaviour.hide()

        self.schedule_section = CollapsibleSection(
            "Schedule", container, collapsible=True, collapsed=True
        )
        self.schedule_days = CheckboxGroup(
            {day.casefold(): day for day in self.WEEKDAYS},
            self.schedule_section,
            columns=1,
        )
        self.schedule_days.set_values({day.casefold(): True for day in self.WEEKDAYS})
        self.schedule_section.body_layout.addWidget(self.schedule_days)
        layout.addWidget(self.schedule_section)
        layout.addStretch()
        self.setWidget(container)

        self.enabled.toggled.connect(self._enabled_changed)
        self.delivery.changed.connect(self._delivery_changed)
        self.limit_behaviour.changed.connect(self._changed)
        self.recipients.changed.connect(self._changed)
        self.messages.changed.connect(self._changed)
        self.sources.changed.connect(self._changed)
        self.new_followers.toggled.connect(self._new_followers_changed)
        self.message_amount.changed.connect(self._runtime_extension_changed)
        self.delay.changed.connect(self._runtime_extension_changed)
        self.check_interval.changed.connect(self._runtime_extension_changed)
        self.dm_all_new_followers.toggled.connect(self._runtime_extension_changed)
        self.reply_to_incoming.toggled.connect(self._runtime_extension_changed)
        self.schedule_days.changed.connect(self._runtime_extension_changed)
        self.edit_messages_button.clicked.connect(self._edit_messages)
        self._update_new_follower_interval()

    @staticmethod
    def _place_pair(layout: QGridLayout, row: int, pair: RangePairSettings) -> None:
        source = pair.layout()
        for column, widget in enumerate(
            (pair.minimum_label, pair.minimum, pair.maximum_label, pair.maximum)
        ):
            source.removeWidget(widget)
            layout.addWidget(widget, row, column)

    @staticmethod
    def _place_field(
        layout: QGridLayout,
        row: int,
        settings: NumericSettings | RangeSettings,
        key: str,
    ) -> None:
        source = settings.layout()
        label = settings.labels[key]
        control = settings.controls[key]
        source.removeWidget(label)
        source.removeWidget(control)
        layout.addWidget(label, row, 0)
        layout.addWidget(control, row, 1)

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
            self.new_followers.setChecked(True)
            self.message_amount.set_value(None)
            self.delay.set_value(None)
            self.check_interval.set_values({"check-new-followers-every": 60})
            self.dm_all_new_followers.setChecked(False)
            self.reply_to_incoming.setChecked(False)
            self.schedule_days.set_values(
                {day.casefold(): True for day in self.WEEKDAYS}
            )
            percentage = self.delivery.controls["pm-percentage"].text().strip()
            if percentage not in {"", "0"}:
                self._enabled_percentage = percentage
            self.enabled.setChecked(percentage not in {"", "0"})
            self._update_status()
            self._update_message_button()
            self._update_new_follower_interval()
        finally:
            self._syncing_enabled = False

    def values(self) -> dict:
        self._validate_runtime_pair(self.message_amount, "users to message")
        self._validate_runtime_pair(self.delay, "delay after sending DM")
        values = self.delivery.values()
        values.update(self.limit_behaviour.values())
        values.update(self.recipients.values())
        percentage = str(values.get("pm-percentage") or "")
        if percentage and max(int(part) for part in percentage.split("-")) > 100:
            raise ValueError("Direct Message Percentage cannot exceed 100.")
        messages = self.messages.text()
        if self.include_messages and self.enabled.isChecked() and not messages.strip():
            self.edit_messages_button.setStyleSheet("border: 1px solid #EF4444;")
            self.edit_messages_button.setFocus()
            raise ValueError("Add at least one direct message before enabling DM.")
        self.edit_messages_button.setStyleSheet("")

        result = {}
        for key, value in values.items():
            populated = value not in {"", "0", 0}
            if key in self._present_keys or populated:
                result[key] = value
        if self.include_messages and (self._message_file_present or messages):
            result[self.MESSAGE_RESOURCE] = messages
        return result

    def _edit_messages(self) -> None:
        dialog = DMMessageEditorDialog(self._message_for_editor(), self)
        if dialog.exec() == DMMessageEditorDialog.Accepted:
            self.messages.set_text(self._message_for_engine(dialog.message()))
            self._update_message_button()

    def _message_for_editor(self) -> str:
        return self.messages.text().replace("\\n", "\n")

    @staticmethod
    def _message_for_engine(message: str) -> str:
        normalized = message.replace("\r\n", "\n").replace("\r", "\n")
        return normalized.replace("\n", "\\n")

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

    def _runtime_extension_changed(self) -> None:
        if not self._syncing_enabled:
            self.changed.emit()

    def _new_followers_changed(self, _enabled: bool) -> None:
        self._update_new_follower_interval()
        self._runtime_extension_changed()

    def _update_new_follower_interval(self) -> None:
        self.check_interval.setEnabled(self.new_followers.isChecked())

    @staticmethod
    def _validate_runtime_pair(pair: RangePairSettings, label: str) -> None:
        if pair.minimum.value() > pair.maximum.value():
            pair.minimum.setFocus()
            raise ValueError(f"Minimum {label} cannot exceed maximum {label}.")

    def _changed(self) -> None:
        if self._syncing_enabled:
            return
        self._update_status()
        self._update_message_button()
        self.changed.emit()

    def _update_message_button(self) -> None:
        configured = bool(self.messages.text().strip())
        self.edit_messages_button.setToolTip(
            "DM message configured" if configured else "No DM message configured"
        )

    def _update_status(self) -> None:
        enabled = self.enabled.isChecked()
        self.status.setText("● Enabled" if enabled else "● Disabled")
        self.status.setStyleSheet(f"color: {'#22C55E' if enabled else '#A1A1AA'}")
