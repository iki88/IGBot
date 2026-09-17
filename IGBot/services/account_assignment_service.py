import json
import logging
import re
import shutil
from pathlib import Path

import yaml
from atomicwrites import atomic_write
from yaml.nodes import MappingNode

from IGBot.core.device import AssignedAccount
from IGBot.services.account_identity import (
    AccountDirectoryKind,
    AccountIdentityCatalog,
    OrphanedAccount,
)
from IGBot.services.account_metadata_service import AccountMetadataService

logger = logging.getLogger(__name__)


class AccountAssignmentService:
    """Manages phone assignments in InstaAddict account configurations."""

    FILTER_SETTING_KEYS = frozenset(
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
            "skip_if_link_in_bio",
            "follow_private_or_empty",
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
    OBSOLETE_FOLLOW_FILTER_KEYS = frozenset(
        {"skip_non_business", "biography_banned_language"}
    )
    TEXT_RESOURCE_NAMES = frozenset(
        {
            "pm_list.txt",
            "comments_list.txt",
            "unfollow_users.txt",
            "remove_followers_users.txt",
        }
    )
    AUDIENCE_SOURCE_KEYS = frozenset(
        {
            "blogger",
            "blogger-followers",
            "blogger-following",
            "blogger-post-likers",
            "hashtag-likers-top",
            "hashtag-likers-recent",
            "hashtag-posts-top",
            "hashtag-posts-recent",
            "place-likers-top",
            "place-likers-recent",
            "place-posts-top",
            "place-posts-recent",
        }
    )

    def __init__(self, accounts_directory: Path) -> None:
        self._accounts_directory = accounts_directory
        self.metadata = AccountMetadataService()
        self.identities = AccountIdentityCatalog(accounts_directory)

    @property
    def accounts_directory(self) -> Path:
        """Return the centralized root used to locate account configurations."""
        return self._accounts_directory

    def load_by_device(self) -> dict[str, tuple[AssignedAccount, ...]]:
        assignments: dict[str, list[AssignedAccount]] = {}
        for account in self.identities.discover():
            if not account.device_id:
                continue
            assignments.setdefault(account.device_id, []).append(account)

        return {
            device_id: tuple(accounts) for device_id, accounts in assignments.items()
        }

    def orphaned_accounts(self) -> tuple[OrphanedAccount, ...]:
        """Return recoverable account data directories missing ``config.yml``."""

        return self.identities.orphans()

    def load_configuration(self, config_path: Path) -> dict:
        """Read an existing account configuration without changing its representation."""
        configuration = yaml.safe_load(config_path.read_bytes())
        if not isinstance(configuration, dict):
            raise TypeError("The account configuration must contain a YAML mapping.")
        metadata = self.metadata.load(config_path.parent)
        if metadata:
            configuration = dict(configuration)
            configuration["username"] = str(
                configuration.get("username")
                or metadata.get("username")
                or config_path.parent.name
            )
            configuration["password"] = str(metadata.get("password") or "")
            configuration["tag"] = str(metadata.get("tag") or "")
            runtime_extensions = metadata.get("runtime_extensions")
            if isinstance(runtime_extensions, dict):
                follow_extensions = runtime_extensions.get("follow")
                if isinstance(follow_extensions, dict):
                    configuration["igbot-follow-mute-after-follow"] = bool(
                        follow_extensions.get("mute_after_follow")
                    )
        filters_path = config_path.parent / "filters.yml"
        if filters_path.is_file():
            filters = yaml.safe_load(filters_path.read_bytes())
            if isinstance(filters, dict):
                configuration.update(
                    {
                        key: filters[key]
                        for key in self.FILTER_SETTING_KEYS
                        if key in filters
                    }
                )
        for resource_name in self.TEXT_RESOURCE_NAMES:
            resource_path = config_path.parent / resource_name
            if resource_path.is_file():
                configuration[resource_name] = resource_path.read_text(encoding="utf-8")
        return configuration

    def update_configuration(
        self,
        account: AssignedAccount,
        username: str,
        password: str,
        app_id: str,
        settings: dict | None = None,
        tag: str | None = None,
    ) -> AssignedAccount:
        """Atomically update account fields while preserving YAML layout and comments."""
        username = username.strip()
        app_id = app_id.strip()
        if not re.fullmatch(r"[A-Za-z0-9._]{1,30}", username):
            raise ValueError("Enter a valid Instagram username.")
        if not password:
            raise ValueError("An account password is required.")

        config_path = account.config_path
        root = self._accounts_directory.resolve()
        if config_path.resolve().parent.parent != root or not config_path.is_file():
            raise ValueError(
                "The account configuration is outside the managed accounts."
            )
        original = config_path.read_bytes()
        metadata_path = config_path.parent / self.metadata.FILE_NAME
        original_metadata = (
            metadata_path.read_bytes() if metadata_path.is_file() else None
        )
        content = original.decode("utf-8")
        engine_configuration = yaml.safe_load(original)
        if not isinstance(engine_configuration, dict):
            raise TypeError("The account configuration must contain a YAML mapping.")
        configuration = self.load_configuration(config_path)
        if (
            str(engine_configuration.get("username") or config_path.parent.name).strip()
            != account.username
        ):
            raise ValueError("The account identity has changed.")
        for candidate in self.identities.discover():
            if candidate.config_path.resolve() == config_path.resolve():
                continue
            if candidate.username.casefold() == username.casefold():
                raise ValueError("An account with this username already exists.")

        document = yaml.compose(content, Loader=yaml.SafeLoader)
        if not isinstance(document, MappingNode):
            raise TypeError("The account configuration must contain a YAML mapping.")
        settings = dict(settings or {})
        mute_after_follow = bool(settings.pop("igbot-follow-mute-after-follow", False))
        filter_settings = {
            key: settings.pop(key) for key in self.FILTER_SETTING_KEYS & settings.keys()
        }
        text_resources = {
            key: settings.pop(key) for key in self.TEXT_RESOURCE_NAMES & settings.keys()
        }
        allowed_settings = {
            "follow-percentage",
            "follow-limit",
            "total-follows-limit",
            "end-if-follows-limit-reached",
            "working-hours",
            "shuffle-jobs",
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
            "unfollow-from-file",
            "remove-followers-from-file",
            "likes-count",
            "likes-percentage",
            "total-likes-limit",
            "end-if-likes-limit-reached",
            "carousel-count",
            "carousel-percentage",
            "watch-photo-time",
            "watch-video-time",
            "posts-from-file",
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
            *self.AUDIENCE_SOURCE_KEYS,
        }
        if set(settings) - allowed_settings:
            raise ValueError("The account configuration contains unsupported settings.")
        effective_settings = dict(configuration)
        effective_settings.update(settings)
        module_enabled = {
            "follow": self._is_enabled_value(
                effective_settings.get("follow-percentage")
            ),
            "unfollow": any(
                self._is_enabled_value(effective_settings.get(key))
                for key in (
                    "unfollow",
                    "unfollow-non-followers",
                    "unfollow-any-non-followers",
                    "unfollow-any-followers",
                    "unfollow-any",
                    "unfollow-from-file",
                    "remove-followers-from-file",
                )
            ),
            "like": self._is_enabled_value(effective_settings.get("likes-percentage")),
            "story": self._is_enabled_value(effective_settings.get("stories-count")),
            "dm": self._is_enabled_value(effective_settings.get("pm-percentage")),
            "comment": self._is_enabled_value(
                effective_settings.get("comment-percentage")
            ),
        }
        setting_modules = {
            **{
                key: "follow"
                for key in (
                    "follow-percentage",
                    "follow-limit",
                    "total-follows-limit",
                    "end-if-follows-limit-reached",
                )
            },
            **{
                key: "unfollow"
                for key in (
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
                    "unfollow-from-file",
                    "remove-followers-from-file",
                )
            },
            **{
                key: "like"
                for key in (
                    "likes-count",
                    "likes-percentage",
                    "total-likes-limit",
                    "end-if-likes-limit-reached",
                    "carousel-count",
                    "carousel-percentage",
                    "watch-photo-time",
                    "watch-video-time",
                    "posts-from-file",
                    "delete-interacted-users",
                )
            },
            **{
                key: "story"
                for key in (
                    "stories-count",
                    "stories-percentage",
                    "total-watches-limit",
                    "end-if-watches-limit-reached",
                )
            },
            **{
                key: "dm"
                for key in (
                    "pm-percentage",
                    "total-pm-limit",
                    "end-if-pm-limit-reached",
                )
            },
            **{
                key: "comment"
                for key in (
                    "comment-percentage",
                    "total-comments-limit",
                    "max-comments-pro-user",
                    "end-if-comments-limit-reached",
                )
            },
        }
        for key, value in settings.items():
            if key in self.AUDIENCE_SOURCE_KEYS:
                if not any(module_enabled.values()):
                    continue
                if value is not None and (
                    not isinstance(value, list)
                    or any(
                        not isinstance(item, str) or not item.strip() for item in value
                    )
                ):
                    raise ValueError(f"{key} must be a list of audience targets.")
                continue
            module = setting_modules.get(key)
            if module is not None and not module_enabled[module]:
                continue
            if (
                key in {"follow-percentage", "follow-limit", "total-follows-limit"}
                and value is not None
                and not re.fullmatch(r"\d+(?:-\d+)?", str(value))
            ):
                raise ValueError(f"{key} must be a number or range.")
            if (
                key == "follow-percentage"
                and max(int(part) for part in str(value).split("-")) > 100
            ):
                raise ValueError("Follow percentage cannot exceed 100.")
            if key in {"follow-limit", "total-follows-limit"} and value is not None:
                parts = [int(part) for part in str(value).split("-")]
                if len(parts) == 2 and parts[0] > parts[1]:
                    raise ValueError(f"{key} minimum cannot exceed its maximum.")
            if key == "end-if-follows-limit-reached" and type(value) is not bool:
                raise ValueError(f"{key} must be a switch value.")
            if key == "working-hours" and (
                not isinstance(value, list)
                or any(
                    not isinstance(window, str)
                    or not re.fullmatch(
                        r"\d{1,2}(?:\.\d{1,2})?-\d{1,2}(?:\.\d{1,2})?",
                        window,
                    )
                    for window in value
                )
            ):
                raise ValueError("Working hours must be a list of schedule windows.")
            if key == "shuffle-jobs" and type(value) is not bool:
                raise ValueError("Shuffle jobs must be a switch value.")
            unfollow_ranges = {
                "unfollow",
                "unfollow-non-followers",
                "unfollow-any-non-followers",
                "unfollow-any-followers",
                "unfollow-any",
                "total-unfollows-limit",
            }
            if key in unfollow_ranges and not re.fullmatch(r"\d+(?:-\d+)?", str(value)):
                raise ValueError(f"{key} must be a number or range.")
            if key in unfollow_ranges and "-" in str(value):
                minimum, maximum = (int(part) for part in str(value).split("-", 1))
                if minimum > maximum:
                    raise ValueError(f"{key} minimum cannot exceed its maximum.")
            if key == "min-following" and (type(value) is not int or value < 0):
                raise ValueError("Minimum following must be a non-negative number.")
            if key == "unfollow-delay" and not re.fullmatch(r"\d+", str(value)):
                raise ValueError(
                    "Unfollow delay must be a non-negative number of days."
                )
            if (
                key
                in {
                    "sort-followers-newest-to-oldest",
                    "delete-removed-followers",
                }
                and type(value) is not bool
            ):
                raise ValueError(f"{key} must be a switch value.")
            if key in {"unfollow-from-file", "remove-followers-from-file"} and (
                not isinstance(value, list)
                or any(not isinstance(item, str) or not item.strip() for item in value)
            ):
                raise ValueError(f"{key} must be a list of file entries.")
            interaction_ranges = {
                "likes-count",
                "likes-percentage",
                "total-likes-limit",
                "carousel-count",
                "carousel-percentage",
                "watch-photo-time",
                "watch-video-time",
                "stories-count",
                "stories-percentage",
                "total-watches-limit",
                "pm-percentage",
                "total-pm-limit",
                "comment-percentage",
                "total-comments-limit",
                "max-comments-pro-user",
            }
            if key in interaction_ranges and not re.fullmatch(
                r"\d+(?:-\d+)?", str(value)
            ):
                raise ValueError(f"{key} must be a number or range.")
            if key in interaction_ranges and "-" in str(value):
                minimum, maximum = (int(part) for part in str(value).split("-", 1))
                if minimum > maximum:
                    raise ValueError(f"{key} minimum cannot exceed its maximum.")
            if (
                key
                in {
                    "likes-percentage",
                    "carousel-percentage",
                    "stories-percentage",
                    "pm-percentage",
                    "comment-percentage",
                }
                and max(int(part) for part in str(value).split("-")) > 100
            ):
                raise ValueError(f"{key} cannot exceed 100.")
            if (
                key
                in {
                    "end-if-likes-limit-reached",
                    "end-if-watches-limit-reached",
                    "end-if-pm-limit-reached",
                    "end-if-comments-limit-reached",
                    "delete-interacted-users",
                }
                and type(value) is not bool
            ):
                raise ValueError(f"{key} must be a switch value.")
            if key == "posts-from-file" and (
                not isinstance(value, list)
                or any(not isinstance(item, str) or not item.strip() for item in value)
            ):
                raise ValueError("posts-from-file must be a list of file entries.")
        filter_switches = set(self.FILTER_SETTING_KEYS) - {
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
        for key, value in filter_settings.items():
            if value is None:
                continue
            if key == "pm_to_private_or_empty":
                filters_enabled = module_enabled["dm"]
            elif key.startswith("comment_"):
                filters_enabled = module_enabled["comment"]
            else:
                filters_enabled = module_enabled["follow"] or module_enabled["like"]
            if not filters_enabled:
                continue
            if key in filter_switches and type(value) is not bool:
                raise ValueError(f"{key} must be a switch value.")
            if key in {
                "min_followers",
                "max_followers",
                "min_followings",
                "max_followings",
                "min_posts",
                "min_likers",
                "max_likers",
            } and (type(value) is not int or value < 0):
                raise ValueError(f"{key} must be a non-negative number.")
            if key == "mutual_friends" and (type(value) is not int or value < -1):
                raise ValueError("mutual_friends must be -1 or a non-negative number.")
            if key in {"min_potency_ratio", "max_potency_ratio"} and (
                type(value) not in {int, float} or value < 0
            ):
                raise ValueError(f"{key} must be a non-negative number.")
            if key in {
                "blacklist_words",
                "mandatory_words",
                "specific_alphabet",
                "biography_language",
            } and (
                not isinstance(value, list)
                or any(not isinstance(item, str) or not item.strip() for item in value)
            ):
                raise ValueError(f"{key} must be a list of non-empty values.")
        resource_modules = {
            "pm_list.txt": "dm",
            "comments_list.txt": "comment",
            "unfollow_users.txt": "unfollow",
            "remove_followers_users.txt": "unfollow",
        }
        if any(
            module_enabled[resource_modules[name]] and not isinstance(value, str)
            for name, value in text_resources.items()
        ):
            raise ValueError("Account text resources must contain text.")

        fields = {}
        obsolete_fields = []
        for key, value in document.value:
            if key.value == "password" or key.value.startswith(
                ("igbot-follow-", "igbot-timer-")
            ):
                obsolete_fields.append((key, value))
            if key.value in {"username", "app-id", "app_id"} | allowed_settings:
                if key.value in fields:
                    raise ValueError(
                        f"The account configuration contains duplicate {key.value} fields."
                    )
                fields[key.value] = value
        app_key = "app-id" if "app-id" in fields else "app_id"
        if "username" not in fields or app_key not in fields:
            raise ValueError("The account configuration is missing required fields.")

        replacements = []
        for key_node, value_node in obsolete_fields:
            line_start = content.rfind("\n", 0, key_node.start_mark.index) + 1
            line_end = content.find("\n", value_node.end_mark.index)
            line_end = len(content) if line_end == -1 else line_end + 1
            replacements.append((line_start, line_end, ""))
        for key, value in (
            ("username", username),
            (app_key, app_id),
        ):
            node = fields.get(key)
            if node is not None and str(engine_configuration.get(key, "")) != value:
                replacements.append(
                    (
                        node.start_mark.index,
                        node.end_mark.index,
                        json.dumps(value, ensure_ascii=False),
                    )
                )
        missing_settings = []
        for key, value in settings.items():
            node = fields.get(key)
            if value is None:
                if node is not None:
                    line_start = content.rfind("\n", 0, node.start_mark.index) + 1
                    line_end = content.find("\n", node.end_mark.index)
                    line_end = len(content) if line_end == -1 else line_end + 1
                    replacements.append((line_start, line_end, ""))
            elif node is None:
                missing_settings.append((key, value))
            elif configuration.get(key) != value:
                replacements.append(
                    (node.start_mark.index, node.end_mark.index, json.dumps(value))
                )
        if missing_settings:
            newline = "\r\n" if "\r\n" in content else "\n"
            prefix = "" if not content or content.endswith(("\n", "\r")) else newline
            block = prefix + "# IGBot Account Configuration" + newline
            block += "".join(
                f"{key}: {json.dumps(value)}{newline}"
                for key, value in missing_settings
            )
            replacements.append((len(content), len(content), block))
        updated = content
        for start, end, replacement in sorted(replacements, reverse=True):
            updated = updated[:start] + replacement + updated[end:]
        if config_path.read_bytes() != original:
            raise RuntimeError("The account configuration changed while editing.")

        self._write_configuration(config_path, updated)
        try:
            verified = config_path.read_bytes()
            parsed = yaml.safe_load(verified)
            if verified != updated.encode("utf-8") or not isinstance(parsed, dict):
                raise RuntimeError(
                    "The saved account configuration could not be verified."
                )
            if any(
                parsed.get(key) != value
                for key, value in (
                    ("username", username),
                    (app_key, app_id),
                )
            ):
                raise RuntimeError("The saved account values could not be verified.")
            if any(
                (key in parsed if value is None else parsed.get(key) != value)
                for key, value in settings.items()
            ):
                raise RuntimeError("The saved account settings could not be verified.")
        except (OSError, RuntimeError, yaml.YAMLError) as error:
            self._write_configuration(config_path, content)
            if config_path.read_bytes() != original:
                raise RuntimeError(
                    "The original account configuration could not be restored."
                ) from error
            raise RuntimeError(
                "Account configuration verification failed; the original was restored."
            ) from error
        filters_path = config_path.parent / "filters.yml"
        resource_paths = {
            name: config_path.parent / name for name in self.TEXT_RESOURCE_NAMES
        }
        original_resources = {
            filters_path: filters_path.read_bytes() if filters_path.is_file() else None,
            **{
                path: path.read_bytes() if path.is_file() else None
                for path in resource_paths.values()
            },
        }
        try:
            if filter_settings or filters_path.is_file():
                cleaned_filter_settings = {
                    key: None for key in self.OBSOLETE_FOLLOW_FILTER_KEYS
                }
                cleaned_filter_settings.update(filter_settings)
                self._update_yaml_fields(filters_path, cleaned_filter_settings)
            for name, resource_content in text_resources.items():
                resource_path = resource_paths[name]
                if resource_content:
                    self._write_configuration(resource_path, resource_content)
                    if resource_path.read_text(encoding="utf-8") != resource_content:
                        raise RuntimeError(
                            f"The {name} resource could not be verified."
                        )
                elif resource_path.exists():
                    resource_path.unlink()
        except (OSError, RuntimeError, TypeError, ValueError, yaml.YAMLError) as error:
            self._write_configuration(config_path, content)
            for path, original_resource in original_resources.items():
                self._restore_file(path, original_resource)
            raise RuntimeError(
                "Account resource update failed; the original files were restored."
            ) from error

        updated_account = self._load_account(config_path)
        if updated_account is None:
            raise RuntimeError("The saved account configuration could not be loaded.")
        old_directory = config_path.parent
        new_directory = root / username
        if (
            old_directory.resolve() != new_directory.resolve()
            and new_directory.exists()
        ):
            raise ValueError("An account directory with this username already exists.")
        renamed = False
        try:
            metadata = self.metadata.load(old_directory)
            runtime_extensions = metadata.get("runtime_extensions")
            if not isinstance(runtime_extensions, dict):
                runtime_extensions = {}
            runtime_extensions = dict(runtime_extensions)
            follow_extensions = runtime_extensions.get("follow")
            if not isinstance(follow_extensions, dict):
                follow_extensions = {}
            follow_extensions = dict(follow_extensions)
            follow_extensions["mute_after_follow"] = mute_after_follow
            runtime_extensions["follow"] = follow_extensions
            self.metadata.save(
                old_directory,
                username,
                password,
                account.device_id,
                tag=tag,
                runtime_extensions=runtime_extensions,
            )
            if old_directory.resolve() != new_directory.resolve():
                old_directory.rename(new_directory)
                renamed = True
            updated_account = self._load_account(new_directory / config_path.name)
            if updated_account is None:
                raise RuntimeError(
                    "The renamed account configuration could not be loaded."
                )
            return updated_account
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            if renamed:
                new_directory.rename(old_directory)
            self._write_configuration(config_path, content)
            self.metadata.restore(metadata_path, original_metadata)
            for path, original_resource in original_resources.items():
                self._restore_file(path, original_resource)
            raise RuntimeError(
                "Account metadata update failed; the original account was restored."
            ) from error

    @staticmethod
    def _is_enabled_value(value: object) -> bool:
        if value is None or value is False:
            return False
        if isinstance(value, str):
            return value.strip() not in {"", "0"}
        if isinstance(value, (int, float)):
            return value != 0
        return bool(value)

    @staticmethod
    def _write_configuration(path: Path, content: str) -> None:
        with atomic_write(path, overwrite=True, encoding="utf-8", newline="") as output:
            output.write(content)

    @classmethod
    def _update_yaml_fields(cls, path: Path, values: dict[str, object]) -> None:
        original = path.read_bytes() if path.is_file() else None
        content = original.decode("utf-8") if original is not None else ""
        parsed = yaml.safe_load(content) if content else {}
        if not isinstance(parsed, dict):
            raise TypeError(f"{path.name} must contain a YAML mapping.")
        document = yaml.compose(content, Loader=yaml.SafeLoader) if content else None
        fields = {}
        if isinstance(document, MappingNode):
            for key_node, value_node in document.value:
                if key_node.value in values:
                    if key_node.value in fields:
                        raise ValueError(
                            f"{path.name} contains duplicate {key_node.value} fields."
                        )
                    fields[key_node.value] = value_node

        replacements = []
        missing = []
        for key, value in values.items():
            node = fields.get(key)
            if value is None:
                if node is not None:
                    line_start = content.rfind("\n", 0, node.start_mark.index) + 1
                    line_end = content.find("\n", node.end_mark.index)
                    line_end = len(content) if line_end == -1 else line_end + 1
                    replacements.append((line_start, line_end, ""))
            elif node is None:
                missing.append((key, value))
            elif parsed.get(key) != value:
                replacements.append(
                    (node.start_mark.index, node.end_mark.index, json.dumps(value))
                )
        if missing:
            newline = "\r\n" if "\r\n" in content else "\n"
            prefix = "" if not content or content.endswith(("\n", "\r")) else newline
            replacements.append(
                (
                    len(content),
                    len(content),
                    prefix
                    + "".join(
                        f"{key}: {json.dumps(value)}{newline}" for key, value in missing
                    ),
                )
            )
        updated = content
        for start, end, replacement in sorted(replacements, reverse=True):
            updated = updated[:start] + replacement + updated[end:]
        cls._write_configuration(path, updated)
        verified = yaml.safe_load(path.read_bytes())
        if not isinstance(verified, dict) or any(
            (key in verified if value is None else verified.get(key) != value)
            for key, value in values.items()
        ):
            cls._restore_file(path, original)
            raise RuntimeError(f"The saved {path.name} values could not be verified.")

    @classmethod
    def _restore_file(cls, path: Path, original: bytes | None) -> None:
        if original is None:
            if path.exists():
                path.unlink()
            return
        with atomic_write(path, overwrite=True, mode="wb") as output:
            output.write(original)

    def create_account(
        self,
        username: str,
        password: str,
        device_id: str,
        templates_directory: Path,
    ) -> AssignedAccount:
        """Initialize an account using InstaAddict's existing local account templates."""
        username = username.strip()
        device_id = device_id.strip()
        account_directory = self._accounts_directory.resolve() / username
        logger.info("Add Account requested for username=%r", username)
        logger.info("Add Account directory: %s", account_directory)
        if not username:
            logger.info("Add Account failed: an Instagram username is required")
            raise ValueError("An Instagram username is required.")
        if not re.fullmatch(r"[A-Za-z0-9._]{1,30}", username):
            logger.info("Add Account failed: the Instagram username is invalid")
            raise ValueError("Enter a valid Instagram username.")
        if not password:
            logger.info("Add Account failed: an account password is required")
            raise ValueError("An account password is required.")
        if not device_id:
            logger.info("Add Account failed: a managed destination phone is required")
            raise ValueError("A managed destination phone is required.")

        accounts_root = self._accounts_directory.resolve()
        if account_directory.resolve().parent != accounts_root:
            logger.info(
                "Add Account failed: account directory is outside the managed root"
            )
            raise ValueError(
                "The account directory is outside the managed accounts root."
            )
        directory_kind = self.identities.classify(account_directory)
        classification = (
            "EMPTY"
            if directory_kind is AccountDirectoryKind.AVAILABLE
            else directory_kind.value
        )
        logger.info("Add Account catalog classification: %s", classification)
        existing = self.identities.discover()
        if any(
            account is not None and account.username.casefold() == username.casefold()
            for account in existing
        ):
            logger.info(
                "Add Account branch: canonical username duplicate; creation failed"
            )
            raise ValueError("An account with this username already exists.")
        if directory_kind is AccountDirectoryKind.ACCOUNT:
            logger.info("Add Account branch: ACCOUNT; creation failed")
            raise ValueError("An account directory with this username already exists.")
        if directory_kind is AccountDirectoryKind.OCCUPIED:
            logger.info(
                "Add Account branch: OCCUPIED; creation failed because the path "
                "cannot be recovered"
            )
            raise ValueError("The account path is occupied and cannot be recovered.")

        template_config = templates_directory / "config.yml"
        if not templates_directory.is_dir() or not template_config.is_file():
            logger.info(
                "Add Account failed: InstaAddict account configuration template "
                "is missing"
            )
            raise RuntimeError(
                "The InstaAddict account configuration template is missing."
            )

        account_created = False
        recovering_orphan = directory_kind is AccountDirectoryKind.ORPHAN
        original_files = (
            {
                path.relative_to(account_directory): path.read_bytes()
                for path in account_directory.rglob("*")
                if path.is_file()
            }
            if recovering_orphan
            else {}
        )
        try:
            accounts_root.mkdir(parents=True, exist_ok=True)
            if not recovering_orphan:
                logger.info(
                    "Add Account branch: EMPTY; creating a new account directory"
                )
                account_directory.mkdir()
                account_created = True
            else:
                logger.info(
                    "Add Account branch: ORPHAN; recovering existing account data"
                )
            for source in templates_directory.rglob("*"):
                destination = account_directory / source.relative_to(
                    templates_directory
                )
                if source.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                elif not destination.exists():
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
            config_path = self.identities.config_path(account_directory)
            content = config_path.read_text(encoding="utf-8")
            encoded_username = json.dumps(username, ensure_ascii=False)
            encoded_device = json.dumps(device_id, ensure_ascii=False)
            content, username_count = re.subn(
                r"(?m)^(username[ \t]*:[ \t]*)[^#\r\n]*([ \t]*#.*)?$",
                lambda match: (
                    f"{match.group(1)}{encoded_username}"
                    f"{' ' + match.group(2).lstrip() if match.group(2) else ''}"
                ),
                content,
                count=1,
            )
            content, device_count = re.subn(
                r"(?m)^#?[ \t]*device[ \t]*:[^\r\n]*$",
                f"device: {encoded_device}",
                content,
                count=1,
            )
            content, app_id_count = re.subn(
                r"(?m)^(app[-_]id[ \t]*:[ \t]*)[^#\r\n]*([ \t]*#.*)?$",
                lambda match: (
                    f'{match.group(1)}""'
                    f"{' ' + match.group(2).lstrip() if match.group(2) else ''}"
                ),
                content,
                count=1,
            )
            content = re.sub(
                r"(?m)^password[ \t]*:[^\r\n]*(?:\r?\n|$)",
                "",
                content,
            )
            if username_count != 1 or device_count != 1 or app_id_count != 1:
                raise RuntimeError(
                    "The account template is missing required configuration."
                )

            with atomic_write(config_path, overwrite=True, encoding="utf-8") as output:
                output.write(content)

            config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            if (
                not isinstance(config, dict)
                or config.get("username") != username
                or config.get("device") != device_id
            ):
                raise RuntimeError(
                    "The new account configuration could not be verified."
                )
            self.metadata.save(account_directory, username, password, device_id)

            account = self._load_account(config_path)
            if account is None:
                raise RuntimeError("The new account configuration could not be loaded.")
            logger.info(
                "Add Account succeeded for username=%r using the %s branch",
                username,
                "ORPHAN" if recovering_orphan else "EMPTY",
            )
            return account
        except (
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
            yaml.YAMLError,
        ) as error:
            logger.info(
                "Add Account failed for username=%r in the %s branch: %s",
                username,
                "ORPHAN" if recovering_orphan else "EMPTY",
                error,
            )
            if account_created and account_directory.is_dir():
                shutil.rmtree(account_directory)
            elif recovering_orphan:
                for path in sorted(account_directory.rglob("*"), reverse=True):
                    if (
                        path.is_file()
                        and path.relative_to(account_directory) not in original_files
                    ):
                        path.unlink()
                    elif path.is_dir() and not any(path.iterdir()):
                        path.rmdir()
                for relative_path, original in original_files.items():
                    path = account_directory / relative_path
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(original)
            raise

    def unassign_device(self, device_id: str) -> tuple[Path, ...]:
        """Remove a device assignment while preserving each account config."""
        assigned_accounts = self.load_by_device().get(device_id, ())
        updated_paths: list[Path] = []
        for account in assigned_accounts:
            config_path = account.config_path
            try:
                content = config_path.read_bytes().decode("utf-8")
                updated = re.sub(
                    r"(?m)^device\s*:[^\r\n]*(?:\r?\n|$)",
                    "",
                    content,
                )
                if updated == content:
                    continue
                with atomic_write(
                    config_path, overwrite=True, encoding="utf-8"
                ) as output:
                    output.write(updated)
            except OSError as error:
                raise RuntimeError(
                    f"Could not remove device assignment from {config_path}: {error}"
                ) from error
            updated_paths.append(config_path)

        if updated_paths:
            logger.info(
                "Removed device %s from %d account assignment(s)",
                device_id,
                len(updated_paths),
            )
        return tuple(updated_paths)

    def _load_account(self, config_path: Path) -> AssignedAccount | None:
        account = self.identities.load(config_path)
        if account is None:
            logger.warning(
                "Ignoring non-canonical account configuration %s", config_path
            )
        return account
