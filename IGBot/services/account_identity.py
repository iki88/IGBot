"""Canonical filesystem identity and discovery for IGBot accounts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import yaml

from IGBot.core.device import AssignedAccount


class AccountDirectoryKind(StrEnum):
    """Classification of one direct child of the accounts directory."""

    ACCOUNT = "ACCOUNT"
    ORPHAN = "ORPHAN"
    OCCUPIED = "OCCUPIED"
    AVAILABLE = "AVAILABLE"


@dataclass(frozen=True, slots=True)
class OrphanedAccount:
    """A recoverable account directory containing data but no configuration."""

    directory: Path

    @property
    def username(self) -> str:
        return self.directory.name


class AccountIdentityCatalog:
    """Apply the single ``config.yml`` account definition everywhere."""

    CONFIG_NAME = "config.yml"

    def __init__(self, accounts_directory: Path) -> None:
        self.accounts_directory = accounts_directory

    def config_path(self, directory: Path) -> Path:
        return directory / self.CONFIG_NAME

    def classify(self, directory: Path) -> AccountDirectoryKind:
        if not directory.exists():
            return AccountDirectoryKind.AVAILABLE
        if not directory.is_dir():
            return AccountDirectoryKind.OCCUPIED
        if self.config_path(directory).is_file():
            return AccountDirectoryKind.ACCOUNT
        if any(directory.iterdir()):
            return AccountDirectoryKind.ORPHAN
        return AccountDirectoryKind.OCCUPIED

    def discover(self) -> tuple[AssignedAccount, ...]:
        if not self.accounts_directory.is_dir():
            return ()
        accounts = []
        for directory in sorted(self.accounts_directory.iterdir()):
            if self.classify(directory) is not AccountDirectoryKind.ACCOUNT:
                continue
            account = self.load(self.config_path(directory))
            if account is not None:
                accounts.append(account)
        return tuple(accounts)

    def orphans(self) -> tuple[OrphanedAccount, ...]:
        if not self.accounts_directory.is_dir():
            return ()
        return tuple(
            OrphanedAccount(directory)
            for directory in sorted(self.accounts_directory.iterdir())
            if self.classify(directory) is AccountDirectoryKind.ORPHAN
        )

    def load(self, config_path: Path) -> AssignedAccount | None:
        if config_path.name != self.CONFIG_NAME or not config_path.is_file():
            return None
        try:
            config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            return None
        if not isinstance(config, dict):
            return None
        return AssignedAccount(
            username=str(config.get("username") or config_path.parent.name).strip(),
            device_id=str(config.get("device") or "").strip(),
            app_id=str(config.get("app-id") or config.get("app_id") or "").strip(),
            config_path=config_path,
        )
