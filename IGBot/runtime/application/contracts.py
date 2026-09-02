"""Platform-independent application-provider contract."""

from __future__ import annotations

from typing import Protocol

from IGBot.runtime.application.models import (
    ApplicationLaunchResult,
    ForegroundApplicationResult,
)
from IGBot.runtime.context import RuntimeContext


class ApplicationProvider(Protocol):
    """Launch and inspect applications for one runtime session."""

    def launch(self, context: RuntimeContext, package: str) -> ApplicationLaunchResult:
        """Request launch of the configured package."""
        ...

    def foreground(self, context: RuntimeContext) -> ForegroundApplicationResult:
        """Return the package currently in the foreground."""
        ...
