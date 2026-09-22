import re
from pathlib import Path
from typing import ClassVar

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from IGBot.services.specific_lists_service import SpecificListsService
from IGBot.ui.widgets.configuration_widgets import ConfigurationSection
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

    def __init__(
        self,
        parent=None,
        include_advanced: bool = True,
        section_title: str = "Method",
        switch_style: bool = True,
    ) -> None:
        super().__init__(parent)
        self._loading = False
        self._present_keys: set[str] = set()
        self._hidden_values: dict[str, list[str] | None] = {}
        self.rows: dict[str, TargetSourceRow] = {}
        self._specific_lists: SpecificListsService | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        method = ConfigurationSection(section_title, self)
        sources = dict(self.PRIORITY_SOURCES)
        if include_advanced:
            sources.update(self.ADVANCED_SOURCES)
        for key, label in sources.items():
            method.body_layout.addWidget(
                self._create_row(key, label, method, switch_style=switch_style)
            )
        layout.addWidget(method)

    @classmethod
    def supported_keys(cls) -> set[str]:
        return set(cls.PRIORITY_SOURCES) | set(cls.ADVANCED_SOURCES)

    def _create_row(
        self,
        key: str,
        label: str,
        parent: QWidget,
        *,
        switch_style: bool,
    ) -> TargetSourceRow:
        row = TargetSourceRow(label, parent, switch_style=switch_style)
        row.changed.connect(self._changed)
        row.edit_requested.connect(lambda key=key: self._edit_source(key))
        self.rows[key] = row
        return row

    def set_configuration(self, configuration: dict) -> None:
        self._loading = True
        try:
            self._present_keys = self.supported_keys() & set(configuration)
            self._hidden_values = {
                key: configuration.get(key)
                for key in self.supported_keys() - set(self.rows)
                if key in configuration
            }
            for key, row in self.rows.items():
                value = configuration.get(key)
                entries = value if isinstance(value, list) else []
                if (
                    key == "blogger"
                    and entries
                    and self._specific_lists is not None
                    and not self._specific_lists.load("followspecific.txt")
                ):
                    self._specific_lists.save("followspecific.txt", entries)
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
        values = dict(self._hidden_values)
        values.update(
            {
                key: row.entries() if row.enabled.isChecked() else None
                for key, row in self.rows.items()
                if row.enabled.isChecked() or key in self._present_keys
            }
        )
        return values

    def _edit_source(self, key: str) -> None:
        row = self.rows[key]
        if key == "blogger" and self._specific_lists is not None:
            row.set_entries(self._specific_lists.load("followspecific.txt"))
        dialog = TargetEditorDialog(
            row.name.text(), row.entries(), self._validator_for(key), self
        )
        if dialog.exec() == TargetEditorDialog.Accepted:
            entries = dialog.entries()
            row.set_entries(entries)
            if key == "blogger" and self._specific_lists is not None:
                self._specific_lists.save("followspecific.txt", entries)
            row.enabled.setChecked(bool(entries))
            self._changed()

    def set_account_directory(self, directory: str | Path) -> None:
        account_directory = Path(directory)
        if not (account_directory / "config.yml").is_file():
            self._specific_lists = None
            return
        self._specific_lists = SpecificListsService(account_directory)
        self._specific_lists.initialize()

    def _validator_for(self, key: str):
        if key in self.USERNAME_KEYS:
            return lambda entry: bool(re.fullmatch(r"[A-Za-z0-9._]{1,30}", entry))
        if key.startswith("hashtag-"):
            return lambda entry: bool(re.fullmatch(r"#?[\w.]+", entry, re.UNICODE))
        return lambda entry: bool(entry.strip()) and len(entry) <= 200

    def _changed(self) -> None:
        if not self._loading:
            self.changed.emit()
