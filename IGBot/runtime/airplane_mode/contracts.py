"""Platform-independent Airplane Mode provider contract."""

from __future__ import annotations

from typing import Protocol

from IGBot.runtime.airplane_mode.models import AirplaneModeToggleResult
from IGBot.runtime.context import RuntimeContext


class AirplaneModeProvider(Protocol):
    """Perform one platform-specific Airplane Mode cycle."""

    def toggle(self, context: RuntimeContext) -> AirplaneModeToggleResult:
        """Enable and disable Airplane Mode, returning a verified outcome."""
        ...
