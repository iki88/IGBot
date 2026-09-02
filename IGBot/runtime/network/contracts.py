"""Platform-independent network-provider contract."""

from __future__ import annotations

from typing import Protocol

from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.network.models import NetworkCheckResult


class NetworkProvider(Protocol):
    """Observe Internet availability for the phone in a RuntimeContext."""

    def check(self, context: RuntimeContext) -> NetworkCheckResult:
        """Return the phone's current Internet connectivity observation."""
        ...
