"""Contracts for translating native runtime requests to execution providers."""

from __future__ import annotations

from typing import Protocol

from IGBot.runtime.compatibility.models import ExecutionRequest, ExecutionResult


class ModuleAdapter(Protocol):
    """Translate one module request without exposing provider details."""

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute a scheduler-approved module request."""
        ...

    def request_stop(self) -> None:
        """Request an orderly stop from the execution provider."""
        ...


class FollowAdapter(ModuleAdapter, Protocol):
    """Compatibility boundary for Follow execution."""


class UnfollowAdapter(ModuleAdapter, Protocol):
    """Compatibility boundary for Unfollow execution."""


class LikeAdapter(ModuleAdapter, Protocol):
    """Compatibility boundary for Like execution."""


class DMAdapter(ModuleAdapter, Protocol):
    """Compatibility boundary for Direct Message execution."""


class InstaAddictAdapter(ModuleAdapter, Protocol):
    """Exclusive contract for the current InstaAddict execution provider."""
