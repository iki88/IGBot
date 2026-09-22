"""Android recent-app cleanup provider boundary."""

from IGBot.runtime.recent_apps.android import AndroidRecentAppsProvider
from IGBot.runtime.recent_apps.contracts import RecentAppsProvider
from IGBot.runtime.recent_apps.models import CloseRecentAppsResult

__all__ = [
    "AndroidRecentAppsProvider",
    "CloseRecentAppsResult",
    "RecentAppsProvider",
]
