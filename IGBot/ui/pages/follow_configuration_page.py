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
    CollapsibleSection,
    NumericSettings,
)


class FollowConfigurationPage(QScrollArea):
    changed = Signal()

    KEYS: ClassVar[dict[str, str]] = {
        "enabled": "enabled",
        "followers": "method-followers",
        "likers": "method-likers",
        "specific": "method-specific-users",
        "keyword": "method-keyword-search",
        "visit": "visit-profile",
        "scroll": "scroll-profile",
        "like_posts": "like-random-posts",
        "minimum": "minimum",
        "maximum": "maximum",
        "daily": "daily-limit",
        "auto_increment": "auto-increment",
        "increment": "increment-amount",
        "warmup": "maximum-warmup-limit",
        "min_delay": "minimum-delay",
        "max_delay": "maximum-delay",
        "blacklist": "skip-blacklisted",
        "whitelist": "respect-whitelist",
        "processed": "skip-previously-processed",
        "word_filter": "filter-word-search",
    }

    def __init__(self, parent=None, include_sources: bool = True) -> None:
        super().__init__(parent)
        self._loading = False
        self._limit_present = False
        self._limit_edited = False
        self.setWidgetResizable(True)
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 14, 12, 14)
        layout.setSpacing(12)

        section = CollapsibleSection("Follow", container)
        row = QHBoxLayout()
        self.enabled = QCheckBox("Enable Follow", section)
        self.enabled.setObjectName("configurationSwitch")
        self.status = QLabel("● Disabled", section)
        self.enabled.toggled.connect(self._enabled_changed)
        row.addWidget(self.enabled)
        row.addStretch()
        row.addWidget(self.status)
        section.body_layout.addLayout(row)
        layout.addWidget(section)

        self.behaviour = CheckboxGroup(
            {
                self.KEYS["visit"]: "Visit Target Profile",
                self.KEYS["scroll"]: "Scroll Profile",
                self.KEYS["like_posts"]: "Like Random Posts",
            },
            container,
        )
        self.limits = NumericSettings(
            {
                self.KEYS["minimum"]: "Minimum",
                self.KEYS["maximum"]: "Maximum",
                self.KEYS["daily"]: "Daily Limit",
                self.KEYS["increment"]: "Increment Amount",
                self.KEYS["warmup"]: "Maximum Warmup Limit",
                self.KEYS["min_delay"]: "Minimum Delay",
                self.KEYS["max_delay"]: "Maximum Delay",
            },
            container,
        )
        self.auto_increment = QCheckBox("Auto Increment", container)
        self.auto_increment.setObjectName("configurationSwitch")
        self.safety = CheckboxGroup(
            {
                self.KEYS["blacklist"]: "Skip Blacklisted Users",
                self.KEYS["whitelist"]: "Respect Whitelist",
                self.KEYS["processed"]: "Skip Previously Processed",
                self.KEYS["word_filter"]: "Filter Word Search",
            },
            container,
        )
        for title, widget in (
            ("Behaviour", self.behaviour),
            ("Limits", self.limits),
            ("Additional Settings", self.safety),
        ):
            section = CollapsibleSection(title, container)
            section.body_layout.addWidget(widget)
            if title == "Limits":
                section.body_layout.addWidget(self.auto_increment)
            layout.addWidget(section)
        self.sources = AudienceSourcesPage(container)
        self.sources.setObjectName("moduleSources")
        self.sources.setVisible(include_sources)
        layout.addWidget(self.sources)
        layout.addStretch()
        self.setWidget(container)
        self.behaviour.changed.connect(self.changed)
        self.limits.changed.connect(self._limits_changed)
        self.safety.changed.connect(self.changed)
        self.auto_increment.toggled.connect(self.changed)
        self.sources.changed.connect(self.changed)

    def _enabled_changed(self, enabled: bool) -> None:
        self.status.setText("● Enabled" if enabled else "● Disabled")
        self.status.setStyleSheet(f"color: {'#22C55E' if enabled else '#A1A1AA'}")
        self.changed.emit()

    def set_configuration(self, configuration: dict) -> None:
        self._loading = True
        self._limit_present = "total-follows-limit" in configuration
        self._limit_edited = False
        self.enabled.setChecked(
            str(configuration.get("follow-percentage") or "0") not in {"", "0"}
        )
        self.behaviour.set_values({})
        self.auto_increment.setChecked(False)
        self.safety.set_values({})
        limits = {key: 0 for key in self.limits.controls}
        total_limit = str(configuration.get("total-follows-limit") or "0")
        parts = total_limit.split("-", 1)
        try:
            limits[self.KEYS["minimum"]] = int(parts[0])
            limits[self.KEYS["maximum"]] = int(parts[-1])
        except ValueError:
            limits[self.KEYS["minimum"]] = 0
            limits[self.KEYS["maximum"]] = 0
        self.limits.set_values(limits)
        self.sources.set_configuration(configuration)
        self._loading = False

    def values(self) -> dict:
        values = self.limits.values()
        minimum, maximum = values[self.KEYS["minimum"]], values[self.KEYS["maximum"]]
        min_delay, max_delay = (
            values[self.KEYS["min_delay"]],
            values[self.KEYS["max_delay"]],
        )
        if minimum > maximum:
            raise ValueError("Minimum follows cannot exceed maximum follows.")
        if min_delay > max_delay:
            raise ValueError("Minimum delay cannot exceed maximum delay.")
        total_limit = str(minimum) if minimum == maximum else f"{minimum}-{maximum}"
        if not self._limit_present and not self._limit_edited:
            return {"follow-percentage": "1" if self.enabled.isChecked() else "0"}
        return {
            "total-follows-limit": total_limit,
            "follow-percentage": "1" if self.enabled.isChecked() else "0",
        }

    def _limits_changed(self) -> None:
        if not self._loading:
            self._limit_edited = True
            self.changed.emit()
