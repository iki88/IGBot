import logging
from pathlib import Path

import yaml

from IGBot.core.device import AssignedAccount

logger = logging.getLogger(__name__)


class AccountAssignmentService:
    """Reads real phone assignments from InstaAddict account configurations."""

    def __init__(self, accounts_directory: Path) -> None:
        self._accounts_directory = accounts_directory

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
