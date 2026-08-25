import json
import logging
import re
import shutil
from pathlib import Path

import yaml
from atomicwrites import atomic_write
from yaml.nodes import MappingNode

from IGBot.core.device import AssignedAccount

logger = logging.getLogger(__name__)


class AccountAssignmentService:
    """Manages phone assignments in InstaAddict account configurations."""

    def __init__(self, accounts_directory: Path) -> None:
        self._accounts_directory = accounts_directory

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
        return configuration

    def update_configuration(
        self, account: AssignedAccount, username: str, password: str, app_id: str
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
        fields = {}
        for key, value in document.value:
            if key.value in {"username", "password", "app-id", "app_id"}:
                if key.value in fields:
                    raise ValueError(
                        f"The account configuration contains duplicate {key.value} fields."
                    )
                fields[key.value] = value
        app_key = "app-id" if "app-id" in fields else "app_id"
        if "username" not in fields or app_key not in fields:
            raise ValueError("The account configuration is missing required fields.")

        replacements = []
        for key, value in (
            ("username", username),
            ("password", password),
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
        if "password" not in fields:
            username_end = fields["username"].end_mark.index
            line_end = content.find("\n", username_end)
            newline = "\r\n" if "\r\n" in content else "\n"
            encoded = json.dumps(password, ensure_ascii=False)
            if line_end == -1:
                replacements.append(
                    (len(content), len(content), f"{newline}password: {encoded}")
                )
            else:
                replacements.append(
                    (line_end + 1, line_end + 1, f"password: {encoded}{newline}")
                )
        if not replacements:
            return account
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
                    ("password", password),
                    (app_key, app_id),
                )
            ):
                raise RuntimeError("The saved account values could not be verified.")
        except (OSError, RuntimeError, yaml.YAMLError) as error:
            self._write_configuration(config_path, content)
            if config_path.read_bytes() != original:
                raise RuntimeError(
                    "The original account configuration could not be restored."
                ) from error
            raise RuntimeError(
                "Account configuration verification failed; the original was restored."
            ) from error
        updated_account = self._load_account(config_path)
        if updated_account is None:
            raise RuntimeError("The saved account configuration could not be loaded.")
        return updated_account

    @staticmethod
    def _write_configuration(path: Path, content: str) -> None:
        with atomic_write(path, overwrite=True, encoding="utf-8", newline="") as output:
            output.write(content)

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
            encoded_password = json.dumps(password, ensure_ascii=False)
            encoded_device = json.dumps(device_id, ensure_ascii=False)
            content, username_count = re.subn(
                r"(?m)^(username[ \t]*:[ \t]*)[^#\r\n]*([ \t]*#.*)?$",
                lambda match: (
                    f"{match.group(1)}{encoded_username}"
                    f"{' ' + match.group(2).lstrip() if match.group(2) else ''}"
                    f"\npassword: {encoded_password}"
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
            if username_count != 1 or device_count != 1:
                raise RuntimeError(
                    "The account template is missing required configuration."
                )

            with atomic_write(config_path, overwrite=True, encoding="utf-8") as output:
                output.write(content)

            config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            if (
                not isinstance(config, dict)
                or config.get("username") != username
                or config.get("password") != password
                or config.get("device") != device_id
            ):
                raise RuntimeError(
                    "The new account configuration could not be verified."
                )

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
        app_id = str(
            config.get("app-id") or config.get("app_id") or "com.instagram.android"
        ).strip()
        return AssignedAccount(
            username=username,
            device_id=device_id,
            app_id=app_id,
            config_path=config_path,
        )
