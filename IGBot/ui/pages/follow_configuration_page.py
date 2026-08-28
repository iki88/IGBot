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

from IGBot.ui.pages.audience_sources_page import AudienceSourcesPage
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


class FollowConfigurationPage(QScrollArea):
    """Operator-focused editor with a strict engine compatibility boundary."""

    changed = Signal()

    PROFILE_SETTINGS: ClassVar[dict[str, str]] = {
        "min_followers": "Minimum Followers",
        "max_followers": "Maximum Followers",
        "min_followings": "Minimum Followings",
        "max_followings": "Maximum Followings",
        "min_posts": "Minimum Posts",
    }
    ADDITIONAL_ENGINE_SETTINGS: ClassVar[dict[str, str]] = {
        "skip_business": "Skip business profiles",
        "skip_non_business": "Skip non-business profiles",
        "skip_if_link_in_bio": "Skip profiles with link in Bio",
        "follow_private_or_empty": "Follow private or empty profiles",
    }
    LIST_FILTERS: ClassVar[dict[str, str]] = {
        "mandatory_words": "Follow only if profile contains these words",
        "blacklist_words": "Don't follow if profile contains these words",
        "specific_alphabet": "Allowed Alphabets",
        "biography_language": "Biography Language",
        "biography_banned_language": "Blocked Biography Language",
    }
    WEEKDAYS: ClassVar[tuple[str, ...]] = (
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    )

    def __init__(self, parent=None, include_sources: bool = True) -> None:
        super().__init__(parent)
        self._loading = False
        self._present_keys: set[str] = set()
        self._edited_keys: set[str] = set()
        self._enabled_percentage = "1"
        self.setWidgetResizable(True)
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 14, 12, 14)
        layout.setSpacing(12)

        enable_section = ConfigurationSection("Enable Follow", container)
        enable_row = QHBoxLayout()
        self.enabled = QCheckBox("Enable Follow", enable_section)
        self.enabled.setObjectName("configurationSwitch")
        self.status = QLabel("● Disabled", enable_section)
        self.enabled.toggled.connect(self._enabled_changed)
        enable_row.addWidget(self.enabled)
        enable_row.addStretch()
        enable_row.addWidget(self.status)
        enable_section.body_layout.addLayout(enable_row)
        layout.addWidget(enable_section)

        self.sources = AudienceSourcesPage(
            container, include_advanced=False, section_title="Follow Method"
        )
        self.sources.setObjectName("moduleSources")
        self.sources.setVisible(include_sources)
        self.sources.changed.connect(self.changed)
        layout.addWidget(self.sources)

        actions_section = ConfigurationSection("Follow Actions", container)
        action_fields = QWidget(actions_section)
        action_grid = QGridLayout(action_fields)
        self.action_grid = action_grid
        action_grid.setContentsMargins(0, 0, 0, 0)
        action_grid.setHorizontalSpacing(12)
        action_grid.setVerticalSpacing(8)
        self.follow_amount = RangePairSettings(
            "Minimum users to follow", "Maximum users to follow", action_fields
        )
        self.delay = RangePairSettings(
            "Minimum delay after following",
            "Maximum delay after following",
            action_fields,
        )
        self.follow_limit = RangeSettings(
            {"total-follows-limit": "Follow limit"}, action_fields
        )
        action_field_width = 180
        for control in (
            self.follow_amount.minimum,
            self.follow_amount.maximum,
            self.delay.minimum,
            self.delay.maximum,
            self.follow_limit.controls["total-follows-limit"],
        ):
            control.setFixedWidth(action_field_width)
        self._place_range_pair(action_grid, 0, self.follow_amount)
        self._place_range_pair(action_grid, 1, self.delay)
        limit_key = "total-follows-limit"
        limit_layout = self.follow_limit.layout()
        limit_layout.removeWidget(self.follow_limit.labels[limit_key])
        limit_layout.removeWidget(self.follow_limit.controls[limit_key])
        action_grid.addWidget(self.follow_limit.labels[limit_key], 2, 0)
        action_grid.addWidget(self.follow_limit.controls[limit_key], 2, 1)
        action_grid.setColumnStretch(4, 1)
        actions_section.body_layout.addWidget(action_fields)
        layout.addWidget(actions_section)

        settings_section = ConfigurationSection("Follow Settings", container)
        self.profile_settings = NumericSettings(self.PROFILE_SETTINGS, settings_section)
        settings_section.body_layout.addWidget(self.profile_settings)
        layout.addWidget(settings_section)

        additional_section = ConfigurationSection(
            "Additional Follow Settings", container
        )
        self.mute_after_follow = QCheckBox(
            "Mute users after following", additional_section
        )
        self.additional_settings = CheckboxGroup(
            self.ADDITIONAL_ENGINE_SETTINGS, additional_section, columns=1
        )
        self.list_filters = {}
        for key, label in self.LIST_FILTERS.items():
            row = TargetSourceRow(
                label, additional_section, item_noun="entry", switch_style=False
            )
            row.changed.connect(lambda key=key: self._field_changed(key))
            row.edit_requested.connect(lambda key=key: self._edit_list_filter(key))
            self.list_filters[key] = row
        self.word_filters = self.list_filters
        self.same_tagged_account = QCheckBox(
            "Don't follow users already followed by the same tagged account",
            additional_section,
        )
        additional_section.body_layout.addWidget(self.mute_after_follow)
        additional_section.body_layout.addWidget(self.additional_settings)
        for row in self.list_filters.values():
            additional_section.body_layout.addWidget(row)
        additional_section.body_layout.addWidget(self.same_tagged_account)
        layout.addWidget(additional_section)

        schedule_section = CollapsibleSection(
            "Schedule", container, collapsible=True, collapsed=True
        )
        self.schedule_section = schedule_section
        self.schedule_days = CheckboxGroup(
            {day.casefold(): day for day in self.WEEKDAYS},
            schedule_section,
            columns=1,
        )
        self.schedule_days.set_values({day.casefold(): True for day in self.WEEKDAYS})
        schedule_section.body_layout.addWidget(self.schedule_days)
        layout.addWidget(schedule_section)
        layout.addStretch()
        self.setWidget(container)

        self.follow_amount.changed.connect(lambda: self._field_changed("follow-limit"))
        self.follow_limit.changed.connect(
            lambda: self._field_changed("total-follows-limit")
        )
        for key, control in self.profile_settings.controls.items():
            control.valueChanged.connect(
                lambda _value, key=key: self._field_changed(key)
            )
        for key, control in self.additional_settings.controls.items():
            control.toggled.connect(lambda _checked, key=key: self._field_changed(key))
        for control in (self.delay.minimum, self.delay.maximum):
            control.valueChanged.connect(self._runtime_extension_changed)
        self.mute_after_follow.toggled.connect(self._runtime_extension_changed)
        self.same_tagged_account.toggled.connect(self._runtime_extension_changed)
        self.schedule_days.changed.connect(self._runtime_extension_changed)

    @staticmethod
    def _place_range_pair(
        layout: QGridLayout, row: int, pair: RangePairSettings
    ) -> None:
        pair_layout = pair.layout()
        widgets = (
            pair.minimum_label,
            pair.minimum,
            pair.maximum_label,
            pair.maximum,
        )
        for column, widget in enumerate(widgets):
            pair_layout.removeWidget(widget)
            layout.addWidget(widget, row, column)

    def _enabled_changed(self, enabled: bool) -> None:
        self.status.setText("● Enabled" if enabled else "● Disabled")
        self.status.setStyleSheet(f"color: {'#22C55E' if enabled else '#A1A1AA'}")
        if not self._loading:
            self._edited_keys.add("follow-percentage")
            self.changed.emit()

    def _field_changed(self, key: str) -> None:
        if not self._loading:
            self._edited_keys.add(key)
            self.changed.emit()

    def _runtime_extension_changed(self, *_args) -> None:
        if not self._loading:
            self.changed.emit()

    def set_configuration(self, configuration: dict) -> None:
        engine_keys = (
            {"follow-percentage", "follow-limit", "total-follows-limit"}
            | set(self.PROFILE_SETTINGS)
            | set(self.ADDITIONAL_ENGINE_SETTINGS)
            | set(self.LIST_FILTERS)
        )
        self._loading = True
        try:
            self._present_keys = engine_keys & set(configuration)
            self._edited_keys.clear()
            percentage = str(configuration.get("follow-percentage") or "0")
            self._enabled_percentage = percentage if percentage != "0" else "1"
            self.enabled.setChecked(percentage != "0")
            self.follow_amount.set_value(configuration.get("follow-limit"))
            self.follow_limit.set_values(configuration)
            self.profile_settings.set_values(configuration)
            self.additional_settings.set_values(configuration)
            for key, row in self.list_filters.items():
                value = configuration.get(key)
                row.set_entries(value if isinstance(value, list) else [])
                row.enabled.setChecked(bool(value))
            self.sources.set_configuration(configuration)
            self._reset_runtime_extensions()
        finally:
            self._loading = False

    def _reset_runtime_extensions(self) -> None:
        self.delay.set_value(None)
        self.mute_after_follow.setChecked(False)
        self.same_tagged_account.setChecked(False)
        self.schedule_days.set_values({day.casefold(): True for day in self.WEEKDAYS})

    def values(self) -> dict:
        values = {}
        percentage = self._enabled_percentage if self.enabled.isChecked() else "0"
        if (
            "follow-percentage" in self._present_keys
            or "follow-percentage" in self._edited_keys
        ):
            values["follow-percentage"] = percentage
        if "follow-limit" in self._present_keys or "follow-limit" in self._edited_keys:
            values["follow-limit"] = self.follow_amount.value()
        limit = self.follow_limit.values()["total-follows-limit"]
        if (
            "total-follows-limit" in self._present_keys
            or "total-follows-limit" in self._edited_keys
        ):
            values["total-follows-limit"] = limit or None
        values.update(self._selected_values(self.profile_settings.values()))
        values.update(self._selected_values(self.additional_settings.values()))
        values.update(self._selected_values(self._list_filter_values()))
        self._validate_profile_ranges(values)
        return values

    def _edit_list_filter(self, key: str) -> None:
        row = self.list_filters[key]
        dialog = TargetEditorDialog(
            row.name.text(), row.entries(), self._list_filter_validator(key), self
        )
        if dialog.exec() == TargetEditorDialog.Accepted:
            entries = dialog.entries()
            row.set_entries(entries)
            row.enabled.setChecked(bool(entries))
            self._field_changed(key)

    @staticmethod
    def _list_filter_validator(key: str):
        if key in {"biography_language", "biography_banned_language"}:
            return lambda entry: bool(
                re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]+)?", entry)
            )
        if key == "specific_alphabet":
            return lambda entry: bool(re.fullmatch(r"[A-Za-z][A-Za-z _-]*", entry))
        return lambda entry: bool(entry.strip())

    def _list_filter_values(self) -> dict:
        values = {}
        for key, row in self.list_filters.items():
            entries = row.entries()
            if row.enabled.isChecked():
                if not entries:
                    row.name.setFocus()
                    raise ValueError(f"Add at least one entry for {row.name.text()}.")
                values[key] = entries
            elif key in self._present_keys or key in self._edited_keys:
                values[key] = None
        return values

    def _selected_values(self, candidate: dict) -> dict:
        return {
            key: value
            for key, value in candidate.items()
            if key in self._present_keys or key in self._edited_keys
        }

    @staticmethod
    def _validate_profile_ranges(values: dict) -> None:
        for minimum_key, maximum_key, label in (
            ("min_followers", "max_followers", "followers"),
            ("min_followings", "max_followings", "followings"),
        ):
            minimum = values.get(minimum_key)
            maximum = values.get(maximum_key)
            if minimum is not None and maximum is not None and minimum > maximum:
                raise ValueError(f"Minimum {label} cannot exceed maximum {label}.")
