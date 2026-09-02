"""Provider-neutral runtime notifications."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RuntimeNotificationLevel(StrEnum):
    """Severity communicated to a future notification destination."""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class RuntimeNotification:
    """One immutable operator notification emitted by the runtime."""

    title: str
    message: str
    level: RuntimeNotificationLevel = RuntimeNotificationLevel.WARNING
