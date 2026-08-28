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
    TextListSettings,
)
from IGBot.ui.widgets.target_editor_dialog import TargetEditorDialog
from IGBot.ui.widgets.target_source_row import TargetSourceRow


class LikeConfigurationPage(QScrollArea):
    """Operator-focused editor for documented engine Like settings."""

    changed = Signal()
    INTERACTION_KEYS: ClassVar[dict[str, str]] = {
        "likes-count": "Likes per Profile",
        "likes-percentage": "Like Percentage",
    }
    LIMIT_KEYS: ClassVar[dict[str, str]] = {"total-likes-limit": "Daily Like Limit"}
    MEDIA_KEYS: ClassVar[dict[str, str]] = {
        "carousel-count": "Carousel Photos",
        "carousel-percentage": "Carousel Percentage",
        "watch-photo-time": "Photo View Time (seconds)",
        "watch-video-time": "Video / Reel View Time (seconds)",
    }
    BOOLEAN_KEYS: ClassVar[dict[str, str]] = {
        "end-if-likes-limit-reached": "Stop Like module when Like limit is reached"
    }
    LIST_KEYS: ClassVar[dict[str, str]] = {"posts-from-file": "Post URL Files"}
    FILTER_KEYS: ClassVar[dict[str, str]] = {
        "min_likers": "Minimum Likes on Post",
        "max_likers": "Maximum Likes on Post",
    }
    PROFILE_FILTER_KEYS: ClassVar[dict[str, str]] = {
        "min_posts": "Minimum Posts",
        "min_followers": "Minimum Followers",
        "max_followers": "Maximum Followers",
        "min_followings": "Minimum Followings",
        "max_followings": "Maximum Followings",
    }
    LIST_FILTERS: ClassVar[dict[str, str]] = {
        "mandatory_words": "Like only if profile contains these words",
        "blacklist_words": "Don't like if profile contains these words",
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

    def __init__(
        self,
        parent=None,
        include_file_targets: bool = True,
        include_sources: bool = True,
    ) -> None:
        super().__init__(parent)
        self.include_file_targets = include_file_targets
        self._loading = False
        self._present_keys: set[str] = set()
        self._edited_keys: set[str] = set()
        self._enabled_percentage = "100"
        self.setWidgetResizable(True)
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 14, 12, 14)
        layout.setSpacing(12)

        enable = ConfigurationSection("Enable Like", container)
        enable_row = QHBoxLayout()
        self.enabled = QCheckBox("Enable Like", enable)
        self.enabled.setObjectName("configurationSwitch")
        self.status = QLabel("● Disabled", enable)
        enable_row.addWidget(self.enabled)
        enable_row.addStretch()
        enable_row.addWidget(self.status)
        enable.body_layout.addLayout(enable_row)
        layout.addWidget(enable)

        self.sources = AudienceSourcesPage(
            container, include_advanced=False, section_title="Like Method"
        )
        self.sources.setVisible(include_sources)
        self.sources.rows["blogger-followers"].name.setText("Like Source's Followers")
        self.sources.rows["blogger"].name.setText("Like Posts of Specific Users")
        self.sources.rows["blogger-following"].hide()
        layout.addWidget(self.sources)

        actions = ConfigurationSection("Like Actions", container)
        action_fields = QWidget(actions)
        self.action_grid = QGridLayout(action_fields)
        self.action_grid.setContentsMargins(0, 0, 0, 0)
        self.action_grid.setHorizontalSpacing(12)
        self.action_grid.setVerticalSpacing(8)
        self.user_amount = RangePairSettings(
            "Minimum users to like", "Maximum users to like", action_fields
        )
        self.delay = RangePairSettings(
            "Minimum delay after liking", "Maximum delay after liking", action_fields
        )
        self.interaction = RangeSettings(self.INTERACTION_KEYS, action_fields)
        self.limits = RangeSettings(self.LIMIT_KEYS, action_fields)
        self.media = RangeSettings(self.MEDIA_KEYS, action_fields)
        width = 180
        for control in (
            self.user_amount.minimum,
            self.user_amount.maximum,
            self.delay.minimum,
            self.delay.maximum,
            self.limits.controls["total-likes-limit"],
            self.interaction.controls["likes-count"],
            self.interaction.controls["likes-percentage"],
            self.media.controls["watch-photo-time"],
            self.media.controls["watch-video-time"],
        ):
            control.setFixedWidth(width)
        self._place_pair(self.action_grid, 0, self.user_amount)
        self._place_pair(self.action_grid, 1, self.delay)
        self._place_field(self.action_grid, 2, self.limits, "total-likes-limit")
        self._place_field(self.action_grid, 3, self.interaction, "likes-count")
        self._place_field(self.action_grid, 4, self.media, "watch-photo-time")
        self._place_field(self.action_grid, 5, self.media, "watch-video-time")
        self._place_field(self.action_grid, 6, self.interaction, "likes-percentage")
        self.media.labels["carousel-count"].hide()
        self.media.controls["carousel-count"].hide()
        self.media.labels["carousel-percentage"].hide()
        self.media.controls["carousel-percentage"].hide()
        self.action_grid.setColumnStretch(4, 1)
        actions.body_layout.addWidget(action_fields)
        layout.addWidget(actions)

        additional = ConfigurationSection("Additional Settings", container)
        self.limit_behaviour = CheckboxGroup(self.BOOLEAN_KEYS, additional, columns=1)
        self.limit_behaviour.hide()
        self.files = TextListSettings(self.LIST_KEYS, additional)
        self.files.hide()
        self.files_section = self.files
        self.word_filters = {}
        for key, label in self.LIST_FILTERS.items():
            row = TargetSourceRow(
                label, additional, item_noun="entry", switch_style=False
            )
            row.changed.connect(lambda key=key: self._field_changed(key))
            row.edit_requested.connect(lambda key=key: self._edit_word_filter(key))
            self.word_filters[key] = row
            additional.body_layout.addWidget(row)
        self.delete_from_source = QCheckBox(
            "Delete specific accounts from source file after liking", additional
        )
        self.tagged_account_protection = QCheckBox(
            "Don't like user already liked by the same tagged account", additional
        )
        additional.body_layout.addWidget(self.delete_from_source)
        additional.body_layout.addWidget(self.tagged_account_protection)
        layout.addWidget(additional)

        filters = ConfigurationSection("Filters", container)
        self.post_filter_enabled = QCheckBox("Enable Post Count Filter", filters)
        self.post_filter = NumericSettings(
            {"min_posts": "Minimum Posts"}, filters, columns=1
        )
        self.post_filter.controls["min_posts"].setFixedWidth(180)
        self.followers_filter_enabled = QCheckBox(
            "Enable Followers Count Filter", filters
        )
        self.followers_filter = NumericSettings(
            {
                "min_followers": "Minimum Followers",
                "max_followers": "Maximum Followers",
            },
            filters,
        )
        self.followings_filter_enabled = QCheckBox(
            "Enable Following Count Filter", filters
        )
        self.followings_filter = NumericSettings(
            {
                "min_followings": "Minimum Followings",
                "max_followings": "Maximum Followings",
            },
            filters,
        )
        self.likes_filter_enabled = QCheckBox("Enable Likes on Post Filter", filters)
        self.filters = NumericSettings(self.FILTER_KEYS, filters)
        for toggle, editor in (
            (self.post_filter_enabled, self.post_filter),
            (self.followers_filter_enabled, self.followers_filter),
            (self.followings_filter_enabled, self.followings_filter),
            (self.likes_filter_enabled, self.filters),
        ):
            filters.body_layout.addWidget(toggle)
            filters.body_layout.addWidget(editor)
            editor.hide()
        layout.addWidget(filters)

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
        for group in (self.interaction, self.limits, self.media):
            for key, control in group.controls.items():
                control.textChanged.connect(
                    lambda _text, key=key: self._field_changed(key)
                )
        for key, control in self.limit_behaviour.controls.items():
            control.toggled.connect(lambda _checked, key=key: self._field_changed(key))
        for key, control in self.filters.controls.items():
            control.valueChanged.connect(
                lambda _value, key=key: self._field_changed(key)
            )
        for group in (
            self.post_filter,
            self.followers_filter,
            self.followings_filter,
        ):
            for key, control in group.controls.items():
                control.valueChanged.connect(
                    lambda _value, key=key: self._field_changed(key)
                )
        for toggle, editor, keys in (
            (self.post_filter_enabled, self.post_filter, ("min_posts",)),
            (
                self.followers_filter_enabled,
                self.followers_filter,
                ("min_followers", "max_followers"),
            ),
            (
                self.followings_filter_enabled,
                self.followings_filter,
                ("min_followings", "max_followings"),
            ),
            (
                self.likes_filter_enabled,
                self.filters,
                ("min_likers", "max_likers"),
            ),
        ):
            toggle.toggled.connect(
                lambda checked, editor=editor, keys=keys: self._filter_toggled(
                    checked, editor, keys
                )
            )
        self.delete_from_source.toggled.connect(
            lambda _checked: self._field_changed("delete-interacted-users")
        )
        self.tagged_account_protection.toggled.connect(self._runtime_extension_changed)
        self.sources.changed.connect(self._changed)
        self.files.changed.connect(self._changed)
        self.user_amount.changed.connect(self._runtime_extension_changed)
        self.delay.changed.connect(self._runtime_extension_changed)
        self.schedule_days.changed.connect(self._runtime_extension_changed)

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
        layout: QGridLayout, row: int, settings: RangeSettings, key: str
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
            set(cls.INTERACTION_KEYS)
            | set(cls.LIMIT_KEYS)
            | set(cls.MEDIA_KEYS)
            | set(cls.BOOLEAN_KEYS)
            | set(cls.LIST_KEYS)
            | set(cls.FILTER_KEYS)
            | set(cls.PROFILE_FILTER_KEYS)
            | set(cls.LIST_FILTERS)
            | {"delete-interacted-users"}
        )

    def set_configuration(self, configuration: dict) -> None:
        self._loading = True
        try:
            self._present_keys = self.supported_keys() & set(configuration)
            self._edited_keys.clear()
            self.interaction.set_values(configuration)
            percentage = str(configuration.get("likes-percentage") or "0")
            self._enabled_percentage = percentage if percentage != "0" else "100"
            if "likes-percentage" not in configuration:
                self.interaction.controls["likes-percentage"].setText("100")
            self.enabled.setChecked(percentage != "0")
            self.limits.set_values(configuration)
            self.limit_behaviour.set_values(configuration)
            self.media.set_values(configuration)
            self.filters.set_values(configuration)
            self.post_filter.set_values(configuration)
            self.followers_filter.set_values(configuration)
            self.followings_filter.set_values(configuration)
            self._set_filter_enabled(
                self.post_filter_enabled,
                self.post_filter,
                any(key in configuration for key in ("min_posts",)),
            )
            self._set_filter_enabled(
                self.followers_filter_enabled,
                self.followers_filter,
                any(key in configuration for key in ("min_followers", "max_followers")),
            )
            self._set_filter_enabled(
                self.followings_filter_enabled,
                self.followings_filter,
                any(
                    key in configuration for key in ("min_followings", "max_followings")
                ),
            )
            self._set_filter_enabled(
                self.likes_filter_enabled,
                self.filters,
                any(key in configuration for key in ("min_likers", "max_likers")),
            )
            for key, row in self.word_filters.items():
                value = configuration.get(key)
                row.set_entries(value if isinstance(value, list) else [])
                row.enabled.setChecked(bool(value))
            self.delete_from_source.setChecked(
                bool(configuration.get("delete-interacted-users", False))
            )
            self.files.set_values(configuration)
            self.sources.set_configuration(configuration)
            self.user_amount.set_value(None)
            self.delay.set_value(None)
            self.schedule_days.set_values(
                {day.casefold(): True for day in self.WEEKDAYS}
            )
            self._update_status()
        finally:
            self._loading = False

    def values(self) -> dict:
        values = self.interaction.values()
        values["likes-percentage"] = (
            self._enabled_percentage if self.enabled.isChecked() else "0"
        )
        values.update(self.limits.values())
        values.update(self.limit_behaviour.values())
        values.update(self.media.values())
        values.update(self._filter_values())
        values.update(self._word_filter_values())
        values["delete-interacted-users"] = self.delete_from_source.isChecked()
        if self.include_file_targets:
            values.update(self.files.values())
        for key, label in (
            ("likes-percentage", "Like Percentage"),
            ("carousel-percentage", "Carousel Percentage"),
        ):
            value = str(values.get(key) or "")
            if value and max(int(part) for part in value.split("-")) > 100:
                control = (
                    self.interaction.controls[key]
                    if key in self.interaction.controls
                    else self.media.controls[key]
                )
                control.setStyleSheet("border: 1px solid #EF4444;")
                control.setFocus()
                raise ValueError(f"{label} cannot exceed 100.")
        result = {}
        for key, value in values.items():
            populated = (
                bool(value)
                if isinstance(value, list)
                else value not in {"", "0", 0, None}
            )
            if (
                key in self._present_keys or key in self._edited_keys or populated
            ) and (not isinstance(value, list) or value):
                result[key] = value
        for minimum_key, maximum_key, editor, noun in (
            ("min_followers", "max_followers", self.followers_filter, "followers"),
            (
                "min_followings",
                "max_followings",
                self.followings_filter,
                "followings",
            ),
            ("min_likers", "max_likers", self.filters, "likes on post"),
        ):
            minimum = result.get(minimum_key)
            maximum = result.get(maximum_key)
            if minimum is not None and maximum is not None and minimum > maximum:
                editor.controls[minimum_key].setFocus()
                raise ValueError(f"Minimum {noun} cannot exceed maximum {noun}.")
        return result

    def _filter_values(self) -> dict:
        values = {}
        for toggle, editor in (
            (self.post_filter_enabled, self.post_filter),
            (self.followers_filter_enabled, self.followers_filter),
            (self.followings_filter_enabled, self.followings_filter),
            (self.likes_filter_enabled, self.filters),
        ):
            for key, value in editor.values().items():
                if key in self._edited_keys:
                    values[key] = value if toggle.isChecked() else None
        return values

    def _word_filter_values(self) -> dict:
        values = {}
        for key, row in self.word_filters.items():
            if key not in self._edited_keys:
                continue
            entries = row.entries()
            if row.enabled.isChecked():
                if not entries:
                    row.name.setFocus()
                    raise ValueError(f"Add at least one entry for {row.name.text()}.")
                values[key] = entries
            else:
                values[key] = None
        return values

    @staticmethod
    def _set_filter_enabled(toggle: QCheckBox, editor: QWidget, enabled: bool) -> None:
        toggle.setChecked(enabled)
        editor.setVisible(enabled)

    def _filter_toggled(
        self, checked: bool, editor: QWidget, keys: tuple[str, ...]
    ) -> None:
        editor.setVisible(checked)
        if not self._loading:
            self._edited_keys.update(keys)
            self.changed.emit()

    def _edit_word_filter(self, key: str) -> None:
        row = self.word_filters[key]
        dialog = TargetEditorDialog(
            row.name.text(), row.entries(), lambda entry: bool(entry.strip()), self
        )
        if dialog.exec() == TargetEditorDialog.Accepted:
            entries = dialog.entries()
            row.set_entries(entries)
            row.enabled.setChecked(bool(entries))
            self._field_changed(key)

    def _enabled_changed(self, enabled: bool) -> None:
        self._update_status()
        if not self._loading:
            self._edited_keys.add("likes-percentage")
            self.changed.emit()

    def _field_changed(self, key: str) -> None:
        if self._loading:
            return
        self._edited_keys.add(key)
        if key == "likes-percentage":
            value = self.interaction.controls[key].text().strip()
            if value not in {"", "0"}:
                self._enabled_percentage = value
                self.enabled.setChecked(True)
            elif value == "0":
                self.enabled.setChecked(False)
        self._update_status()
        self.changed.emit()

    def _changed(self) -> None:
        if not self._loading:
            self.changed.emit()

    def _runtime_extension_changed(self) -> None:
        if not self._loading:
            self.changed.emit()

    def _update_status(self) -> None:
        enabled = self.enabled.isChecked()
        self.status.setText("● Enabled" if enabled else "● Disabled")
        self.status.setStyleSheet(f"color: {'#22C55E' if enabled else '#A1A1AA'}")
