"""Platform-independent Instagram profile-provider contract."""

from __future__ import annotations

from typing import Protocol

from IGBot.runtime.account_verification.models import (
    ProfileObservation,
    UsernameDetectionResult,
)
from IGBot.runtime.context import RuntimeContext


class InstagramProfileProvider(Protocol):
    """Navigate to Profile and read Instagram account identity."""

    def open_profile(self, context: RuntimeContext) -> ProfileObservation:
        """Open Profile and observe its visible username state."""
        ...

    def complete_username_from_switcher(
        self, context: RuntimeContext
    ) -> UsernameDetectionResult:
        """Read the selected complete username and close Account Switcher."""
        ...
