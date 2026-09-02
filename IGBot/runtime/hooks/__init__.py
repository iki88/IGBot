"""Event-driven runtime-hook contracts."""

from IGBot.runtime.hooks.contracts import (
    ContactScrapingHook,
    HookManager,
    RuntimeHook,
    StatisticsHook,
)
from IGBot.runtime.hooks.models import HookEvent, HookEventType, HookResult

__all__ = [
    "ContactScrapingHook",
    "HookEvent",
    "HookEventType",
    "HookManager",
    "HookResult",
    "RuntimeHook",
    "StatisticsHook",
]
