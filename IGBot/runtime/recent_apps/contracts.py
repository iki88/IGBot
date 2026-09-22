"""Platform boundary for closing removable Android recent apps."""

from __future__ import annotations

from typing import Protocol

from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.recent_apps.models import CloseRecentAppsResult


class RecentAppsProvider(Protocol):
    """Close removable recent apps while preserving Android-locked tasks."""

    def close(self, context: RuntimeContext) -> CloseRecentAppsResult:
        """Return the system Recents cleanup outcome."""
        ...
