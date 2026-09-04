"""Shared interaction-module runtime contract."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.modules.state_machine import InteractionModule
from IGBot.runtime.state import ModuleState


class RuntimeModule(Protocol):
    """State surface exposed by every interaction module to scheduling."""

    @property
    def module(self) -> InteractionModule:
        """Return the stable interaction-module identity."""
        ...

    @property
    def context(self) -> RuntimeContext:
        """Return the session-scoped RuntimeContext."""
        ...

    @property
    def state(self) -> ModuleState:
        """Return the module's current lifecycle state."""
        ...

    @property
    def enabled(self) -> bool:
        """Return whether the operator enabled the module."""
        ...

    @property
    def backoff_until(self) -> datetime | None:
        """Return the current backoff boundary, when applicable."""
        ...

    def is_eligible(self) -> bool:
        """Return scheduler eligibility without exposing module internals."""
        ...
