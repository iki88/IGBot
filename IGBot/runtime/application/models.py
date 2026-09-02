"""Provider-neutral Android application outcomes."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ApplicationLaunchResult:
    """Result of requesting that one application be launched."""

    succeeded: bool
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class ForegroundApplicationResult:
    """Observed foreground package or a provider failure."""

    package: str | None = None
    detail: str | None = None
