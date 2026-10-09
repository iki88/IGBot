"""Stable notification domain models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class NotificationSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class NotificationType(StrEnum):
    ZERO_INTERACTIONS = "ZERO_INTERACTIONS"


@dataclass(frozen=True, slots=True)
class Notification:
    id: int
    username: str
    device: str
    tag: str
    severity: NotificationSeverity
    type: NotificationType
    active: bool
    occurrences: int
    detected_at: str
    last_detected_at: str
    resolved_at: str | None
    details: str
