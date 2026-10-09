"""Account-local, session-scoped Ignore List support."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class IgnoreService:
    """Immutable username lookup loaded once for one native runtime session."""

    usernames: frozenset[str] = frozenset()
    FILENAME = "ignore.txt"

    @classmethod
    def load(cls, account_directory: str | Path) -> "IgnoreService":
        path = Path(account_directory) / "Lists" / cls.FILENAME
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)
        return cls(
            frozenset(cls.normalize_many(path.read_text(encoding="utf-8").splitlines()))
        )

    @classmethod
    def save(
        cls, account_directory: str | Path, usernames: Iterable[str]
    ) -> tuple[str, ...]:
        directory = Path(account_directory) / "Lists"
        directory.mkdir(parents=True, exist_ok=True)
        normalized = cls.normalize_many(usernames)
        content = "".join(f"{username}\n" for username in normalized)
        (directory / cls.FILENAME).write_text(content, encoding="utf-8")
        return normalized

    @staticmethod
    def normalize(username: str) -> str:
        return str(username).strip().casefold()

    @classmethod
    def normalize_many(cls, usernames: Iterable[str]) -> tuple[str, ...]:
        result: list[str] = []
        seen: set[str] = set()
        for username in usernames:
            normalized = cls.normalize(username)
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
        return tuple(result)

    def is_ignored(self, username: str) -> bool:
        return self.normalize(username) in self.usernames


def log_ignored(context, username: str) -> None:
    """Emit the single operator-facing message for one skipped candidate."""

    context.logger.info(
        "[Ignore] Skipped (Ignore List)", username=IgnoreService.normalize(username)
    )
