import re
from pathlib import Path
from typing import ClassVar

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
            "skip_following",
            "skip_follower",
            "skip_if_private",
            "skip_business",
            "follow_only_business",
            "skip_if_link_in_bio",
            "follow_only_link_in_bio",
            "follow_private_or_empty",
            "follow_only_private",
            "min_followers",
            "max_followers",
            "min_followings",
            "max_followings",
            "min_posts",
            "min_likers",
            "max_likers",
            "mutual_friends",
            "min_potency_ratio",
            "max_potency_ratio",
            "blacklist_words",
            "mandatory_words",
            "specific_alphabet",
            "biography_language",
        }
    )
    CONFIG_KEYS = frozenset(
        {
            "igbot-template-follow-methods",
            "igbot-template-like-methods",
            "igbot-follow-mute-after-follow",
            "igbot-follow-only-active-stories",
            "igbot-follow-auto-increment-enabled",
            "igbot-follow-auto-increment-by",
            "igbot-follow-auto-increment-maximum",
            "igbot-unfollow-enabled",
            "igbot-unfollow-method",
            "igbot-unfollow-sort",
            "igbot-unfollow-budget",
            "igbot-unfollow-action-delay",
            "igbot-unfollow-auto-increment-enabled",
            "igbot-unfollow-auto-increment-by",
            "igbot-unfollow-auto-increment-maximum",
            "igbot-like-budget",
            "igbot-like-action-delay",
            "igbot-like-auto-increment-enabled",
            "igbot-like-auto-increment-by",
            "igbot-like-auto-increment-maximum",
            "igbot-dm-method",
            "igbot-dm-budget",
            "igbot-dm-action-delay",
            "follow-percentage",
            "follow-limit",
            "total-follows-limit",
            "end-if-follows-limit-reached",
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
            "delete-interacted-users",
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
    METHOD_CONFIG_KEYS = frozenset(
        {
            "igbot-template-follow-methods",
            "igbot-template-like-methods",
            "igbot-unfollow-method",
            "igbot-dm-method",
        }
    )
    RUNTIME_EXTENSION_KEYS: ClassVar[dict[str, tuple[str, str]]] = {
        "igbot-follow-mute-after-follow": ("follow", "mute_after_follow"),
        "igbot-follow-only-active-stories": ("follow", "only_active_stories"),
        "igbot-follow-auto-increment-enabled": (
            "follow",
            "auto_increment_enabled",
        ),
        "igbot-follow-auto-increment-by": ("follow", "auto_increment_by"),
        "igbot-follow-auto-increment-maximum": (
            "follow",
            "auto_increment_maximum",
        ),
        "igbot-unfollow-enabled": ("unfollow", "enabled"),
        "igbot-unfollow-method": ("unfollow", "method"),
        "igbot-unfollow-sort": ("unfollow", "sort"),
        "igbot-unfollow-budget": ("unfollow", "budget"),
        "igbot-unfollow-action-delay": ("unfollow", "action_delay"),
        "igbot-unfollow-auto-increment-enabled": (
            "unfollow",
            "auto_increment_enabled",
        ),
        "igbot-unfollow-auto-increment-by": ("unfollow", "auto_increment_by"),
        "igbot-unfollow-auto-increment-maximum": (
            "unfollow",
            "auto_increment_maximum",
        ),
        "igbot-like-budget": ("like", "budget"),
        "igbot-like-action-delay": ("like", "action_delay"),
        "igbot-like-auto-increment-enabled": (
            "like",
            "auto_increment_enabled",
        ),
        "igbot-like-auto-increment-by": ("like", "auto_increment_by"),
        "igbot-like-auto-increment-maximum": (
            "like",
            "auto_increment_maximum",
        ),
        "igbot-dm-method": ("dm", "method"),
        "igbot-dm-budget": ("dm", "budget"),
        "igbot-dm-action-delay": ("dm", "action_delay"),
    }
    ALWAYS_PERSIST_CONFIG_KEYS = METHOD_CONFIG_KEYS | frozenset(RUNTIME_EXTENSION_KEYS)
    RUNTIME_EXTENSION_DEFAULTS: ClassVar[dict[str, object]] = {
        "igbot-follow-mute-after-follow": False,
        "igbot-follow-only-active-stories": False,
        "igbot-follow-auto-increment-enabled": False,
        "igbot-follow-auto-increment-by": "1",
        "igbot-follow-auto-increment-maximum": "",
        "igbot-unfollow-enabled": False,
        "igbot-unfollow-method": "",
        "igbot-unfollow-sort": "default",
        "igbot-unfollow-budget": "1",
        "igbot-unfollow-action-delay": "0",
        "igbot-unfollow-auto-increment-enabled": False,
        "igbot-unfollow-auto-increment-by": "1",
        "igbot-unfollow-auto-increment-maximum": "",
        "igbot-like-budget": "0",
        "igbot-like-action-delay": "0",
        "igbot-like-auto-increment-enabled": False,
        "igbot-like-auto-increment-by": "1",
        "igbot-like-auto-increment-maximum": "",
        "igbot-dm-method": "new-followers",
        "igbot-dm-budget": "1",
        "igbot-dm-action-delay": "0",
    }
    METHOD_DEFAULTS: ClassVar[dict[str, object]] = {
        "igbot-template-follow-methods": [],
        "igbot-template-like-methods": [],
    }

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
        self._validate_methods(values)
        self._validate_runtime_extensions(values)
        config = {
            key: self._config_default(key)
            for key in self.CONFIG_KEYS
            if key not in self.METHOD_CONFIG_KEYS or key in values
        }
        config.update(
            {key: value for key, value in values.items() if key in self.CONFIG_KEYS}
        )
        filters = {key: None for key in self.FILTER_KEYS}
        filters.update(
            {key: value for key, value in values.items() if key in self.FILTER_KEYS}
        )
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
        from IGBot.services.account_metadata_service import AccountMetadataService
        from IGBot.services.specific_lists_service import SpecificListsService

        values = self.load(name)
        has_source_methods = any(
            key in values
            for key in (
                "igbot-template-follow-methods",
                "igbot-template-like-methods",
            )
        )
        follow_methods = set(values.pop("igbot-template-follow-methods", ()) or ())
        like_methods = set(values.pop("igbot-template-like-methods", ()) or ())
        runtime_extension_values = {
            key: values.pop(key, default)
            for key, default in self.RUNTIME_EXTENSION_DEFAULTS.items()
        }
        runtime_extension_values["igbot-follow-methods"] = sorted(follow_methods)
        runtime_extension_values["igbot-like-methods"] = sorted(like_methods)
        account_config_keys = (
            self.CONFIG_KEYS
            - self.METHOD_CONFIG_KEYS
            - frozenset(self.RUNTIME_EXTENSION_KEYS)
        )
        config_values = {key: None for key in account_config_keys}
        config_values.update(
            {key: value for key, value in values.items() if key in account_config_keys}
        )
        filter_values = {key: None for key in self.FILTER_KEYS}
        filter_values.update(
            {key: value for key, value in values.items() if key in self.FILTER_KEYS}
        )
        targets = {
            account_directory / "config.yml": config_values,
            account_directory / "filters.yml": filter_values,
        }
        originals = {
            path: path.read_bytes() if path.is_file() else None for path in targets
        }
        metadata_service = AccountMetadataService()
        metadata_path = account_directory / metadata_service.FILE_NAME
        original_metadata = (
            metadata_path.read_bytes() if metadata_path.is_file() else None
        )
        try:
            current_config = self._read_yaml(account_directory / "config.yml")
            selected_sources = follow_methods | like_methods
            for source in ("blogger-followers", "blogger-following", "blogger"):
                if has_source_methods and source not in selected_sources:
                    config_values[source] = None
            if (
                has_source_methods
                and "blogger" in selected_sources
                and not current_config.get("blogger")
            ):
                lists = SpecificListsService(account_directory)
                filenames = []
                if "blogger" in follow_methods:
                    filenames.append("followspecific.txt")
                if "blogger" in like_methods:
                    filenames.append("likespecific.txt")
                usernames = []
                for filename in filenames:
                    usernames = lists.load(filename)
                    if usernames:
                        break
                if usernames:
                    config_values["blogger"] = usernames
            for path, additions in targets.items():
                AccountAssignmentService._update_yaml_fields(path, additions)
                verified = self._read_yaml(path)
                if any(verified.get(key) != value for key, value in additions.items()):
                    raise RuntimeError(
                        f"The applied {path.name} could not be verified."
                    )
            metadata = metadata_service.load(account_directory)
            extensions = dict(metadata.get("runtime_extensions") or {})
            for key, value in runtime_extension_values.items():
                if key == "igbot-follow-methods":
                    module, field = "follow", "methods"
                elif key == "igbot-like-methods":
                    module, field = "like", "methods"
                else:
                    module, field = self.RUNTIME_EXTENSION_KEYS[key]
                extension = dict(extensions.get(module) or {})
                extension[field] = value
                extensions[module] = extension
            metadata_service.save(
                account_directory,
                str(
                    metadata.get("username")
                    or current_config.get("username")
                    or account_directory.name
                ),
                str(metadata.get("password") or ""),
                str(
                    metadata.get("assigned_device_id")
                    or current_config.get("device")
                    or ""
                ),
                tag=str(metadata.get("tag") or ""),
                runtime_extensions=extensions,
            )
        except (OSError, RuntimeError, TypeError, yaml.YAMLError) as error:
            for path, content in originals.items():
                if content is None:
                    if path.exists():
                        path.unlink()
                else:
                    self._write_bytes(path, content)
            AccountMetadataService.restore(metadata_path, original_metadata)
            raise RuntimeError(
                "Template application failed; the account was restored."
            ) from error

    @staticmethod
    def _validate_methods(values: dict) -> None:
        method_sets = {
            "igbot-template-follow-methods": {
                "blogger-followers",
                "blogger-following",
                "blogger",
            },
            "igbot-template-like-methods": {"blogger-followers", "blogger"},
        }
        for key, allowed in method_sets.items():
            methods = values.get(key, [])
            if not isinstance(methods, list) or any(method not in allowed for method in methods):
                raise ValueError(f"{key} contains an unsupported method.")
        if values.get("igbot-unfollow-method", "") not in {
            "",
            "search",
            "following-list-search",
            "specific-users",
            "all-followings",
        }:
            raise ValueError("The template contains an unsupported Unfollow method.")
        if values.get("igbot-dm-method", "new-followers") not in {
            "new-followers",
            "specific-users",
        }:
            raise ValueError("The template contains an unsupported DM method.")

    @classmethod
    def _config_default(cls, key: str) -> object:
        if key in cls.METHOD_DEFAULTS:
            return cls.METHOD_DEFAULTS[key]
        if key in cls.RUNTIME_EXTENSION_DEFAULTS:
            return cls.RUNTIME_EXTENSION_DEFAULTS[key]
        return None

    @staticmethod
    def _validate_runtime_extensions(values: dict) -> None:
        boolean_keys = {
            "igbot-follow-mute-after-follow",
            "igbot-follow-only-active-stories",
            "igbot-follow-auto-increment-enabled",
            "igbot-unfollow-enabled",
            "igbot-unfollow-auto-increment-enabled",
            "igbot-like-auto-increment-enabled",
        }
        for key in boolean_keys & values.keys():
            if type(values[key]) is not bool:
                raise ValueError(f"{key} must be a switch value.")
        if values.get("igbot-unfollow-sort", "default") not in {
            "default",
            "latest",
            "earliest",
        }:
            raise ValueError("The template contains an unsupported Unfollow sort.")
        range_keys = {
            "igbot-unfollow-budget",
            "igbot-unfollow-action-delay",
            "igbot-like-budget",
            "igbot-like-action-delay",
            "igbot-dm-budget",
            "igbot-dm-action-delay",
        }
        for key in range_keys & values.keys():
            value = str(values[key])
            if not re.fullmatch(r"\d+(?:-\d+)?", value):
                raise ValueError(f"{key} must be a number or ascending range.")
            if "-" in value:
                minimum, maximum = (int(part) for part in value.split("-", 1))
                if minimum > maximum:
                    raise ValueError(f"{key} must be an ascending range.")
        for module in ("follow", "unfollow", "like"):
            prefix = f"igbot-{module}-auto-increment"
            increment_key = f"{prefix}-by"
            maximum_key = f"{prefix}-maximum"
            if increment_key in values and not re.fullmatch(
                r"[1-9]\d*", str(values[increment_key])
            ):
                raise ValueError(f"{increment_key} must be a positive integer.")
            if maximum_key in values:
                maximum = str(values[maximum_key])
                if maximum and not re.fullmatch(r"\d+(?:-\d+)?", maximum):
                    raise ValueError(
                        f"{maximum_key} must be a number or ascending range."
                    )
                if "-" in maximum:
                    lower, upper = (int(part) for part in maximum.split("-", 1))
                    if lower > upper:
                        raise ValueError(f"{maximum_key} must be an ascending range.")

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
