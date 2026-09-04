"""Provider and service contracts for Follower Synchronization."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.database import FollowRepository, UsersRepository
from IGBot.runtime.follower_synchronization.models import (
    FollowerComparison,
    FollowerReadResult,
)


class FollowerReader(Protocol):
    """Read a bounded set of complete usernames from Instagram."""

    def read(self, context: RuntimeContext, limit: int) -> FollowerReadResult:
        """Open Followers and return no more than ``limit`` usernames."""
        ...


class FollowerComparer(Protocol):
    """Compare observed followers with repository state."""

    def compare(
        self,
        usernames: tuple[str, ...],
        users: UsersRepository,
        follow: FollowRepository,
        observed_at: datetime,
    ) -> FollowerComparison:
        """Return required writes without changing repository state."""
        ...


class FollowerWriter(Protocol):
    """Persist a comparison through Runtime Database repositories."""

    def write(
        self,
        comparison: FollowerComparison,
        users: UsersRepository,
        follow: FollowRepository,
        observed_at: datetime,
    ) -> None:
        """Apply only Users and Follow changes."""
        ...
