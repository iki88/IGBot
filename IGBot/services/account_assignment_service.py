import json
import logging
import re
import shutil
from pathlib import Path

import yaml
from atomicwrites import atomic_write
from yaml.nodes import MappingNode

from IGBot.core.device import AssignedAccount
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
        }
    )
    TEXT_RESOURCE_NAMES = frozenset({"pm_list.txt", "comments_list.txt"})
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

    @property
    def accounts_directory(self) -> Path:
        """Return the centralized root used to locate account configurations."""
        return self._accounts_directory

    def load_by_device(self) -> dict[str, tuple[AssignedAccount, ...]]:
        assignments: dict[str, list[AssignedAccount]] = {}
        if not self._accounts_directory.is_dir():
            return {}

        for config_path in sorted(self._accounts_directory.glob("*/config.y*ml")):
            account = self._load_account(config_path)
            if account is None or not account.device_id:
                continue
            assignments.setdefault(account.device_id, []).append(account)

        return {
            device_id: tuple(accounts) for device_id, accounts in assignments.items()
        }

    def load_configuration(self, config_path: Path) -> dict:
        """Read an existing account configuration without changing its representation."""
        configuration = yaml.safe_load(config_path.read_bytes())
        if not isinstance(configuration, dict):
            raise TypeError("The account configuration must contain a YAML mapping.")
        metadata = self.metadata.load(config_path.parent)
        if metadata:
            configuration = dict(configuration)
            configuration["username"] = str(
                metadata.get("username") or configuration.get("username") or ""
            )
            configuration["password"] = str(metadata.get("password") or "")
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
    ) -> AssignedAccount:
        """Atomically update account fields while preserving YAML layout and comments."""
        username = username.strip()
        app_id = app_id.strip()
        if not re.fullmatch(r"[A-Za-z0-9._]{1,30}", username):
            raise ValueError("Enter a valid Instagram username.")
        if not password:
            raise ValueError("An account password is required.")
        if not re.fullmatch(
            r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+", app_id
        ):
            raise ValueError("Enter a valid Android application ID.")

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
        configuration = self.load_configuration(config_path)
        if (
            str(configuration.get("username") or config_path.parent.name).strip()
            != account.username
        ):
            raise ValueError("The account identity has changed.")
        for candidate_path in self._accounts_directory.glob("*/config.y*ml"):
            if candidate_path.resolve() == config_path.resolve():
                continue
            candidate = self._load_account(candidate_path)
            if candidate and candidate.username.casefold() == username.casefold():
                raise ValueError("An account with this username already exists.")

        document = yaml.compose(content, Loader=yaml.SafeLoader)
        if not isinstance(document, MappingNode):
            raise TypeError("The account configuration must contain a YAML mapping.")
        settings = dict(settings or {})
        filter_settings = {
            key: settings.pop(key) for key in self.FILTER_SETTING_KEYS & settings.keys()
        }
        text_resources = {
            key: settings.pop(key) for key in self.TEXT_RESOURCE_NAMES & settings.keys()
        }
        allowed_settings = {
            "follow-percentage",
            "total-follows-limit",
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
        for key, value in settings.items():
            if key in self.AUDIENCE_SOURCE_KEYS:
                if value is not None and (
                    not isinstance(value, list)
                    or any(
                        not isinstance(item, str) or not item.strip() for item in value
                    )
                ):
                    raise ValueError(f"{key} must be a list of audience targets.")
                continue
            if key in {"follow-percentage", "total-follows-limit"} and not re.fullmatch(
                r"\d+(?:-\d+)?", str(value)
            ):
                raise ValueError(f"{key} must be a number or range.")
            if (
                key == "follow-percentage"
                and max(int(part) for part in str(value).split("-")) > 100
            ):
                raise ValueError("Follow percentage cannot exceed 100.")
            if key == "total-follows-limit":
                parts = [int(part) for part in str(value).split("-")]
                if len(parts) == 2 and parts[0] > parts[1]:
                    raise ValueError(
                        "Total follows limit minimum cannot exceed its maximum."
                    )
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
                }
                and type(value) is not bool
            ):
                raise ValueError(f"{key} must be a switch value.")
            if key == "posts-from-file" and (
                not isinstance(value, list)
                or any(not isinstance(item, str) or not item.strip() for item in value)
            ):
                raise ValueError("posts-from-file must be a list of file entries.")
        if any(type(value) is not bool for value in filter_settings.values()):
            raise ValueError("Account filter settings must be switch values.")
        if any(not isinstance(value, str) for value in text_resources.values()):
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
            if node is not None and str(configuration.get(key, "")) != value:
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
            if filter_settings:
                self._update_yaml_fields(filters_path, filter_settings)
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
            self.metadata.save(old_directory, username, password, account.device_id)
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
            if node is None:
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
            verified.get(key) != value for key, value in values.items()
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
        if not username:
            raise ValueError("An Instagram username is required.")
        if not re.fullmatch(r"[A-Za-z0-9._]{1,30}", username):
            raise ValueError("Enter a valid Instagram username.")
        if not password:
            raise ValueError("An account password is required.")
        if not device_id:
            raise ValueError("A managed destination phone is required.")

        accounts_root = self._accounts_directory.resolve()
        account_directory = accounts_root / username
        if account_directory.resolve().parent != accounts_root:
            raise ValueError(
                "The account directory is outside the managed accounts root."
            )
        existing = (
            self._load_account(config_path)
            for config_path in self._accounts_directory.glob("*/config.y*ml")
        )
        if any(
            account is not None and account.username.casefold() == username.casefold()
            for account in existing
        ):
            raise ValueError("An account with this username already exists.")
        if account_directory.exists():
            raise ValueError("An account directory with this username already exists.")

        template_config = templates_directory / "config.yml"
        if not templates_directory.is_dir() or not template_config.is_file():
            raise RuntimeError(
                "The InstaAddict account configuration template is missing."
            )

        account_created = False
        try:
            accounts_root.mkdir(parents=True, exist_ok=True)
            account_directory.mkdir()
            account_created = True
            shutil.copytree(templates_directory, account_directory, dirs_exist_ok=True)
            config_path = account_directory / "config.yml"
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
            return account
        except (OSError, RuntimeError, TypeError, ValueError, yaml.YAMLError):
            if account_created and account_directory.is_dir():
                shutil.rmtree(account_directory)
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
        try:
            config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as error:
            logger.warning("Could not read account config %s: %s", config_path, error)
            return None

        if not isinstance(config, dict):
            logger.warning("Account config %s does not contain a mapping", config_path)
            return None

        device_id = str(config.get("device") or "").strip()
        username = str(config.get("username") or config_path.parent.name).strip()
        app_id = str(config.get("app-id") or config.get("app_id") or "").strip()
        return AssignedAccount(
            username=username,
            device_id=device_id,
            app_id=app_id,
            config_path=config_path,
        )
