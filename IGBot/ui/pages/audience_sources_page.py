import re
from typing import ClassVar

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from IGBot.ui.widgets.configuration_widgets import CollapsibleSection
from IGBot.ui.widgets.target_editor_dialog import TargetEditorDialog
from IGBot.ui.widgets.target_source_row import TargetSourceRow


class AudienceSourcesPage(QWidget):
    """Compact reusable module source controls backed by the target editor."""

    changed = Signal()
    PRIORITY_SOURCES: ClassVar[dict[str, str]] = {
        "blogger-followers": "Follow User's Followers",
        "blogger-following": "Follow User's Followings",
        "blogger": "Follow Specific Users",
    }
    ADVANCED_SOURCES: ClassVar[dict[str, str]] = {
        "blogger-post-likers": "Blogger Post Likers",
        "hashtag-likers-top": "Top Hashtag Likers",
        "hashtag-likers-recent": "Recent Hashtag Likers",
        "hashtag-posts-top": "Top Hashtag Posts",
        "hashtag-posts-recent": "Recent Hashtag Posts",
        "place-likers-top": "Top Place Likers",
        "place-likers-recent": "Recent Place Likers",
        "place-posts-top": "Top Place Posts",
        "place-posts-recent": "Recent Place Posts",
    }
    USERNAME_KEYS = frozenset(
        {"blogger-followers", "blogger-following", "blogger", "blogger-post-likers"}
    )

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._loading = False
        self._present_keys: set[str] = set()
        self.rows: dict[str, TargetSourceRow] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        priority = CollapsibleSection("Method", self)
        for key, label in self.PRIORITY_SOURCES.items():
            priority.body_layout.addWidget(self._create_row(key, label, priority))
        layout.addWidget(priority)

        advanced = CollapsibleSection("Advanced Sources", self)
        for key, label in self.ADVANCED_SOURCES.items():
            advanced.body_layout.addWidget(self._create_row(key, label, advanced))
        layout.addWidget(advanced)

    @classmethod
    def supported_keys(cls) -> set[str]:
        return set(cls.PRIORITY_SOURCES) | set(cls.ADVANCED_SOURCES)

    def _create_row(self, key: str, label: str, parent: QWidget) -> TargetSourceRow:
        row = TargetSourceRow(label, parent)
        row.changed.connect(self._changed)
        row.edit_requested.connect(lambda key=key: self._edit_source(key))
        self.rows[key] = row
        return row

    def set_configuration(self, configuration: dict) -> None:
        self._loading = True
        try:
            self._present_keys = self.supported_keys() & set(configuration)
            for key, row in self.rows.items():
                value = configuration.get(key)
                entries = value if isinstance(value, list) else []
                row.set_entries(entries)
                row.enabled.setChecked(bool(entries))
        finally:
            self._loading = False

    def values(self) -> dict:
        values = {}
        for key, row in self.rows.items():
            entries = row.entries()
            if row.enabled.isChecked():
                if not entries:
                    row.name.setStyleSheet("border: 1px solid #EF4444;")
                    row.name.setFocus()
                    raise ValueError(f"Add at least one target for {row.name.text()}.")
                row.name.setStyleSheet("")
                values[key] = entries
            elif key in self._present_keys:
                values[key] = None
        return values

    def state_values(self) -> dict:
        """Return editor state without validation for synchronizing module views."""
        return {
            key: row.entries() if row.enabled.isChecked() else None
            for key, row in self.rows.items()
            if row.enabled.isChecked() or key in self._present_keys
        }

    def _edit_source(self, key: str) -> None:
        row = self.rows[key]
        dialog = TargetEditorDialog(
            row.name.text(), row.entries(), self._validator_for(key), self
        )
        if dialog.exec() == TargetEditorDialog.Accepted:
            entries = dialog.entries()
            row.set_entries(entries)
            row.enabled.setChecked(bool(entries))
            self._changed()

    def _validator_for(self, key: str):
        if key in self.USERNAME_KEYS:
            return lambda entry: bool(re.fullmatch(r"[A-Za-z0-9._]{1,30}", entry))
        if key.startswith("hashtag-"):
            return lambda entry: bool(re.fullmatch(r"#?[\w.]+", entry, re.UNICODE))
        return lambda entry: bool(entry.strip()) and len(entry) <= 200

    def _changed(self) -> None:
        if not self._loading:
            self.changed.emit()
