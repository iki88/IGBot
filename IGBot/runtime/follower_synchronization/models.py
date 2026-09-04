"""Structured observations and outcomes for Follower Synchronization."""

from __future__ import annotations

from dataclasses import dataclass

from IGBot.runtime.database import FollowRecord


@dataclass(frozen=True, slots=True)
class FollowerReadResult:
    """Bounded follower usernames returned by a platform reader."""

    completed: bool
    usernames: tuple[str, ...] = ()
    limit_reached: bool = False
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class FollowerComparison:
    """Repository-backed comparison without persistence side effects."""

    follow_back_updates: tuple[FollowRecord, ...] = ()
    organic_usernames: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FollowerSynchronizationResult:
    """Facts produced for the Startup Result and future scheduler handoff."""

    synchronization_completed: bool
    scanned_count: int
    follow_back_updates: int
    newly_discovered_organic_followers: tuple[str, ...]
    limit_reached: bool = False
