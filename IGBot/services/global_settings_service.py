"""Canonical persistence for application-wide IGBot settings."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import ClassVar

from atomicwrites import atomic_write


class GlobalSettingsService:
    """Load and atomically save the single global settings document."""

    FILE_NAME = "global_settings.json"
    DEFAULTS: ClassVar[dict[str, object]] = {
        "start_all_phones_delay": 0,
        "wait_after_launching_instagram": "",
        "login_retry_limit_per_day": 0,
        "enable_block_detection": False,
        "pause_after_action_block": 0,
        "maximum_crash_retries": 0,
        "toggle_airplane_mode_between_sessions": False,
        "use_random_search_letters": False,
        "first_character_pool": "abcdefghijklmnopqrstuvwxyz",
        "second_character_pool": "aeiou",
        "maximum_source_scrolling_time": 0,
        "enable_follow_back_ratio_check": True,
        "maximum_follows_per_hour": 0,
        "maximum_unfollows_per_hour": 0,
        "maximum_likes_per_hour": 0,
        "maximum_comments_per_hour": 0,
        "maximum_dms_per_hour": 0,
        "maximum_story_views_per_hour": 0,
        "enable_contact_details_scraping": False,
        "ai_provider": "openai",
        "ai_model": "",
        "openai_api_key": "",
        "temperature": 0.0,
        "backend_api_enabled": False,
    }

    def __init__(self, workspace: Path) -> None:
        self.path = workspace / self.FILE_NAME

    def load(self) -> dict[str, object]:
        """Return defaults overlaid with valid persisted setting names."""

        settings = dict(self.DEFAULTS)
        if not self.path.is_file():
            return settings
        try:
            persisted = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError(f"Could not load Global Settings: {error}") from error
        if not isinstance(persisted, dict):
            raise TypeError("Global Settings must contain a JSON object.")
        settings.update(
            {key: persisted[key] for key in self.DEFAULTS.keys() & persisted.keys()}
        )
        return settings

    def save(self, settings: Mapping[str, object]) -> dict[str, object]:
        """Atomically persist and verify one complete canonical snapshot."""

        unknown = set(settings) - self.DEFAULTS.keys()
        missing = self.DEFAULTS.keys() - set(settings)
        if unknown or missing:
            raise ValueError(
                "Global Settings must contain the complete canonical schema."
            )
        snapshot = dict(settings)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with atomic_write(
                self.path, overwrite=True, encoding="utf-8", newline=""
            ) as output:
                json.dump(
                    snapshot, output, ensure_ascii=False, indent=2, sort_keys=True
                )
                output.write("\n")
            verified = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError(f"Could not save Global Settings: {error}") from error
        if verified != snapshot:
            raise RuntimeError("The saved Global Settings could not be verified.")
        return snapshot

    def runtime_settings(self) -> Mapping[str, object]:
        """Return a persisted snapshot for runtime context construction."""

        return self.load()
