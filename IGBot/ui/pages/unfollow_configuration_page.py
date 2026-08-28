import re
from typing import ClassVar

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

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
    SEARCH_KEYS = tuple(key for key in RANGE_KEYS if key != "unfollow-any")
    BEHAVIOUR_LABELS: ClassVar[dict[str, str]] = {
        "unfollow": "Only Users Followed by IGBot",
        "unfollow-non-followers": "Only Users Followed by IGBot Who Didn't Follow Back",
        "unfollow-any-non-followers": "Any Non-Follower",
        "unfollow-any-followers": "Any Follower",
    }
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
        self.own_following_method = QCheckBox(
            "Unfollow Using Own Following List", method
        )
        self.specific_users = TargetSourceRow(
            "Unfollow Specific Users", method, item_noun="username", switch_style=False
        )
        self.specific_users.setVisible(include_file_targets)
        method.body_layout.addWidget(self.search_method)
        method.body_layout.addWidget(self.own_following_method)
        method.body_layout.addWidget(self.specific_users)
        layout.addWidget(method)

        actions = ConfigurationSection("Unfollow Actions", container)
        action_fields = QWidget(actions)
        self.action_grid = QGridLayout(action_fields)
        self.action_grid.setContentsMargins(0, 0, 0, 0)
        self.action_grid.setHorizontalSpacing(12)
        self.action_grid.setVerticalSpacing(8)
        self.numeric = NumericSettings(
            {"unfollow-delay": "Unfollow Delay (days)"}, action_fields, columns=1
        )
        self.unfollow_amount = RangePairSettings(
            "Minimum users to unfollow", "Maximum users to unfollow", action_fields
        )
        self.limits = RangeSettings(
            {"total-unfollows-limit": "Unfollow Limit"}, action_fields
        )
        action_field_width = 180
        for control in (
            self.unfollow_amount.minimum,
            self.unfollow_amount.maximum,
            self.limits.controls["total-unfollows-limit"],
            self.numeric.controls["unfollow-delay"],
        ):
            control.setFixedWidth(action_field_width)
        self._place_range_pair(self.action_grid, 0, self.unfollow_amount)
        self._place_single_field(
            self.action_grid, 1, self.limits, "total-unfollows-limit"
        )
        self._place_single_field(self.action_grid, 2, self.numeric, "unfollow-delay")
        self.action_grid.setColumnStretch(4, 1)
        actions.body_layout.addWidget(action_fields)
        layout.addWidget(actions)

        additional = ConfigurationSection("Additional Settings", container)
        self.mode_options = CheckboxGroup(self.BEHAVIOUR_LABELS, additional, columns=1)
        self.dont_unfollow_followers = QCheckBox("Don't Unfollow Followers", additional)
        self.behaviour = CheckboxGroup(
            {
                "sort-followers-newest-to-oldest": "Process newest followed users first",
                "delete-removed-followers": "Remove processed users from the removal list",
            },
            additional,
            columns=1,
        )
        additional.body_layout.addWidget(self.mode_options)
        additional.body_layout.addWidget(self.dont_unfollow_followers)
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
        self.own_following_method.toggled.connect(self._method_changed)
        self.unfollow_amount.changed.connect(self._amount_changed)
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
        for key, control in self.behaviour.controls.items():
            control.toggled.connect(lambda _checked, key=key: self._field_changed(key))
        self.dont_unfollow_followers.toggled.connect(self._runtime_extension_changed)
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
            self.search_method.setChecked(
                any(self._mode_enabled(key) for key in self.SEARCH_KEYS)
            )
            self.own_following_method.setChecked(self._mode_enabled("unfollow-any"))
            self.unfollow_amount.set_value(self._first_mode_value())
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
                configuration.get(self.SPECIFIC_RESOURCE),
            )
            self._set_resource_row(
                self.remove_followers,
                configuration.get("remove-followers-from-file"),
                configuration.get(self.REMOVE_RESOURCE),
            )
            if not self._has_enabled_method():
                self.search_method.setChecked(True)
            self.enabled.setChecked(self._has_enabled_method())
            self.dont_unfollow_followers.setChecked(False)
            self.schedule_days.set_values(
                {day.casefold(): True for day in self.WEEKDAYS}
            )
            self._update_status()
        finally:
            self._loading = False

    def values(self) -> dict:
        values = self.modes.values()
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
            row.enabled.setChecked(bool(entries))
            self._field_changed(key)

    def _enabled_changed(self, enabled: bool) -> None:
        if self._loading:
            return
        if enabled and not self._has_enabled_method():
            self.search_method.setChecked(True)
            self.mode_options.controls["unfollow"].setChecked(True)
        self._edited_keys.update(self.RANGE_KEYS)
        self._update_status()
        self.changed.emit()

    def _method_changed(self) -> None:
        if self._loading:
            return
        if not self.search_method.isChecked():
            for key, control in self.mode_options.controls.items():
                control.setChecked(False)
                self._set_mode_value(key, False)
        elif not any(self.mode_options.values().values()):
            self.mode_options.controls["unfollow"].setChecked(True)
        self._set_mode_value("unfollow-any", self.own_following_method.isChecked())
        self._sync_enabled()

    def _mode_option_changed(self, key: str, checked: bool) -> None:
        if self._loading:
            return
        self._set_mode_value(key, checked)
        if checked:
            self.search_method.setChecked(True)
        self._sync_enabled()

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
            self._sync_enabled()

    def _sync_enabled(self) -> None:
        self.enabled.setChecked(self._has_enabled_method())
        self._update_status()
        self.changed.emit()

    def _runtime_extension_changed(self) -> None:
        if not self._loading:
            self.changed.emit()

    def _mode_enabled(self, key: str) -> bool:
        return self.modes.controls[key].text().strip() not in {"", "0"}

    def _mode_selected(self, key: str) -> bool:
        if key == "unfollow-any":
            return self.own_following_method.isChecked()
        return self.mode_options.controls[key].isChecked()

    def _first_mode_value(self) -> str:
        for control in self.modes.controls.values():
            if control.text().strip() not in {"", "0"}:
                return control.text()
        return "1"

    def _has_enabled_method(self) -> bool:
        return (
            any(self._mode_enabled(key) for key in self.RANGE_KEYS)
            or self.specific_users.enabled.isChecked()
        )

    def _update_status(self) -> None:
        enabled = self.enabled.isChecked()
        self.status.setText("● Enabled" if enabled else "● Disabled")
        self.status.setStyleSheet(f"color: {'#22C55E' if enabled else '#A1A1AA'}")
