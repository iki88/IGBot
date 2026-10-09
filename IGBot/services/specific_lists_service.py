"""Account-local username-list storage for Specific Users workflows."""

from pathlib import Path
from typing import ClassVar

import yaml


class SpecificListsService:
    SOURCE_FILES: ClassVar[dict[str, str]] = {
        "igbot-follow-sources-followers": "follow_sources_followers.txt",
        "igbot-follow-sources-following": "follow_sources_following.txt",
        "igbot-like-sources-followers": "like_sources_followers.txt",
        "igbot-story-sources-followers": "story_sources_followers.txt",
        "igbot-comment-sources-followers": "comment_sources_followers.txt",
    }
    LEGACY_SOURCE_KEYS: ClassVar[dict[str, str]] = {
        "follow_sources_followers.txt": "blogger-followers",
        "follow_sources_following.txt": "blogger-following",
        "like_sources_followers.txt": "blogger-followers",
        "story_sources_followers.txt": "blogger-followers",
        "comment_sources_followers.txt": "blogger-followers",
    }
    FILENAMES = (
        "followspecific.txt",
        "likespecific.txt",
        "dmspecific.txt",
        "commentspecific.txt",
        "unfollowspecific.txt",
        "ignore.txt",
        *SOURCE_FILES.values(),
    )

    def __init__(self, account_directory: str | Path) -> None:
        self.account_directory = Path(account_directory)
        self.directory = self.account_directory / "Lists"

    def initialize(self, *, migrate_legacy: bool = True) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        legacy = self._legacy_sources() if migrate_legacy else {}
        for filename in self.FILENAMES:
            path = self.directory / filename
            if path.exists():
                continue
            usernames = legacy.get(filename, ())
            path.write_text(
                "".join(f"{username}\n" for username in usernames), encoding="utf-8"
            )

    def source_values(self) -> dict[str, list[str]]:
        """Return module-specific source lists for runtime configuration."""
        self.initialize()
        return {
            key: self.load(filename) for key, filename in self.SOURCE_FILES.items()
        }

    def load(self, filename: str) -> list[str]:
        self._validate(filename)
        self.initialize()
        return [
            line.strip()
            for line in (self.directory / filename)
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]

    def save(self, filename: str, usernames: list[str]) -> None:
        self._validate(filename)
        self.initialize()
        content = "".join(
            f"{username.strip()}\n" for username in usernames if username.strip()
        )
        (self.directory / filename).write_text(content, encoding="utf-8")

    def _validate(self, filename: str) -> None:
        if filename not in self.FILENAMES:
            raise ValueError(f"Unsupported Specific Users list: {filename}")

    def _legacy_sources(self) -> dict[str, list[str]]:
        config_path = self.account_directory / "config.yml"
        if not config_path.is_file():
            return {}
        try:
            configuration = yaml.safe_load(config_path.read_bytes())
        except (OSError, yaml.YAMLError):
            return {}
        if not isinstance(configuration, dict):
            return {}
        migrated = {}
        for filename, key in self.LEGACY_SOURCE_KEYS.items():
            value = configuration.get(key)
            migrated[filename] = (
                [str(username).strip() for username in value if str(username).strip()]
                if isinstance(value, list)
                else []
            )
        return migrated
