"""Contracts for inline, event-driven runtime hooks."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from IGBot.runtime.hooks.models import HookEvent, HookEventType, HookResult


class RuntimeHook(Protocol):
    """React inline to events and return control to the scheduler."""

    @property
    def event_types(self) -> Sequence[HookEventType]:
        """Return the event categories handled by this hook."""
        ...

    def handle(self, event: HookEvent) -> HookResult:
        """Handle one event synchronously."""
        ...


class ContactScrapingHook(RuntimeHook, Protocol):
    """Boundary for future profile contact-detail collection."""


class StatisticsHook(RuntimeHook, Protocol):
    """Boundary for future inline statistics updates."""


class HookManager(Protocol):
    """Dispatch runtime events to registered hooks."""

    def dispatch(self, event: HookEvent) -> Sequence[HookResult]:
        """Run matching hooks and return their outcomes."""
        ...
