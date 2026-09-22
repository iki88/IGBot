"""Connection owner and composition root for a per-account Runtime Database."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import TracebackType
from typing import Self

from IGBot.runtime.database.migrations import migrate_runtime_schema
from IGBot.runtime.database.repositories import (
    CommentRepository,
    DMRepository,
    FollowRepository,
    LikeRepository,
    StoryRepository,
    UsersRepository,
)
from IGBot.runtime.database.specific_repositories import (
    SpecificProgressRepository,
    specific_repositories,
)


class RuntimeDatabase:
    """Own one ``runtime.db`` connection and its repository instances."""

    def __init__(self, account_directory: str | Path) -> None:
        self.path = Path(account_directory) / "runtime.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path)
        self._connection.row_factory = sqlite3.Row
        self._closed = False

        self.users = UsersRepository(self._connection)
        self.follow = FollowRepository(self._connection)
        self.like = LikeRepository(self._connection)
        self.comment = CommentRepository(self._connection)
        self.story = StoryRepository(self._connection)
        self.dm = DMRepository(self._connection)
        self.specific = specific_repositories(self._connection)
        self.specific_follow = self.specific["specific_follow"]
        self.specific_unfollow = self.specific["specific_unfollow"]
        self.specific_like = self.specific["specific_like"]
        self.specific_dm = self.specific["specific_dm"]
        self.specific_comment = self.specific["specific_comment"]
        self.specific_progress = SpecificProgressRepository(self._connection)

        try:
            self._initialize_schema()
        except Exception:
            self._connection.close()
            self._closed = True
            raise

    def _initialize_schema(self) -> None:
        repositories = (
            self.users,
            self.follow,
            self.like,
            self.comment,
            self.story,
            self.dm,
            *self.specific.values(),
            self.specific_progress,
        )
        migrate_runtime_schema(self._connection, repositories)
        with self._connection:
            for repository in repositories:
                repository.initialize_schema()

    def commit(self) -> None:
        """Commit repository writes as one caller-owned unit of work."""

        self._connection.commit()

    def rollback(self) -> None:
        """Roll back repository writes in the current unit of work."""

        self._connection.rollback()

    def close(self) -> None:
        """Close the owned SQLite connection; repeated calls are harmless."""

        if not self._closed:
            self._connection.close()
            self._closed = True

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exception_type is None:
            self.commit()
        else:
            self.rollback()
        self.close()
