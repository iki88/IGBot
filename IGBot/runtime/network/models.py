"""Provider-neutral network observations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NetworkCheckResult:
    """One Internet availability observation from a platform provider."""

    available: bool
    detail: str | None = None
