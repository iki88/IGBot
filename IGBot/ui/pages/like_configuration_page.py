from typing import ClassVar

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from IGBot.ui.pages.audience_sources_page import AudienceSourcesPage
from IGBot.ui.widgets.configuration_widgets import (
    CheckboxGroup,
    ConfigurationSection,
    RangeSettings,
    TextListSettings,
)


class LikeConfigurationPage(QScrollArea):
    """Configuration-only interface for documented engine Like settings."""

    changed = Signal()
    INTERACTION_KEYS: ClassVar[dict[str, str]] = {
        "likes-count": "Likes per Profile",
        "likes-percentage": "Like Percentage",
    }
    LIMIT_KEYS: ClassVar[dict[str, str]] = {
        "total-likes-limit": "Total Likes Limit",
    }
    MEDIA_KEYS: ClassVar[dict[str, str]] = {
        "carousel-count": "Carousel Photos",
        "carousel-percentage": "Carousel Percentage",
        "watch-photo-time": "Photo Watch Time (seconds)",
        "watch-video-time": "Video/Reel Watch Time (seconds)",
    }
    BOOLEAN_KEYS: ClassVar[dict[str, str]] = {
        "end-if-likes-limit-reached": "End Session when Like Limit is Reached",
    }
    LIST_KEYS: ClassVar[dict[str, str]] = {
        "posts-from-file": "Post URL Files",
    }

    def __init__(
        self,
        parent=None,
        include_file_targets: bool = True,
        include_sources: bool = True,
    ) -> None:
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
        row.addWidget(QLabel("Engine configuration status", overview))
        row.addStretch()
        self.status = QLabel("● Disabled", overview)
        row.addWidget(self.status)
        overview.body_layout.addLayout(row)
        layout.addWidget(overview)

        self.sources = AudienceSourcesPage(container)
        self.sources.setVisible(include_sources)
        layout.addWidget(self.sources)

        self.interaction = RangeSettings(self.INTERACTION_KEYS, container)
        self.limits = RangeSettings(self.LIMIT_KEYS, container)
        settings = ConfigurationSection("Settings", container)
        settings.body_layout.addWidget(self.interaction)
        settings.body_layout.addWidget(self.limits)
        layout.addWidget(settings)

        self.limit_behaviour = CheckboxGroup(self.BOOLEAN_KEYS, container)
        self.media = RangeSettings(self.MEDIA_KEYS, container)
        self.files = TextListSettings(self.LIST_KEYS, container)
        additional = ConfigurationSection("Additional Settings", container)
        additional.body_layout.addWidget(self.limit_behaviour)
        additional.body_layout.addWidget(self.media)
        additional.body_layout.addWidget(self.files)
        self.files_section = self.files
        self.files.setVisible(include_file_targets)
        layout.addWidget(additional)
        layout.addStretch()
        self.setWidget(container)

        for widget in (
            self.interaction,
            self.limits,
            self.limit_behaviour,
            self.media,
            self.files,
        ):
            widget.changed.connect(self._changed)
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
            set(cls.INTERACTION_KEYS)
            | set(cls.LIMIT_KEYS)
            | set(cls.MEDIA_KEYS)
            | set(cls.BOOLEAN_KEYS)
            | set(cls.LIST_KEYS)
        )

    def set_configuration(self, configuration: dict) -> None:
        self._present_keys = self.supported_keys() & set(configuration)
        self.interaction.set_values(configuration)
        self.limits.set_values(configuration)
        self.limit_behaviour.set_values(configuration)
        self.media.set_values(configuration)
        self.files.set_values(configuration)
        self.sources.set_configuration(configuration)
        self._update_status()

    def values(self) -> dict:
        values = self.interaction.values()
        values.update(self.limits.values())
        values.update(self.limit_behaviour.values())
        values.update(self.media.values())
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
            for control in self.interaction.controls.values()
        ) or any(
            control.toPlainText().strip() for control in self.files.controls.values()
        )
        self.status.setText("● Enabled" if enabled else "● Disabled")
        self.status.setStyleSheet(f"color: {'#22C55E' if enabled else '#A1A1AA'}")
