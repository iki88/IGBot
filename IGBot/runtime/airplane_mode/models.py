"""Provider-neutral Airplane Mode outcomes."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AirplaneModeToggleResult:
    """Result of one complete Airplane Mode on/off cycle."""

    succeeded: bool
    detail: str | None = None
