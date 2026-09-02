"""Provider-independent runtime notification contract."""

from __future__ import annotations

from typing import Protocol

from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.notifications.models import RuntimeNotification


class RuntimeNotifier(Protocol):
    """Deliver an operator-facing runtime notification."""

    def notify(
        self, context: RuntimeContext, notification: RuntimeNotification
    ) -> None:
        """Deliver a notification without owning its presentation."""
        ...
