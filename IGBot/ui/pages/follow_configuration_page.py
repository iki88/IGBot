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
    DecimalSettings,
    InlineListSettings,
    NumericSettings,
    RangeSettings,
)
from IGBot.ui.widgets.target_editor_dialog import TargetEditorDialog
from IGBot.ui.widgets.target_source_row import TargetSourceRow


class FollowConfigurationPage(QScrollArea):
    """Operator-focused editor for the engine's production Follow settings."""

    changed = Signal()
    SETTINGS: ClassVar[dict[str, str]] = {
        "follow-percentage": "Follow Percentage",
        "follow-limit": "Per-source Follow Limit",
        "total-follows-limit": "Per-session Follow Limit",
    }
    ADDITIONAL: ClassVar[dict[str, str]] = {
        "end-if-follows-limit-reached": "End Session When Follow Limit Is Reached"
    }
    FILTER_SWITCHES: ClassVar[dict[str, str]] = {
        "skip_follower": "Skip Existing Followers",
        "skip_if_private": "Skip Private Profiles",
        "skip_business": "Skip Business Profiles",
        "skip_non_business": "Skip Non-business Profiles",
        "skip_if_link_in_bio": "Skip Profiles With Link In Bio",
        "follow_private_or_empty": "Allow Private Or Empty Profiles",
    }
    FILTER_NUMBERS: ClassVar[dict[str, str]] = {
        "min_followers": "Minimum Followers",
        "max_followers": "Maximum Followers",
        "min_followings": "Minimum Following",
        "max_followings": "Maximum Following",
        "min_posts": "Minimum Posts",
    }
    FILTER_REMAINING_NUMBERS: ClassVar[dict[str, str]] = {
        "mutual_friends": "Minimum Mutual Friends",
    }
    FILTER_RATIOS: ClassVar[dict[str, str]] = {
        "min_potency_ratio": "Minimum Followers / Following Ratio",
        "max_potency_ratio": "Maximum Followers / Following Ratio",
    }
    FILTER_EDITORS: ClassVar[dict[str, str]] = {
        "mandatory_words": "Follow only if user contains these words",
        "blacklist_words": "Don't follow if user contains these words",
    }
    FILTER_LISTS: ClassVar[dict[str, str]] = {
        "specific_alphabet": "Allowed Alphabet",
        "biography_language": "Biography Language",
        "biography_banned_language": "Blocked Biography Language",
    }

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

        enable_section = ConfigurationSection("Enable", container)
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

        self.sources = AudienceSourcesPage(container, include_advanced=False)
        self.sources.setObjectName("moduleSources")
        self.sources.setVisible(include_sources)
        self.sources.changed.connect(self.changed)
        layout.addWidget(self.sources)

        settings_section = ConfigurationSection("Settings", container)
        self.settings = RangeSettings(self.SETTINGS, settings_section)
        settings_section.body_layout.addWidget(self.settings)
        layout.addWidget(settings_section)

        additional_section = ConfigurationSection("Additional Settings", container)
        self.additional = CheckboxGroup(self.ADDITIONAL, additional_section)
        additional_section.body_layout.addWidget(self.additional)
        layout.addWidget(additional_section)

        filters_section = ConfigurationSection("Filters", container)
        self.filter_switches = CheckboxGroup(self.FILTER_SWITCHES, filters_section)
        self.filter_numbers = NumericSettings(self.FILTER_NUMBERS, filters_section)
        self.filter_remaining_numbers = NumericSettings(
            self.FILTER_REMAINING_NUMBERS, filters_section
        )
        self.filter_remaining_numbers.controls["mutual_friends"].setMinimum(-1)
        self.filter_ratios = DecimalSettings(self.FILTER_RATIOS, filters_section)
        self.filter_editors = {}
        for key, label in self.FILTER_EDITORS.items():
            row = TargetSourceRow(
                label, filters_section, item_noun="entry", switch_style=False
            )
            row.changed.connect(lambda key=key: self._field_changed(key))
            row.edit_requested.connect(lambda key=key: self._edit_filter_list(key))
            self.filter_editors[key] = row
        self.filter_lists = InlineListSettings(
            self.FILTER_LISTS, filters_section, columns=1
        )
        for widget in (
            self.filter_numbers,
            self.filter_remaining_numbers,
            self.filter_ratios,
            self.filter_switches,
        ):
            filters_section.body_layout.addWidget(widget)
        for row in self.filter_editors.values():
            filters_section.body_layout.addWidget(row)
        filters_section.body_layout.addWidget(self.filter_lists)
        layout.addWidget(filters_section)
        layout.addStretch()
        self.setWidget(container)

        for editor in (
            self.settings,
            self.additional,
            self.filter_switches,
            self.filter_numbers,
            self.filter_remaining_numbers,
            self.filter_ratios,
            self.filter_lists,
        ):
            self._connect_editor(editor)

    def _connect_editor(self, editor: QWidget) -> None:
        for key, control in editor.controls.items():
            if isinstance(control, QCheckBox):
                signal = control.toggled
            elif hasattr(control, "valueChanged"):
                signal = control.valueChanged
            else:
                signal = control.textChanged
            signal.connect(lambda *_args, key=key: self._field_changed(key))

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

    def set_configuration(self, configuration: dict) -> None:
        keys = (
            set(self.SETTINGS)
            | set(self.ADDITIONAL)
            | set(self.FILTER_SWITCHES)
            | set(self.FILTER_NUMBERS)
            | set(self.FILTER_REMAINING_NUMBERS)
            | set(self.FILTER_RATIOS)
            | set(self.FILTER_EDITORS)
            | set(self.FILTER_LISTS)
        )
        self._loading = True
        try:
            self._present_keys = keys & set(configuration)
            self._edited_keys.clear()
            percentage = str(configuration.get("follow-percentage") or "0")
            self._enabled_percentage = percentage if percentage != "0" else "1"
            self.enabled.setChecked(percentage != "0")
            self.settings.set_values(configuration)
            self.additional.set_values(configuration)
            self.filter_switches.set_values(configuration)
            self.filter_numbers.set_values(configuration)
            self.filter_remaining_numbers.set_values(configuration)
            self.filter_ratios.set_values(configuration)
            for key, row in self.filter_editors.items():
                value = configuration.get(key)
                row.set_entries(value if isinstance(value, list) else [])
                row.enabled.setChecked(bool(value))
            self.filter_lists.set_values(configuration)
            self.sources.set_configuration(configuration)
        finally:
            self._loading = False

    def values(self) -> dict:
        values = {}
        settings = self.settings.values()
        percentage = settings["follow-percentage"]
        if percentage and max(int(part) for part in percentage.split("-")) > 100:
            raise ValueError("Follow percentage cannot exceed 100.")
        settings["follow-percentage"] = (
            (percentage or self._enabled_percentage)
            if self.enabled.isChecked()
            else "0"
        )
        for candidate in (
            settings,
            self.additional.values(),
            self.filter_switches.values(),
            self.filter_numbers.values(),
            self.filter_remaining_numbers.values(),
            self.filter_ratios.values(),
            self._filter_editor_values(),
            self.filter_lists.values(),
        ):
            values.update(self._selected_values(candidate))
        self._validate_filter_ranges(values)
        return values

    def _edit_filter_list(self, key: str) -> None:
        row = self.filter_editors[key]
        dialog = TargetEditorDialog(row.name.text(), row.entries(), parent=self)
        if dialog.exec() == TargetEditorDialog.Accepted:
            entries = dialog.entries()
            row.set_entries(entries)
            row.enabled.setChecked(bool(entries))
            self._field_changed(key)

    def _filter_editor_values(self) -> dict:
        values = {}
        for key, row in self.filter_editors.items():
            entries = row.entries()
            if row.enabled.isChecked():
                if not entries:
                    row.name.setStyleSheet("border: 1px solid #EF4444;")
                    row.name.setFocus()
                    raise ValueError(f"Add at least one entry for {row.name.text()}.")
                row.name.setStyleSheet("")
                values[key] = entries
            elif key in self._present_keys or key in self._edited_keys:
                values[key] = None
        return values

    def _selected_values(self, candidate: dict) -> dict:
        selected = {}
        for key, value in candidate.items():
            if key not in self._present_keys and key not in self._edited_keys:
                continue
            selected[key] = None if value == "" or value == [] else value
        return selected

    @staticmethod
    def _validate_filter_ranges(values: dict) -> None:
        for minimum_key, maximum_key, label in (
            ("min_followers", "max_followers", "followers"),
            ("min_followings", "max_followings", "following"),
            ("min_potency_ratio", "max_potency_ratio", "ratio"),
        ):
            minimum = values.get(minimum_key)
            maximum = values.get(maximum_key)
            if minimum is not None and maximum is not None and minimum > maximum:
                raise ValueError(f"Minimum {label} cannot exceed maximum {label}.")
