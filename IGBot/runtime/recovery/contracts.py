"""Contracts for recovery selection and execution."""

from __future__ import annotations

from typing import Protocol

from IGBot.runtime.recovery.models import RecoveryDecision, RecoveryRequest


class RecoveryStrategy(Protocol):
    """Evaluate one class of runtime failure."""

    def evaluate(self, request: RecoveryRequest) -> RecoveryDecision:
        """Return the recovery decision for a failure."""
        ...


class CrashRecovery(RecoveryStrategy, Protocol):
    """Boundary for future Instagram crash recovery."""


class LoginRecovery(RecoveryStrategy, Protocol):
    """Boundary for future login and challenge recovery."""


class ActionBlockRecovery(RecoveryStrategy, Protocol):
    """Boundary for future action-block recovery."""


class RecoveryController(Protocol):
    """Route failures to the appropriate recovery strategy."""

    def recover(self, request: RecoveryRequest) -> RecoveryDecision:
        """Evaluate a failure through the configured strategy."""
        ...
