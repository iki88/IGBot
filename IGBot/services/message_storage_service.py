"""Account-local storage for native interaction message templates."""

from __future__ import annotations

from pathlib import Path


class MessageStorageService:
    """Read and write extensible UTF-8 message resources for one account."""

    DIRECTORY = "Messages"
    WELCOME_DM = "welcome_dm.txt"

    def __init__(self, account_directory: str | Path) -> None:
        self.account_directory = Path(account_directory)
        self.directory = self.account_directory / self.DIRECTORY

    def path(self, filename: str) -> Path:
        return self.directory / filename

    def load(self, filename: str) -> str:
        path = self.path(filename)
        if path.is_file():
            return path.read_text(encoding="utf-8")
        return ""

    def save(self, filename: str, message: str) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.path(filename)
        path.write_text(message, encoding="utf-8")
        return path
