import subprocess
from datetime import datetime, timezone

import pytest

from IGBot.services.device_snapshot_service import DeviceSnapshotService
from IGBot.services.snapshot_folder_opener import SnapshotFolderOpener


class FakeDevice:
    def __init__(self, *, hierarchy="<hierarchy />", screenshot=b"png"):
        self.hierarchy = hierarchy
        self.screenshot_bytes = screenshot
        self.dumps = []
        self.screenshots = []

    def dump_hierarchy(self, *, compressed):
        self.dumps.append(compressed)
        return self.hierarchy

    def screenshot(self, destination):
        self.screenshots.append(destination)
        with open(destination, "wb") as output:
            output.write(self.screenshot_bytes)


def test_snapshot_uses_shared_timestamp_and_expected_device_directory(tmp_path):
    device = FakeDevice()
    service = DeviceSnapshotService(
        tmp_path,
        connector=lambda serial: device if serial == "SERIAL-1" else None,
        clock=lambda: datetime(2026, 9, 11, 14, 5, 9, tzinfo=timezone.utc),
    )

    snapshot = service.capture("SERIAL-1")

    assert snapshot.timestamp == "2026-09-11_14-05-09"
    assert snapshot.directory == tmp_path / "snapshots" / "SERIAL-1"
    assert snapshot.hierarchy_path.name == "2026-09-11_14-05-09.xml"
    assert snapshot.screenshot_path.name == "2026-09-11_14-05-09.png"
    assert snapshot.hierarchy_path.read_text(encoding="utf-8") == "<hierarchy />"
    assert snapshot.screenshot_path.read_bytes() == b"png"
    assert device.dumps == [False]


def test_snapshot_never_overwrites_an_existing_timestamp(tmp_path):
    directory = tmp_path / "snapshots" / "SERIAL-1"
    directory.mkdir(parents=True)
    existing = directory / "2026-09-11_14-05-09.xml"
    existing.write_text("original", encoding="utf-8")
    service = DeviceSnapshotService(
        tmp_path,
        connector=lambda _serial: FakeDevice(),
        clock=lambda: datetime(2026, 9, 11, 14, 5, 9, tzinfo=timezone.utc),
    )

    snapshot = service.capture("SERIAL-1")

    assert existing.read_text(encoding="utf-8") == "original"
    assert snapshot.timestamp == "2026-09-11_14-05-10"


def test_failed_snapshot_leaves_no_partial_pair(tmp_path):
    service = DeviceSnapshotService(
        tmp_path,
        connector=lambda _serial: FakeDevice(screenshot=b""),
        clock=lambda: datetime(2026, 9, 11, 14, 5, 9, tzinfo=timezone.utc),
    )

    with pytest.raises(RuntimeError, match="Saving screenshot failed"):
        service.capture("SERIAL-1")

    directory = tmp_path / "snapshots" / "SERIAL-1"
    assert list(directory.iterdir()) == []


@pytest.mark.parametrize(("returncode", "opened"), ((0, True), (10, False)))
def test_snapshot_folder_opener_avoids_duplicate_explorer_windows(
    tmp_path, returncode, opened
):
    calls = []

    def runner(command, **options):
        calls.append((command, options))
        return subprocess.CompletedProcess(command, returncode, "", "")

    result = SnapshotFolderOpener(command_runner=runner).open_if_needed(tmp_path)

    assert result is opened
    assert calls[0][0][-1] == SnapshotFolderOpener._SCRIPT
    assert calls[0][1]["env"]["IGBOT_SNAPSHOT_DIRECTORY"] == str(tmp_path.resolve())
    assert calls[0][1]["timeout"] == 5


def test_snapshot_logs_each_verified_output_path(tmp_path, caplog):
    service = DeviceSnapshotService(tmp_path, connector=lambda _serial: FakeDevice())

    with caplog.at_level("INFO"):
        snapshot = service.capture("SERIAL-1")

    assert "[Snapshot] Capturing UI hierarchy..." in caplog.text
    assert f"[Snapshot] XML saved:\n{snapshot.hierarchy_path}" in caplog.text
    assert "[Snapshot] Capturing screenshot..." in caplog.text
    assert f"[Snapshot] Screenshot saved:\n{snapshot.screenshot_path}" in caplog.text


def test_snapshot_reports_the_failed_capture_stage(tmp_path):
    class BrokenDevice(FakeDevice):
        def dump_hierarchy(self, *, compressed):
            raise TimeoutError("hierarchy timed out")

    service = DeviceSnapshotService(tmp_path, connector=lambda _serial: BrokenDevice())

    with pytest.raises(
        RuntimeError, match="Capturing UI hierarchy failed: hierarchy timed out"
    ):
        service.capture("SERIAL-1")
