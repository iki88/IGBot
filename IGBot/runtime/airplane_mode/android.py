"""ADB implementation of the Airplane Mode provider boundary."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

from IGBot.runtime.airplane_mode.models import AirplaneModeToggleResult
from IGBot.runtime.android import discover_adb
from IGBot.runtime.context import RuntimeContext


class AndroidAirplaneModeProvider:
    """Run and verify Android's connectivity-service Airplane Mode commands."""

    def __init__(
        self,
        *,
        command_runner: Callable[
            ..., subprocess.CompletedProcess[str]
        ] = subprocess.run,
        adb_executable: str | Path | None = None,
    ) -> None:
        self._command_runner = command_runner
        self._adb_executable = str(adb_executable or discover_adb())

    def toggle(self, context: RuntimeContext) -> AirplaneModeToggleResult:
        """Enable then disable Airplane Mode and verify both service states."""
        enabled = self._set_and_verify(context, "enable", "enabled")
        if enabled is not None:
            self._best_effort_disable(context)
            return AirplaneModeToggleResult(False, enabled)

        disabled = self._set_and_verify(context, "disable", "disabled")
        if disabled is not None:
            return AirplaneModeToggleResult(False, disabled)
        return AirplaneModeToggleResult(True)

    def _set_and_verify(
        self,
        context: RuntimeContext,
        action: str,
        expected_state: str,
    ) -> str | None:
        failure = self._run(context, action)
        if failure is not None:
            return failure
        query_failure, observed = self._query(context)
        if query_failure is not None:
            return query_failure
        if observed != expected_state:
            return (
                f"Airplane Mode {action} verification failed: expected "
                f"{expected_state}, observed {observed or 'no state'}."
            )
        return None

    def _run(self, context: RuntimeContext, action: str) -> str | None:
        result, failure = self._execute(context, action)
        if failure is not None:
            return failure
        if result is not None and result.returncode != 0:
            detail = (result.stderr or result.stdout or "command failed").strip()
            return f"Airplane Mode {action} failed: {detail}"
        return None

    def _query(self, context: RuntimeContext) -> tuple[str | None, str | None]:
        result, failure = self._execute(context)
        if failure is not None:
            return failure, None
        if result is None or result.returncode != 0:
            detail = (
                (result.stderr or result.stdout).strip()
                if result is not None
                else "command failed"
            )
            return f"Airplane Mode state query failed: {detail}", None
        return None, result.stdout.strip().lower()

    def _execute(
        self, context: RuntimeContext, action: str | None = None
    ) -> tuple[subprocess.CompletedProcess[str] | None, str | None]:
        command = [
            self._adb_executable,
            "-s",
            context.session.phone_id,
            "shell",
            "cmd",
            "connectivity",
            "airplane-mode",
        ]
        if action is not None:
            command.append(action)
        try:
            return (
                self._command_runner(
                    command,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=15,
                ),
                None,
            )
        except FileNotFoundError:
            return None, "ADB was not found."
        except subprocess.TimeoutExpired:
            return None, "The Airplane Mode command timed out."
        except OSError as error:
            return None, f"The Airplane Mode command failed: {error}"

    def _best_effort_disable(self, context: RuntimeContext) -> None:
        self._run(context, "disable")
