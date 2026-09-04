"""Persistence records owned by an account's Runtime Database."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UserRecord:
    """Shared target identity and its first discovery provenance."""

    id: int
    username: str
    first_seen: str
    first_discovered_by: str | None = None


@dataclass(frozen=True, slots=True)
class FollowRecord:
    """Follow-family state for one target user."""

    user_id: int
    source: str | None = None
    follow_date: str | None = None
    follow_back: bool = False
    follow_back_date: str | None = None
    unfollowed: bool = False
    unfollow_date: str | None = None
    last_session_id: str | None = None


@dataclass(frozen=True, slots=True)
class LikeRecord:
    """Like state for one target user."""

    user_id: int
    source: str | None = None
    likes_count: int = 0
    last_like_date: str | None = None
    follow_back: bool = False
    follow_back_date: str | None = None


@dataclass(frozen=True, slots=True)
class CommentRecord:
    """Comment state for one target user."""

    user_id: int
    source: str | None = None
    comments_count: int = 0
    last_comment_date: str | None = None
    follow_back: bool = False
    follow_back_date: str | None = None


@dataclass(frozen=True, slots=True)
class StoryRecord:
    """Story-view state for one target user."""

    user_id: int
    source: str | None = None
    story_views_count: int = 0
    last_story_date: str | None = None
    follow_back: bool = False
    follow_back_date: str | None = None


@dataclass(frozen=True, slots=True)
class DMRecord:
    """Direct-message state for one target user."""

    user_id: int
    source: str | None = None
    dm_count: int = 0
    last_dm_date: str | None = None
    last_message: str | None = None
    last_reply: str | None = None
