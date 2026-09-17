"""Immutable shared Instagram profile observations."""

from __future__ import annotations

from dataclasses import dataclass

from IGBot.runtime.database.timestamps import utc_timestamp


@dataclass(frozen=True, slots=True)
class ProfileUpdate:
    username: str
    discovered_at: str
    full_name: str = ""
    biography: str = ""
    category: str = ""
    website: str = ""
    phone: str = ""
    email: str = ""
    address: str = ""
    followers: int | None = None
    following: int | None = None
    posts: int | None = None
    is_private: bool = False
    is_business: bool = False
    is_verified: bool = False
    follow_status: str = ""
    source_account: str = ""

    def __post_init__(self) -> None:
        if not self.username.strip():
            raise ValueError("Profile username cannot be empty")
        utc_timestamp(self.discovered_at)
