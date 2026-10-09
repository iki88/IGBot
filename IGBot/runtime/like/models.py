"""Structured results and settings for the native Like provider."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from IGBot.runtime.navigation import NavigationResult


class AndroidLikeStatus(StrEnum):
    SUCCESS = "SUCCESS"
    ALREADY_LIKED = "ALREADY_LIKED"
    NO_POSTS = "NO_POSTS"
    NO_SUPPORTED_POST = "NO_SUPPORTED_POST"
    PRIVATE_SKIPPED = "PRIVATE_SKIPPED"
    PROFILE_UNAVAILABLE = "PROFILE_UNAVAILABLE"
    PROFILE_NOT_FOUND = "PROFILE_NOT_FOUND"
    LIKE_FAILED = "LIKE_FAILED"
    GHOST_BLOCK_DETECTED = "GHOST_BLOCK_DETECTED"
    NAVIGATION_FAILED = "NAVIGATION_FAILED"
    FILTER_REJECTED = "FILTER_REJECTED"
    IGNORED = "IGNORED"


class LikeMediaType(StrEnum):
    PHOTO = "Photo"
    CAROUSEL = "Carousel"
    REEL = "Reel"


@dataclass(frozen=True, slots=True)
class LikePostFilterSettings:
    """Optional visible Like-count bounds for an opened media item."""

    minimum_likes: int | None = None
    maximum_likes: int | None = None

    @property
    def enabled(self) -> bool:
        return self.minimum_likes is not None or self.maximum_likes is not None


@dataclass(frozen=True, slots=True)
class AndroidLikeResult:
    status: AndroidLikeStatus
    detail: str | None = None
    likes_completed: int = 0
    navigation: NavigationResult = field(default_factory=NavigationResult)

    def __post_init__(self) -> None:
        if self.likes_completed < 0:
            raise ValueError("Verified Like count cannot be negative")
        if self.likes_completed and self.status is not AndroidLikeStatus.SUCCESS:
            raise ValueError(
                "Verified Likes require a SUCCESS interaction status; "
                "post-interaction navigation belongs in navigation"
            )

    @property
    def succeeded(self) -> bool:
        return self.status is AndroidLikeStatus.SUCCESS


@dataclass(frozen=True, slots=True)
class LikeModuleSettings:
    enabled: bool
    configured: bool
    budget: int | str
    daily_remaining: int
    hourly_remaining: int
