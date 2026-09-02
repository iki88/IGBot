"""ADB implementation of the runtime application-provider boundary."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from pathlib import Path

from IGBot.runtime.android import discover_adb
from IGBot.runtime.application.models import (
    ApplicationLaunchResult,
    ForegroundApplicationResult,
)
from IGBot.runtime.context import RuntimeContext


class AndroidApplicationProvider:
    """Launch and inspect Android packages with isolated ADB commands."""

    _FOREGROUND_PATTERN = re.compile(
        r"(?:mCurrentFocus|mFocusedApp|mResumedActivity|topResumedActivity|"
        r"ResumedActivity)\s*[:=].*?\b([A-Za-z][A-Za-z0-9._]*)/"
    )

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

    def launch(self, context: RuntimeContext, package: str) -> ApplicationLaunchResult:
        """Launch the package's exported MAIN/LAUNCHER activity."""
        command = self._adb_command(
            context,
            "shell",
            "am",
            "start",
            "-W",
            "-a",
            "android.intent.action.MAIN",
            "-c",
            "android.intent.category.LAUNCHER",
            "-p",
            package,
        )
        result, failure = self._execute(command, timeout=30)
        if failure is not None:
            return ApplicationLaunchResult(False, failure)
        if result is None or result.returncode != 0:
            return ApplicationLaunchResult(
                False,
                self._command_detail(result, "Instagram launch command failed."),
            )
        output = "\n".join((result.stdout or "", result.stderr or ""))
        if "error:" in output.lower() or "exception" in output.lower():
            return ApplicationLaunchResult(False, output.strip())
        return ApplicationLaunchResult(True)

    def foreground(self, context: RuntimeContext) -> ForegroundApplicationResult:
        """Inspect window state first, then activity state as a fallback."""
        failures: list[str] = []
        commands = (
            ("shell", "dumpsys", "window", "windows"),
            ("shell", "dumpsys", "activity", "activities"),
        )
        for shell_command in commands:
            result, failure = self._execute(
                self._adb_command(context, *shell_command), timeout=15
            )
            if failure is not None:
                failures.append(failure)
                continue
            if result is None or result.returncode != 0:
                failures.append(
                    self._command_detail(result, "Foreground application query failed.")
                )
                continue
            match = self._FOREGROUND_PATTERN.search(result.stdout or "")
            if match:
                return ForegroundApplicationResult(package=match.group(1))

        detail = next((failure for failure in failures if failure), None)
        return ForegroundApplicationResult(
            detail=detail or "No foreground Android application could be detected."
        )

    def _adb_command(self, context: RuntimeContext, *arguments: str) -> list[str]:
        return [
            self._adb_executable,
            "-s",
            context.session.phone_id,
            *arguments,
        ]

    def _execute(
        self, command: list[str], *, timeout: int
    ) -> tuple[subprocess.CompletedProcess[str] | None, str | None]:
        try:
            return (
                self._command_runner(
                    command,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=timeout,
                ),
                None,
            )
        except FileNotFoundError:
            return None, "ADB was not found."
        except subprocess.TimeoutExpired:
            return None, "The Android application command timed out."
        except OSError as error:
            return None, f"The Android application command failed: {error}"

    @staticmethod
    def _command_detail(
        result: subprocess.CompletedProcess[str] | None, fallback: str
    ) -> str:
        if result is None:
            return fallback
        return (result.stderr or result.stdout or fallback).strip()
