import re
from pathlib import Path
from typing import ClassVar

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from IGBot.services.specific_lists_service import SpecificListsService
from IGBot.ui.widgets.configuration_widgets import (
    CheckboxGroup,
    CollapsibleSection,
    ConfigurationSection,
    NumericSettings,
    RangePairSettings,
    RangeSettings,
)
from IGBot.ui.widgets.target_editor_dialog import TargetEditorDialog
from IGBot.ui.widgets.target_source_row import TargetSourceRow


class UnfollowConfigurationPage(QScrollArea):
    """Operator-focused editor for the engine's Unfollow capabilities."""

    changed = Signal()
    RANGE_KEYS: ClassVar[dict[str, str]] = {
        "unfollow": "Only Users Followed by IGBot",
        "unfollow-non-followers": "Only Users Followed by IGBot Who Didn't Follow Back",
        "unfollow-any-non-followers": "Any Non-Follower",
        "unfollow-any-followers": "Any Follower",
        "unfollow-any": "Using Own Following List",
    }
    SEARCH_KEYS = ("unfollow", "unfollow-non-followers")
    BEHAVIOUR_LABELS: ClassVar[dict[str, str]] = {
        "unfollow": "Only Users Followed by IGBot",
        "unfollow-non-followers": "Only Users Followed by IGBot Who Didn't Follow Back",
    }
    METHOD_KEY = "igbot-unfollow-method"
    SORT_KEY = "igbot-unfollow-sort"
    ENABLED_KEY = "igbot-unfollow-enabled"
    BUDGET_KEY = "igbot-unfollow-budget"
    ACTION_DELAY_KEY = "igbot-unfollow-action-delay"
    WEEKDAYS = (
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    )
    SPECIFIC_RESOURCE = "unfollow_users.txt"
    REMOVE_RESOURCE = "remove_followers_users.txt"

    def __init__(self, parent=None, include_file_targets: bool = True) -> None:
        super().__init__(parent)
        self.include_file_targets = include_file_targets
        self._loading = False
        self._amount_edited = False
        self._present_keys: set[str] = set()
        self._edited_keys: set[str] = set()
        self._external_file_values: dict[str, object] = {}
        self._specific_lists: SpecificListsService | None = None
        self.setWidgetResizable(True)
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 14, 12, 14)
        layout.setSpacing(12)

        enable = ConfigurationSection("Enable Unfollow", container)
        enable_row = QHBoxLayout()
        self.enabled = QCheckBox("Enable Unfollow", enable)
        self.enabled.setObjectName("configurationSwitch")
        self.status = QLabel("● Disabled", enable)
        enable_row.addWidget(self.enabled)
        enable_row.addStretch()
        enable_row.addWidget(self.status)
        enable.body_layout.addLayout(enable_row)
        layout.addWidget(enable)

        method = ConfigurationSection("Unfollow Method", container)
        self.search_method = QCheckBox("Unfollow Using Search", method)
        self.search_method.setToolTip("Use usernames previously followed by IGBot.")
        self.following_list_search_method = QCheckBox(
            "Unfollow Using Following List Search", method
        )
        self.specific_users = TargetSourceRow(
            "Unfollow Specific Users", method, item_noun="username", switch_style=False
        )
        self.specific_users.setVisible(include_file_targets)
        self.all_followings_method = QCheckBox("Unfollow All Followings", method)
        self.method_group = QButtonGroup(self)
        self.method_group.setExclusive(True)
        for control in (
            self.search_method,
            self.following_list_search_method,
            self.specific_users.enabled,
            self.all_followings_method,
        ):
            self.method_group.addButton(control)

        self.all_followings_warning = QLabel(
            "⚠️ This method unfollows accounts directly from your Instagram Following "
            "list.\n\nIt does not use IGBot follow history and may unfollow accounts "
            "you followed manually.\n\nUse with caution.",
            method,
        )
        self.all_followings_warning.setWordWrap(True)
        self.all_followings_warning.setObjectName("warningText")

        self.sort_following_list = QWidget(method)
        sort_layout = QVBoxLayout(self.sort_following_list)
        sort_layout.setContentsMargins(24, 4, 0, 0)
        sort_layout.setSpacing(6)
        sort_layout.addWidget(QLabel("Sort Following List", self.sort_following_list))
        self.sort_default = QRadioButton(
            "Default (Recommended)", self.sort_following_list
        )
        self.sort_latest = QRadioButton(
            "Date Followed: Latest", self.sort_following_list
        )
        self.sort_earliest = QRadioButton(
            "Date Followed: Earliest", self.sort_following_list
        )
        self.sort_group = QButtonGroup(self)
        for control in (self.sort_default, self.sort_latest, self.sort_earliest):
            self.sort_group.addButton(control)
            sort_layout.addWidget(control)
        self.sort_default.setChecked(True)
        sort_note = QLabel(
            "Instagram may not always honor sorting correctly on accounts with large "
            "Following lists.\n\nDefault is recommended.",
            self.sort_following_list,
        )
        sort_note.setWordWrap(True)
        sort_layout.addWidget(sort_note)

        method.body_layout.addWidget(self.search_method)
        method.body_layout.addWidget(self.following_list_search_method)
        method.body_layout.addWidget(self.specific_users)
        method.body_layout.addWidget(self.all_followings_method)
        method.body_layout.addWidget(self.all_followings_warning)
        method.body_layout.addWidget(self.sort_following_list)
        layout.addWidget(method)

        actions = ConfigurationSection("Unfollow Actions", container)
        self.actions_section = actions
        action_fields = QWidget(actions)
        self.action_grid = QGridLayout(action_fields)
        self.action_grid.setContentsMargins(0, 0, 0, 0)
        self.action_grid.setHorizontalSpacing(12)
        self.action_grid.setVerticalSpacing(8)
        self.unfollow_amount = RangePairSettings(
            "Minimum users to unfollow", "Maximum users to unfollow", action_fields
        )
        self.unfollow_action_delay = RangePairSettings(
            "Minimum delay after unfollow (seconds)",
            "Maximum delay after unfollow (seconds)",
            action_fields,
        )
        self.limits = RangeSettings(
            {"total-unfollows-limit": "Unfollow Limit"}, action_fields
        )
        action_field_width = 180
        for control in (
            self.unfollow_amount.minimum,
            self.unfollow_amount.maximum,
            self.unfollow_action_delay.minimum,
            self.unfollow_action_delay.maximum,
            self.limits.controls["total-unfollows-limit"],
        ):
            control.setFixedWidth(action_field_width)
        self._place_range_pair(self.action_grid, 0, self.unfollow_amount)
        self._place_range_pair(self.action_grid, 1, self.unfollow_action_delay)
        self._place_single_field(
            self.action_grid, 2, self.limits, "total-unfollows-limit"
        )
        self.unfollow_limit_help = QLabel(
            "Daily hard limit.\n"
            "The bot will never exceed this number of unfollows per day.",
            actions,
        )
        self.unfollow_limit_help.setWordWrap(True)
        self.unfollow_limit_help.setObjectName("configurationHint")
        self.action_grid.addWidget(self.unfollow_limit_help, 3, 0, 1, 4)
        self.action_grid.setColumnStretch(4, 1)
        actions.body_layout.addWidget(action_fields)
        layout.addWidget(actions)

        timing = ConfigurationSection("Unfollow Timing", container)
        self.timing_section = timing
        timing_fields = QWidget(timing)
        self.timing_grid = QGridLayout(timing_fields)
        self.timing_grid.setContentsMargins(0, 0, 0, 0)
        self.timing_grid.setHorizontalSpacing(12)
        self.timing_grid.setVerticalSpacing(8)
        self.numeric = NumericSettings(
            {"unfollow-delay": "Unfollow Delay (days)"}, timing_fields, columns=1
        )
        self.numeric.controls["unfollow-delay"].setFixedWidth(action_field_width)
        self._place_single_field(self.timing_grid, 0, self.numeric, "unfollow-delay")
        self.timing_grid.setColumnStretch(2, 1)
        timing.body_layout.addWidget(timing_fields)
        self.unfollow_timing_message = QLabel(timing)
        self.unfollow_timing_message.setWordWrap(True)
        self.unfollow_timing_message.setObjectName("mutedText")
        timing.body_layout.addWidget(self.unfollow_timing_message)
        layout.addWidget(timing)

        additional = ConfigurationSection("Additional Unfollow Settings", container)
        self.additional_section = additional
        self.mode_options = CheckboxGroup(self.BEHAVIOUR_LABELS, additional, columns=1)
        self.behaviour = CheckboxGroup(
            {
                "sort-followers-newest-to-oldest": "Process newest followed users first",
                "delete-removed-followers": "Remove processed users from the removal list",
            },
            additional,
            columns=1,
        )
        additional.body_layout.addWidget(self.mode_options)
        self.remove_followers = TargetSourceRow(
            "Remove Followers From File",
            additional,
            item_noun="username",
            switch_style=False,
        )
        self.behaviour.hide()
        self.remove_followers.hide()
        layout.addWidget(additional)

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

        # Hidden compatibility editors retain exact legacy values until the operator
        # deliberately changes the shared action range.
        self.modes = RangeSettings(self.RANGE_KEYS, container)
        self.modes.hide()
        self.filters = NumericSettings(
            {"min-following": "Minimum Following"}, container, columns=1
        )
        self.filters.hide()
        self.files = self.specific_users
        self.files_section = self.specific_users

        self.enabled.toggled.connect(self._enabled_changed)
        self.search_method.toggled.connect(self._method_changed)
        self.following_list_search_method.toggled.connect(self._method_changed)
        self.specific_users.enabled.toggled.connect(self._method_changed)
        self.all_followings_method.toggled.connect(self._method_changed)
        self.unfollow_amount.changed.connect(self._amount_changed)
        self.unfollow_action_delay.changed.connect(self._runtime_extension_changed)
        for key, control in self.limits.controls.items():
            control.textChanged.connect(lambda _text, key=key: self._field_changed(key))
        for key, control in self.numeric.controls.items():
            control.valueChanged.connect(
                lambda _value, key=key: self._field_changed(key)
            )
        for key, control in self.mode_options.controls.items():
            control.toggled.connect(
                lambda checked, key=key: self._mode_option_changed(key, checked)
            )
        followed_by_igbot = self.mode_options.controls["unfollow"]
        did_not_follow_back = self.mode_options.controls["unfollow-non-followers"]
        followed_by_igbot.toggled.connect(
            lambda checked: self._enforce_exclusive_option(checked, did_not_follow_back)
        )
        did_not_follow_back.toggled.connect(
            lambda checked: self._enforce_exclusive_option(checked, followed_by_igbot)
        )
        for key, control in self.behaviour.controls.items():
            control.toggled.connect(lambda _checked, key=key: self._field_changed(key))
        for control in (self.sort_default, self.sort_latest, self.sort_earliest):
            control.toggled.connect(self._runtime_extension_changed)
        self.specific_users.changed.connect(
            lambda: self._field_changed("unfollow-from-file")
        )
        self.specific_users.edit_requested.connect(
            lambda: self._edit_resource(self.specific_users, "unfollow-from-file")
        )
        self.remove_followers.changed.connect(
            lambda: self._field_changed("remove-followers-from-file")
        )
        self.remove_followers.edit_requested.connect(
            lambda: self._edit_resource(
                self.remove_followers, "remove-followers-from-file"
            )
        )
        self.schedule_days.changed.connect(self._runtime_extension_changed)
        self._update_method_availability()

    @staticmethod
    def _place_range_pair(
        layout: QGridLayout, row: int, pair: RangePairSettings
    ) -> None:
        pair_layout = pair.layout()
        for column, widget in enumerate(
            (pair.minimum_label, pair.minimum, pair.maximum_label, pair.maximum)
        ):
            pair_layout.removeWidget(widget)
            layout.addWidget(widget, row, column)

    @staticmethod
    def _place_single_field(
        layout: QGridLayout,
        row: int,
        settings: RangeSettings | NumericSettings,
        key: str,
    ) -> None:
        settings_layout = settings.layout()
        label = settings.labels[key]
        control = settings.controls[key]
        settings_layout.removeWidget(label)
        settings_layout.removeWidget(control)
        layout.addWidget(label, row, 0)
        layout.addWidget(control, row, 1)

    def set_configuration(self, configuration: dict) -> None:
        engine_keys = set(self.RANGE_KEYS) | {
            "total-unfollows-limit",
            "min-following",
            "unfollow-delay",
            "sort-followers-newest-to-oldest",
            "delete-removed-followers",
            "unfollow-from-file",
            "remove-followers-from-file",
        }
        self._loading = True
        try:
            self._present_keys = engine_keys & set(configuration)
            self._edited_keys.clear()
            self._amount_edited = False
            self.modes.set_values(configuration)
            self.limits.set_values(configuration)
            self.numeric.set_values(configuration)
            self.filters.set_values(configuration)
            self.behaviour.set_values(configuration)
            self.mode_options.set_values(
                {key: self._mode_enabled(key) for key in self.BEHAVIOUR_LABELS}
            )
            self._set_sort_from_configuration(configuration)
            self.unfollow_amount.set_value(
                configuration.get(self.BUDGET_KEY) or self._first_mode_value()
            )
            self.unfollow_action_delay.set_value(
                configuration.get(self.ACTION_DELAY_KEY)
            )
            self._external_file_values = {
                key: configuration.get(key)
                for key, resource in (
                    ("unfollow-from-file", self.SPECIFIC_RESOURCE),
                    ("remove-followers-from-file", self.REMOVE_RESOURCE),
                )
                if configuration.get(key) not in (None, [resource])
            }
            self._set_resource_row(
                self.specific_users,
                configuration.get("unfollow-from-file"),
                (
                    "\n".join(self._specific_lists.load("unfollowspecific.txt"))
                    if self._specific_lists is not None
                    else configuration.get(self.SPECIFIC_RESOURCE)
                ),
            )
            self._set_resource_row(
                self.remove_followers,
                configuration.get("remove-followers-from-file"),
                configuration.get(self.REMOVE_RESOURCE),
            )
            self._set_method_from_configuration(configuration)
            self.enabled.setChecked(
                bool(configuration.get(self.ENABLED_KEY))
                if self.ENABLED_KEY in configuration
                else self._has_enabled_method()
            )
            self.schedule_days.set_values(
                {day.casefold(): True for day in self.WEEKDAYS}
            )
            self._update_status()
            self._update_method_availability()
        finally:
            self._loading = False

    def values(self) -> dict:
        values = {
            key: control.text().strip() for key, control in self.modes.controls.items()
        }
        implemented_value = values["unfollow"]
        if implemented_value:
            valid = bool(re.fullmatch(r"\d+(?:-\d+)?", implemented_value))
            if valid and "-" in implemented_value:
                minimum, maximum = (
                    int(part) for part in implemented_value.split("-", 1)
                )
                valid = minimum <= maximum
            if not valid:
                control = self.modes.controls["unfollow"]
                control.setStyleSheet("border: 1px solid #EF4444;")
                control.setFocus()
                raise ValueError("unfollow must be a number or ascending range.")
        if self._amount_edited:
            amount = self.unfollow_amount.value()
            for key in self.RANGE_KEYS:
                if self._mode_selected(key):
                    values[key] = amount
        values.update(self.limits.values())
        values.update(self.numeric.values())
        values.update(self.filters.values())
        values.update(self.behaviour.values())
        if self.include_file_targets:
            values.update(self._resource_values())
        result = {}
        for key, value in values.items():
            if key == "unfollow-delay":
                value = str(value)
            populated = (
                bool(value)
                if isinstance(value, (list, dict))
                else value not in {"", "0", 0, None}
            )
            if key in self._present_keys or key in self._edited_keys or populated:
                result[key] = value
        if not self.enabled.isChecked():
            for key in set(self.RANGE_KEYS) | {
                "unfollow-from-file",
                "remove-followers-from-file",
            }:
                if key in self._present_keys or key in self._edited_keys:
                    result[key] = None
        return result

    def _resource_values(self) -> dict:
        values = {}
        for key, resource, row in (
            ("unfollow-from-file", self.SPECIFIC_RESOURCE, self.specific_users),
            ("remove-followers-from-file", self.REMOVE_RESOURCE, self.remove_followers),
        ):
            entries = row.entries()
            if row.enabled.isChecked():
                if not entries:
                    row.name.setFocus()
                    raise ValueError(
                        f"Add at least one username for {row.name.text()}."
                    )
                values[key] = [resource]
                values[resource] = "\n".join(entries) + "\n"
            elif key in self._external_file_values and key not in self._edited_keys:
                values[key] = self._external_file_values[key]
            elif key in self._present_keys or key in self._edited_keys:
                values[key] = None
                values[resource] = ""
        return values

    @staticmethod
    def _set_resource_row(row, configured_files, content) -> None:
        entries = [
            line.strip() for line in str(content or "").splitlines() if line.strip()
        ]
        row.set_entries(entries)
        row.enabled.setChecked(bool(configured_files and entries))

    def _edit_resource(self, row: TargetSourceRow, key: str) -> None:
        validator = lambda entry: bool(re.fullmatch(r"[A-Za-z0-9._]{1,30}", entry))
        dialog = TargetEditorDialog(row.name.text(), row.entries(), validator, self)
        if dialog.exec() == TargetEditorDialog.Accepted:
            entries = dialog.entries()
            row.set_entries(entries)
            if row is self.specific_users and self._specific_lists is not None:
                self._specific_lists.save("unfollowspecific.txt", entries)
            row.enabled.setChecked(bool(entries))
            self._field_changed(key)

    def set_account_directory(self, directory: str | Path) -> None:
        account_directory = Path(directory)
        if not (account_directory / "config.yml").is_file():
            self._specific_lists = None
            return
        self._specific_lists = SpecificListsService(account_directory)
        self._specific_lists.initialize()

    def _enabled_changed(self, enabled: bool) -> None:
        if self._loading:
            return
        self._edited_keys.update(self.RANGE_KEYS)
        self._update_status()
        self.changed.emit()

    def _method_changed(self) -> None:
        if self._loading:
            return
        if not self._history_settings_available():
            for key, control in self.mode_options.controls.items():
                control.setChecked(False)
                self._set_mode_value(key, False)
        self._update_method_availability()
        self._notify_changed()

    def _mode_option_changed(self, key: str, checked: bool) -> None:
        if self._loading:
            return
        self._set_mode_value(key, checked)
        self._notify_changed()

    @staticmethod
    def _enforce_exclusive_option(checked: bool, opposite: QCheckBox) -> None:
        if checked:
            opposite.setChecked(False)

    def _set_mode_value(self, key: str, enabled: bool) -> None:
        control = self.modes.controls[key]
        if enabled and control.text().strip() in {"", "0"}:
            control.setText(self.unfollow_amount.value())
        elif not enabled:
            control.setText("")
        self._edited_keys.add(key)

    def _amount_changed(self) -> None:
        if not self._loading:
            self._amount_edited = True
            self.changed.emit()

    def _field_changed(self, key: str) -> None:
        if not self._loading:
            self._edited_keys.add(key)
            self._notify_changed()

    def _notify_changed(self) -> None:
        self._update_status()
        self.changed.emit()

    def _runtime_extension_changed(self) -> None:
        if not self._loading:
            self.changed.emit()

    def _mode_enabled(self, key: str) -> bool:
        return self.modes.controls[key].text().strip() not in {"", "0"}

    def _mode_selected(self, key: str) -> bool:
        control = self.mode_options.controls.get(key)
        return bool(control and control.isChecked())

    def _first_mode_value(self) -> str:
        for control in self.modes.controls.values():
            if control.text().strip() not in {"", "0"}:
                return control.text()
        return "1"

    def _has_enabled_method(self) -> bool:
        return any(button.isChecked() for button in self.method_group.buttons())

    def runtime_extension_values(self) -> dict[str, object]:
        return {
            self.ENABLED_KEY: self.enabled.isChecked(),
            self.METHOD_KEY: self._selected_method(),
            self.SORT_KEY: self._selected_sort(),
            self.BUDGET_KEY: self.unfollow_amount.value(),
            self.ACTION_DELAY_KEY: self.unfollow_action_delay.value(),
        }

    def _selected_method(self) -> str:
        for value, control in (
            ("search", self.search_method),
            ("following-list-search", self.following_list_search_method),
            ("specific-users", self.specific_users.enabled),
            ("all-followings", self.all_followings_method),
        ):
            if control.isChecked():
                return value
        return ""

    def _set_method_from_configuration(self, configuration: dict) -> None:
        method = str(configuration.get(self.METHOD_KEY) or "")
        if not method:
            if self.specific_users.enabled.isChecked():
                method = "specific-users"
            elif self._mode_enabled("unfollow-any"):
                method = "all-followings"
            elif any(self._mode_enabled(key) for key in self.SEARCH_KEYS):
                method = "search"
        controls = {
            "search": self.search_method,
            "following-list-search": self.following_list_search_method,
            "specific-users": self.specific_users.enabled,
            "all-followings": self.all_followings_method,
        }
        self.method_group.setExclusive(False)
        for control in controls.values():
            control.setChecked(False)
        self.method_group.setExclusive(True)
        if method in controls:
            controls[method].setChecked(True)

    def _selected_sort(self) -> str:
        if self.sort_latest.isChecked():
            return "latest"
        if self.sort_earliest.isChecked():
            return "earliest"
        return "default"

    def _set_sort_from_configuration(self, configuration: dict) -> None:
        {
            "latest": self.sort_latest,
            "earliest": self.sort_earliest,
        }.get(
            str(configuration.get(self.SORT_KEY) or ""), self.sort_default
        ).setChecked(True)

    def _history_settings_available(self) -> bool:
        return (
            self.search_method.isChecked()
            or self.following_list_search_method.isChecked()
        )

    def _update_method_availability(self) -> None:
        available = self._history_settings_available()
        for control in self.mode_options.controls.values():
            control.setEnabled(available)
        show_all_followings = self.all_followings_method.isChecked()
        self.all_followings_warning.setVisible(show_all_followings)
        self.sort_following_list.setVisible(show_all_followings)
        delay_available = available
        self.numeric.labels["unfollow-delay"].setEnabled(delay_available)
        self.numeric.controls["unfollow-delay"].setEnabled(delay_available)
        if self.specific_users.enabled.isChecked():
            self.unfollow_timing_message.setText(
                "Unfollow Delay does not apply to this method.\n"
                "Specific Users are processed immediately."
            )
            self.unfollow_timing_message.show()
        elif show_all_followings:
            self.unfollow_timing_message.setText(
                "Unfollow Delay does not apply to this method.\n"
                "This provider walks your Instagram Following list directly."
            )
            self.unfollow_timing_message.show()
        else:
            self.unfollow_timing_message.clear()
            self.unfollow_timing_message.hide()

    def _update_status(self) -> None:
        enabled = self.enabled.isChecked()
        self.status.setText("● Enabled" if enabled else "● Disabled")
        self.status.setStyleSheet(f"color: {'#22C55E' if enabled else '#A1A1AA'}")
