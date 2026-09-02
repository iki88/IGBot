"""Android implementation of the runtime network-provider boundary."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

from IGBot.runtime.android import discover_adb
from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.network.models import NetworkCheckResult


class AndroidNetworkProvider:
    """Check Android Internet reachability through an isolated ADB probe."""

    def __init__(
        self,
        *,
        command_runner: Callable[
            ..., subprocess.CompletedProcess[str]
        ] = subprocess.run,
        adb_executable: str | Path | None = None,
        probe_host: str = "1.1.1.1",
    ) -> None:
        self._command_runner = command_runner
        self._adb_executable = str(adb_executable or discover_adb())
        self._probe_host = probe_host

    def check(self, context: RuntimeContext) -> NetworkCheckResult:
        """Probe an external address from the session's Android phone."""
        command = [
            self._adb_executable,
            "-s",
            context.session.phone_id,
            "shell",
            "ping",
            "-c",
            "1",
            "-W",
            "5",
            self._probe_host,
        ]
        try:
            result = self._command_runner(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
        except FileNotFoundError:
            return NetworkCheckResult(False, "ADB was not found.")
        except subprocess.TimeoutExpired:
            return NetworkCheckResult(False, "The Android network probe timed out.")
        except OSError as error:
            return NetworkCheckResult(
                False, f"The Android network probe failed: {error}"
            )

        if result.returncode == 0:
            return NetworkCheckResult(True)
        detail = (result.stderr or result.stdout or "Internet probe failed.").strip()
        return NetworkCheckResult(False, detail)
