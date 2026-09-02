"""Session lifecycle contract."""

from __future__ import annotations

from typing import Protocol

from IGBot.runtime.session.models import SessionContext, SessionStartResult


class SessionLifecycle(Protocol):
    """Public entry point implemented by the native SessionController."""

    def start(self, context: SessionContext) -> SessionStartResult:
        """Run startup and transfer successful control to the scheduler."""
        ...
