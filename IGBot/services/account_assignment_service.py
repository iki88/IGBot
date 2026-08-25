import logging
import re
from pathlib import Path

import yaml
from atomicwrites import atomic_write

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
