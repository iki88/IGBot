"""Repository-backed follower comparison."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from IGBot.runtime.database import FollowRepository, UsersRepository
from IGBot.runtime.follower_synchronization.models import FollowerComparison


def utc_text(value: datetime) -> str:
    """Serialize an aware timestamp in the Runtime Database UTC format."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Follower Synchronization timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat()


class RuntimeFollowerComparer:
    """Classify followers as follow-backs or newly observed organic users."""

    def compare(
        self,
        usernames: tuple[str, ...],
        users: UsersRepository,
        follow: FollowRepository,
        observed_at: datetime,
    ) -> FollowerComparison:
        observed_text = utc_text(observed_at)
        updates = []
        organic = []
        for username in usernames:
            user = users.get_by_username(username)
            if user is None:
                organic.append(username)
                continue
            follow_record = follow.get(user.id)
            if follow_record is not None:
                updates.append(
                    replace(
                        follow_record,
                        follow_back=True,
                        follow_back_date=observed_text,
                    )
                )
        return FollowerComparison(tuple(updates), tuple(organic))
