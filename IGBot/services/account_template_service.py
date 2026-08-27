import re
from pathlib import Path

import yaml
from atomicwrites import atomic_write

from IGBot.core.account_template import AccountTemplate


class AccountTemplateService:
    """Owns independent, reusable account-behaviour templates."""

    FILTER_KEYS = frozenset(
        {
            "pm_to_private_or_empty",
            "comment_photos",
            "comment_videos",
            "comment_carousels",
            "comment_hashtag_likers_top",
            "comment_hashtag_likers_recent",
            "comment_hashtag_posts_top",
            "comment_hashtag_posts_recent",
            "comment_place_likers_top",
            "comment_place_likers_recent",
            "comment_place_posts_top",
            "comment_place_posts_recent",
            "comment_blogger_followers",
            "comment_blogger_following",
            "comment_blogger_post_likers",
            "comment_blogger",
            "comment_interact_usernames",
            "comment_interact_from_file",
            "comment_feed",
        }
    )
    CONFIG_KEYS = frozenset(
        {
            "follow-percentage",
            "total-follows-limit",
            "unfollow",
            "unfollow-non-followers",
            "unfollow-any-non-followers",
            "unfollow-any-followers",
            "unfollow-any",
            "min-following",
            "sort-followers-newest-to-oldest",
            "unfollow-delay",
            "total-unfollows-limit",
            "delete-removed-followers",
            "likes-count",
            "likes-percentage",
            "total-likes-limit",
            "end-if-likes-limit-reached",
            "carousel-count",
            "carousel-percentage",
            "watch-photo-time",
            "watch-video-time",
            "stories-count",
            "stories-percentage",
            "total-watches-limit",
            "end-if-watches-limit-reached",
            "pm-percentage",
            "total-pm-limit",
            "end-if-pm-limit-reached",
            "comment-percentage",
            "total-comments-limit",
            "max-comments-pro-user",
            "end-if-comments-limit-reached",
        }
    )

    def __init__(self, templates_directory: Path) -> None:
        self.directory = templates_directory

    def list_templates(self) -> tuple[AccountTemplate, ...]:
        if not self.directory.is_dir():
            return ()
        return tuple(
            AccountTemplate(path.name, path)
            for path in sorted(
                self.directory.iterdir(), key=lambda item: item.name.casefold()
            )
            if path.is_dir() and (path / "config.yml").is_file()
        )

    def create(self, name: str) -> AccountTemplate:
        name = self._validate_name(name)
        self._ensure_unique(name)
        directory = self.directory / name
        self.directory.mkdir(parents=True, exist_ok=True)
        directory.mkdir()
        try:
            self._write_yaml(directory / "config.yml", {})
            self._write_yaml(directory / "filters.yml", {})
            return AccountTemplate(name, directory)
        except OSError:
            for filename in ("config.yml", "filters.yml"):
                path = directory / filename
                if path.is_file():
                    path.unlink()
            if directory.is_dir():
                directory.rmdir()
            raise

    def load(self, name: str) -> dict:
        template = self._find(name)
        values = self._read_yaml(template.directory / "config.yml")
        filters = self._read_yaml(template.directory / "filters.yml")
        return {
            **{key: value for key, value in values.items() if key in self.CONFIG_KEYS},
            **{key: value for key, value in filters.items() if key in self.FILTER_KEYS},
        }

    def save(self, name: str, values: dict) -> AccountTemplate:
        template = self._find(name)
        unsupported = set(values) - self.CONFIG_KEYS - self.FILTER_KEYS
        if unsupported:
            raise ValueError("The template contains account-specific settings.")
        config = {
            key: value
            for key, value in values.items()
            if key in self.CONFIG_KEYS and value not in (None, "", [])
        }
        filters = {
            key: value
            for key, value in values.items()
            if key in self.FILTER_KEYS and value not in (None, "", [])
        }
        config_path = template.directory / "config.yml"
        filters_path = template.directory / "filters.yml"
        originals = {
            config_path: config_path.read_bytes(),
            filters_path: filters_path.read_bytes(),
        }
        try:
            self._write_yaml(config_path, config)
            self._write_yaml(filters_path, filters)
            if self.load(name) != {**config, **filters}:
                raise RuntimeError("The saved template could not be verified.")
        except (OSError, RuntimeError, TypeError, yaml.YAMLError) as error:
            for path, content in originals.items():
                self._write_bytes(path, content)
            raise RuntimeError(
                "Template save failed; the original was restored."
            ) from error
        return template

    def rename(self, name: str, new_name: str) -> AccountTemplate:
        template = self._find(name)
        new_name = self._validate_name(new_name)
        if name.casefold() != new_name.casefold():
            self._ensure_unique(new_name)
        destination = self.directory / new_name
        if destination != template.directory:
            template.directory.rename(destination)
        return AccountTemplate(new_name, destination)

    def delete(self, name: str) -> None:
        template = self._find(name)
        allowed = {"config.yml", "filters.yml"}
        contents = {path.name for path in template.directory.iterdir()}
        if contents - allowed:
            raise RuntimeError("The template directory contains unexpected files.")
        for filename in allowed:
            path = template.directory / filename
            if path.is_file():
                path.unlink()
        template.directory.rmdir()

    def apply(self, name: str, account_directory: Path) -> None:
        from IGBot.services.account_assignment_service import AccountAssignmentService

        values = self.load(name)
        config_values = {
            key: value for key, value in values.items() if key in self.CONFIG_KEYS
        }
        filter_values = {
            key: value for key, value in values.items() if key in self.FILTER_KEYS
        }
        targets = {
            account_directory / "config.yml": config_values,
            account_directory / "filters.yml": filter_values,
        }
        originals = {
            path: path.read_bytes() if path.is_file() else None for path in targets
        }
        try:
            for path, additions in targets.items():
                AccountAssignmentService._update_yaml_fields(path, additions)
                verified = self._read_yaml(path)
                if any(verified.get(key) != value for key, value in additions.items()):
                    raise RuntimeError(
                        f"The applied {path.name} could not be verified."
                    )
        except (OSError, RuntimeError, TypeError, yaml.YAMLError) as error:
            for path, content in originals.items():
                if content is None:
                    if path.exists():
                        path.unlink()
                else:
                    self._write_bytes(path, content)
            raise RuntimeError(
                "Template application failed; the account was restored."
            ) from error

    def _find(self, name: str) -> AccountTemplate:
        identity = name.casefold()
        template = next(
            (
                item
                for item in self.list_templates()
                if item.name.casefold() == identity
            ),
            None,
        )
        if template is None:
            raise ValueError("The selected account template does not exist.")
        return template

    def _ensure_unique(self, name: str) -> None:
        if any(
            item.name.casefold() == name.casefold() for item in self.list_templates()
        ):
            raise ValueError("An account template with this name already exists.")

    @staticmethod
    def _validate_name(name: str) -> str:
        name = name.strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,59}", name):
            raise ValueError("Enter a valid template name.")
        return name

    @staticmethod
    def _read_yaml(path: Path) -> dict:
        if not path.is_file():
            return {}
        value = yaml.safe_load(path.read_bytes())
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise TypeError(f"{path.name} must contain a YAML mapping.")
        return value

    @staticmethod
    def _write_yaml(path: Path, value: dict) -> None:
        content = yaml.safe_dump(value, sort_keys=False, allow_unicode=True)
        with atomic_write(path, overwrite=True, encoding="utf-8", newline="") as output:
            output.write(content)

    @staticmethod
    def _write_bytes(path: Path, content: bytes) -> None:
        with atomic_write(path, overwrite=True, mode="wb") as output:
            output.write(content)
