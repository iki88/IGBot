"""UIAutomator2 provider for Android's system-owned Recents cleanup."""

from __future__ import annotations

import re
import subprocess
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path

from IGBot.runtime.android import discover_adb
from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.recent_apps.models import CloseRecentAppsResult


class AndroidRecentAppsProvider:
    """Use the system Close-all action so Android preserves locked recent apps."""

    _BOUNDS = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")
    _TASK_ID = re.compile(r"Task\{[^\r\n]*?#(\d+)\b")
    _CLOSE_ALL_IDS = frozenset(
        {"btn_clear_all", "clear_all", "recent_apps_clear_all", "recents_clear_all"}
    )
    _CLOSE_ALL_LABELS = frozenset({"close all", "clear all"})

    def __init__(
        self,
        *,
        device_factory: Callable[[str], object] | None = None,
        command_runner: Callable[
            ..., subprocess.CompletedProcess[str]
        ] = subprocess.run,
        adb_executable: str | Path | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        timeout: float = 3.0,
        poll_interval: float = 0.25,
    ) -> None:
        self._device_factory = device_factory or self._connect
        self._command_runner = command_runner
        self._adb_executable = str(adb_executable or discover_adb())
        self._sleeper = sleeper
        self._clock = clock
        self._timeout = timeout
        self._poll_interval = poll_interval

    def close(self, context: RuntimeContext) -> CloseRecentAppsResult:
        """Open Recents and activate Android's lock-aware Close-all control once."""

        try:
            device = self._device_factory(context.session.phone_id)
            before = self._recent_task_ids(context.session.phone_id)
            device.press("recent")
            close_all = self._wait_for_close_all(device)
            if close_all is None:
                device.press("home")
                return CloseRecentAppsResult(True)

            device.click(*close_all)
            if not self._wait_until_closed(device):
                return CloseRecentAppsResult(
                    False, detail="Android Recents did not finish closing apps."
                )
            after = self._recent_task_ids(context.session.phone_id)
            removed = len(before - after)
            return CloseRecentAppsResult(True, max(1, removed))
        except Exception as error:  # noqa: BLE001 - Android provider boundary
            return CloseRecentAppsResult(
                False, detail=f"Closing recent apps failed: {error}"
            )

    def _wait_for_close_all(self, device: object) -> tuple[int, int] | None:
        deadline = self._clock() + self._timeout
        while True:
            target = self._close_all_center(device.dump_hierarchy(compressed=False))
            if target is not None:
                return target
            if self._clock() >= deadline:
                return None
            self._sleeper(self._poll_interval)

    def _wait_until_closed(self, device: object) -> bool:
        deadline = self._clock() + self._timeout
        while True:
            if self._close_all_center(device.dump_hierarchy(compressed=False)) is None:
                return True
            if self._clock() >= deadline:
                return False
            self._sleeper(self._poll_interval)

    @classmethod
    def _close_all_center(cls, hierarchy: str) -> tuple[int, int] | None:
        root = ET.fromstring(hierarchy)
        for node in root.iter("node"):
            resource_id = node.get("resource-id", "").rsplit("/", 1)[-1].casefold()
            label = (node.get("text") or node.get("content-desc") or "").strip()
            bounds = cls._BOUNDS.fullmatch(node.get("bounds", ""))
            if bounds is None:
                continue
            if (
                resource_id not in cls._CLOSE_ALL_IDS
                and label.casefold() not in cls._CLOSE_ALL_LABELS
            ):
                continue
            left, top, right, bottom = (int(value) for value in bounds.groups())
            return ((left + right) // 2, (top + bottom) // 2)
        return None

    def _recent_task_ids(self, serial: str) -> frozenset[str]:
        result = self._command_runner(
            [
                self._adb_executable,
                "-s",
                serial,
                "shell",
                "dumpsys",
                "activity",
                "recents",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if result.returncode != 0:
            return frozenset()
        return frozenset(self._TASK_ID.findall(result.stdout))

    @staticmethod
    def _connect(serial: str) -> object:
        import uiautomator2 as u2

        return u2.connect(serial)
