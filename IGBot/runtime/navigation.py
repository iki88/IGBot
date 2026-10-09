"""Shared post-interaction navigation outcome contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class NavigationStatus(StrEnum):
    """State of navigation performed after an interaction outcome is final."""

    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class NavigationResult:
    status: NavigationStatus = NavigationStatus.NOT_ATTEMPTED
    detail: str | None = None
    expected: str | None = None
    actual: str | None = None
