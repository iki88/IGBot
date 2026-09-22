"""Structured outcomes for Android recent-app cleanup."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CloseRecentAppsResult:
    """Report whether Android dismissed its removable recent tasks."""

    succeeded: bool
    closed_count: int = 0
    detail: str | None = None

    def __post_init__(self) -> None:
        if self.closed_count < 0:
            raise ValueError("Closed recent-app count cannot be negative")
