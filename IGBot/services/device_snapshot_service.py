"""Manual Android UI snapshots for operator and developer diagnostics."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class SnapshotCaptureError(RuntimeError):
    """Identify the exact snapshot stage that failed."""

    def __init__(self, stage: str, reason: object) -> None:
        super().__init__(f"{stage}: {reason}")


@dataclass(frozen=True, slots=True)
class DeviceSnapshot:
    """Paths and shared timestamp produced by one successful capture."""

    serial: str
    timestamp: str
    directory: Path
    hierarchy_path: Path
    screenshot_path: Path


class DeviceSnapshotService:
    """Capture and atomically publish one paired XML/PNG device snapshot."""

    TIMESTAMP_FORMAT = "%Y-%m-%d_%H-%M-%S"

    def __init__(
        self,
        workspace_root: Path,
        *,
        connector: Callable[[str], object] | None = None,
        clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._workspace_root = Path(workspace_root)
        self._connector = connector or self._connect
        self._clock = clock

    def capture(self, serial: str) -> DeviceSnapshot:
        """Capture the current hierarchy and screenshot with one unique stem."""
        serial = serial.strip()
        if not serial:
            raise ValueError("A device serial is required for a snapshot.")

        directory = (self._workspace_root / "snapshots" / serial).resolve()
        directory.mkdir(parents=True, exist_ok=True)
        timestamp, reservation = self._reserve_timestamp(directory, self._clock())
        hierarchy_path = directory / f"{timestamp}.xml"
        screenshot_path = directory / f"{timestamp}.png"
        token = uuid4().hex
        temporary_xml = directory / f".{timestamp}.{token}.tmp.xml"
        temporary_png = directory / f".{timestamp}.{token}.tmp.png"

        published: list[Path] = []
        try:
            try:
                device = self._connector(serial)
            except Exception as error:
                raise SnapshotCaptureError(
                    "Connecting to device failed", error
                ) from error

            logger.info("[Snapshot] Capturing UI hierarchy...")
            try:
                hierarchy = device.dump_hierarchy(compressed=False)
            except Exception as error:
                raise SnapshotCaptureError(
                    "Capturing UI hierarchy failed", error
                ) from error
            if not isinstance(hierarchy, str) or not hierarchy.strip():
                raise SnapshotCaptureError(
                    "Capturing UI hierarchy failed", "the hierarchy was empty"
                )
            try:
                temporary_xml.write_text(hierarchy, encoding="utf-8")
                os.replace(temporary_xml, hierarchy_path)
                published.append(hierarchy_path)
            except OSError as error:
                raise SnapshotCaptureError("Saving XML failed", error) from error
            if not hierarchy_path.is_file() or hierarchy_path.stat().st_size == 0:
                raise SnapshotCaptureError(
                    "Saving XML failed", "the published XML does not exist or is empty"
                )
            logger.info("[Snapshot] XML saved:\n%s", hierarchy_path)

            logger.info("[Snapshot] Capturing screenshot...")
            try:
                device.screenshot(str(temporary_png))
            except Exception as error:
                raise SnapshotCaptureError(
                    "Capturing screenshot failed", error
                ) from error
            if not temporary_png.is_file() or temporary_png.stat().st_size == 0:
                raise SnapshotCaptureError(
                    "Saving screenshot failed",
                    "the screenshot was not created or is empty",
                )
            try:
                os.replace(temporary_png, screenshot_path)
                published.append(screenshot_path)
            except OSError as error:
                raise SnapshotCaptureError("Saving screenshot failed", error) from error
            if not screenshot_path.is_file() or screenshot_path.stat().st_size == 0:
                raise SnapshotCaptureError(
                    "Saving screenshot failed",
                    "the published screenshot does not exist or is empty",
                )
            logger.info("[Snapshot] Screenshot saved:\n%s", screenshot_path)
        except Exception:
            for path in (temporary_xml, temporary_png, *published):
                path.unlink(missing_ok=True)
            raise
        finally:
            reservation.unlink(missing_ok=True)

        return DeviceSnapshot(
            serial,
            timestamp,
            directory,
            hierarchy_path,
            screenshot_path,
        )

    @classmethod
    def _reserve_timestamp(cls, directory: Path, current: datetime) -> tuple[str, Path]:
        """Exclusively reserve a free second so concurrent captures cannot overwrite."""
        candidate = current.replace(microsecond=0)
        while True:
            timestamp = candidate.strftime(cls.TIMESTAMP_FORMAT)
            reservation = directory / f".{timestamp}.snapshot.lock"
            if (directory / f"{timestamp}.xml").exists() or (
                directory / f"{timestamp}.png"
            ).exists():
                candidate += timedelta(seconds=1)
                continue
            try:
                reservation.touch(exist_ok=False)
            except FileExistsError:
                candidate += timedelta(seconds=1)
                continue
            return timestamp, reservation

    @staticmethod
    def _connect(serial: str) -> object:
        import uiautomator2 as u2

        return u2.connect(serial)
