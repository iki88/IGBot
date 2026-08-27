from typing import ClassVar

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QRadioButton,
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


class CommentConfigurationPage(QScrollArea):
    """Configuration editor for the engine's Comment settings."""

    changed = Signal()
    CONFIG_RANGE_KEYS: ClassVar[dict[str, str]] = {
        "comment-percentage": "Comment Percentage",
        "max-comments-pro-user": "Maximum Comments per User",
    }
    LIMIT_KEYS: ClassVar[dict[str, str]] = {
        "total-comments-limit": "Total Comments Limit",
    }
    CONFIG_BOOLEAN_KEYS: ClassVar[dict[str, str]] = {
        "end-if-comments-limit-reached": "End Session when Comment Limit is Reached",
    }
    CONTENT_FILTER_KEYS: ClassVar[dict[str, str]] = {
        "comment_photos": "Comment on Photos",
        "comment_videos": "Comment on Videos",
        "comment_carousels": "Comment on Carousels",
    }
    SOURCE_FILTER_KEYS: ClassVar[dict[str, str]] = {
        "comment_hashtag_likers_top": "Top Hashtag Likers",
        "comment_hashtag_likers_recent": "Recent Hashtag Likers",
        "comment_hashtag_posts_top": "Top Hashtag Posts",
        "comment_hashtag_posts_recent": "Recent Hashtag Posts",
        "comment_place_likers_top": "Top Place Likers",
        "comment_place_likers_recent": "Recent Place Likers",
        "comment_place_posts_top": "Top Place Posts",
        "comment_place_posts_recent": "Recent Place Posts",
        "comment_blogger_followers": "Blogger Followers",
        "comment_blogger_following": "Blogger Following",
        "comment_blogger_post_likers": "Blogger Post Likers",
        "comment_blogger": "Blogger Posts",
        "comment_interact_usernames": "Username Targets",
        "comment_interact_from_file": "File Targets",
        "comment_feed": "Feed",
    }
    COMMENT_RESOURCE = "comments_list.txt"

    def __init__(
        self, parent=None, include_comments: bool = True, include_sources: bool = True
    ) -> None:
        super().__init__(parent)
        self.include_comments = include_comments
        self._present_keys: set[str] = set()
        self._comment_file_present = False
        self._syncing_method = False
        self._explicitly_disabled = False
        self._enabled_percentage = "1"
        self.setWidgetResizable(True)
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 14, 12, 14)
        layout.setSpacing(12)

        method_section = ConfigurationSection("Enable / Disable", container)
        method_row = QHBoxLayout()
        self.method_group = QButtonGroup(self)
        self.ai_method = QRadioButton("AI Comments (Coming Soon)", method_section)
        self.ai_method.setEnabled(False)
        self.spintax_method = QRadioButton("Spintax", method_section)
        self.disabled_method = QRadioButton("Disabled", method_section)
        self.method_group.addButton(self.ai_method)
        self.method_group.addButton(self.spintax_method)
        self.method_group.addButton(self.disabled_method)
        self.status = QLabel("● Disabled", method_section)
        for option in (self.ai_method, self.spintax_method, self.disabled_method):
            method_row.addWidget(option)
        method_row.addStretch()
        method_row.addWidget(self.status)
        method_section.body_layout.addLayout(method_row)
        layout.addWidget(method_section)

        self.sources = AudienceSourcesPage(container)
        self.sources.setVisible(include_sources)
        layout.addWidget(self.sources)

        self.comments = TextResourceEditor(
            "Comment Editor",
            "Enter comments directly. Plain text, spintax, emoji, and multiple lines are supported.",
            container,
        )
        self.delivery = RangeSettings(self.CONFIG_RANGE_KEYS, container)
        self.limits = RangeSettings(self.LIMIT_KEYS, container)
        settings = ConfigurationSection("Settings", container)
        settings.body_layout.addWidget(self.comments)
        self.comments_section = self.comments
        self.comments.setVisible(include_comments)
        settings.body_layout.addWidget(self.delivery)
        settings.body_layout.addWidget(self.limits)
        layout.addWidget(settings)

        self.limit_behaviour = CheckboxGroup(self.CONFIG_BOOLEAN_KEYS, container)
        self._add_section(
            layout, "Additional Settings", self.limit_behaviour, container
        )

        self.content_filters = CheckboxGroup(self.CONTENT_FILTER_KEYS, container)
        self.source_filters = CheckboxGroup(self.SOURCE_FILTER_KEYS, container)
        filters = ConfigurationSection("Filters", container)
        filters.body_layout.addWidget(self.content_filters)
        filters.body_layout.addWidget(self.source_filters)
        layout.addWidget(filters)
        layout.addStretch()
        self.setWidget(container)

        self.method_group.buttonClicked.connect(self._method_changed)
        self.comments.changed.connect(self._changed)
        self.delivery.changed.connect(self._delivery_changed)
        self.limits.changed.connect(self._changed)
        self.limit_behaviour.changed.connect(self._changed)
        self.content_filters.changed.connect(self._changed)
        self.source_filters.changed.connect(self._changed)
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
            | set(cls.LIMIT_KEYS)
            | set(cls.CONFIG_BOOLEAN_KEYS)
            | set(cls.CONTENT_FILTER_KEYS)
            | set(cls.SOURCE_FILTER_KEYS)
            | {cls.COMMENT_RESOURCE}
        )

    def set_configuration(self, configuration: dict) -> None:
        self._syncing_method = True
        try:
            self._present_keys = self.supported_keys() & set(configuration)
            self._explicitly_disabled = False
            self._comment_file_present = self.COMMENT_RESOURCE in configuration
            self.comments.set_text(str(configuration.get(self.COMMENT_RESOURCE) or ""))
            self.delivery.set_values(configuration)
            self.limits.set_values(configuration)
            self.limit_behaviour.set_values(configuration)
            self.content_filters.set_values(configuration)
            self.source_filters.set_values(configuration)
            self.sources.set_configuration(configuration)
            percentage = self.delivery.controls["comment-percentage"].text().strip()
            if percentage not in {"", "0"}:
                self._enabled_percentage = percentage
                self.spintax_method.setChecked(True)
            else:
                self.disabled_method.setChecked(True)
            self._update_status()
        finally:
            self._syncing_method = False

    def values(self) -> dict:
        values = self.delivery.values()
        values.update(self.limits.values())
        values.update(self.limit_behaviour.values())
        values.update(self.content_filters.values())
        values.update(self.source_filters.values())
        percentage = str(values.get("comment-percentage") or "")
        if percentage and max(int(part) for part in percentage.split("-")) > 100:
            control = self.delivery.controls["comment-percentage"]
            control.setStyleSheet("border: 1px solid #EF4444;")
            control.setFocus()
            raise ValueError("Comment Percentage cannot exceed 100.")
        comments = self.comments.text()
        if (
            self.include_comments
            and self.spintax_method.isChecked()
            and not comments.strip()
        ):
            self.comments.editor.setStyleSheet("border: 1px solid #EF4444;")
            self.comments.editor.setFocus()
            raise ValueError("Add at least one comment before enabling comments.")
        self.comments.editor.setStyleSheet("")

        result = {}
        for key, value in values.items():
            populated = value not in {"", "0", 0}
            if (
                key in self._present_keys
                or populated
                or (key == "comment-percentage" and self._explicitly_disabled)
            ):
                result[key] = value
        if self.include_comments and (self._comment_file_present or comments):
            result[self.COMMENT_RESOURCE] = comments
        return result

    def _method_changed(self) -> None:
        if self._syncing_method:
            return
        percentage = self.delivery.controls["comment-percentage"]
        self._syncing_method = True
        try:
            if self.spintax_method.isChecked():
                if percentage.text().strip() in {"", "0"}:
                    percentage.setText(self._enabled_percentage)
            elif self.disabled_method.isChecked():
                if percentage.text().strip() not in {"", "0"}:
                    self._enabled_percentage = percentage.text().strip()
                percentage.setText("0")
                self._explicitly_disabled = True
        finally:
            self._syncing_method = False
        self._changed()

    def _delivery_changed(self) -> None:
        if self._syncing_method:
            return
        percentage = self.delivery.controls["comment-percentage"].text().strip()
        self._syncing_method = True
        try:
            if percentage not in {"", "0"}:
                self._enabled_percentage = percentage
                self.spintax_method.setChecked(True)
            else:
                self.disabled_method.setChecked(True)
                self._explicitly_disabled = True
        finally:
            self._syncing_method = False
        self._changed()

    def _changed(self) -> None:
        self._update_status()
        self.changed.emit()

    def _update_status(self) -> None:
        enabled = self.spintax_method.isChecked()
        self.status.setText("● Enabled" if enabled else "● Disabled")
        self.status.setStyleSheet(f"color: {'#22C55E' if enabled else '#A1A1AA'}")
