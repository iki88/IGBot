"""Repository-only persistence for Follower Synchronization."""

from __future__ import annotations

from datetime import datetime

from IGBot.runtime.database import FollowRepository, UsersRepository
from IGBot.runtime.follower_synchronization.comparer import utc_text
from IGBot.runtime.follower_synchronization.models import FollowerComparison


class RuntimeFollowerWriter:
    """Write only Users discoveries and Follow follow-back updates."""

    def write(
        self,
        comparison: FollowerComparison,
        users: UsersRepository,
        follow: FollowRepository,
        observed_at: datetime,
    ) -> None:
        observed_text = utc_text(observed_at)
        for username in comparison.organic_usernames:
            users.create(
                username=username,
                first_seen=observed_text,
                first_discovered_by="ORGANIC",
            )
        for record in comparison.follow_back_updates:
            follow.save(record)
