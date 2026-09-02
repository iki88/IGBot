"""Events and results exchanged by inline runtime hooks."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from IGBot.runtime.context import RuntimeContext


class HookEventType(StrEnum):
    """Stable categories for events observed during module execution."""

    PROFILE_OPENED = "ProfileOpened"
    CONVERSATION_OPENED = "ConversationOpened"
    INTERACTION_COMPLETED = "InteractionCompleted"
    SESSION_STATISTICS_CHANGED = "SessionStatisticsChanged"


@dataclass(frozen=True, slots=True)
class HookEvent:
    """An immutable event emitted by a future interaction implementation."""

    event_type: HookEventType
    context: RuntimeContext
    payload: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class HookResult:
    """Outcome returned before control goes back to the scheduler."""

    handled: bool
    detail: str | None = None
