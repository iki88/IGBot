import subprocess

import pytest

from IGBot.services.scrcpy_service import ScrcpyService


class _Process:
    def __init__(self, process_id: int = 42) -> None:
        self.pid = process_id
        self.return_code = None
        self.terminated = False

    def poll(self):
        return self.return_code

    def terminate(self) -> None:
        self.terminated = True


def test_scrcpy_launches_selected_device(tmp_path, mocker):
    service = ScrcpyService(tmp_path)
    executable = tmp_path / "tools" / "scrcpy" / "scrcpy.exe"
    process = _Process()
    mocker.patch.object(service, "_validate_device")
    mocker.patch.object(service, "_find_executable", return_value=executable)
    popen = mocker.patch("subprocess.Popen", return_value=process)

    result = service.launch("phone-a")

    assert result.launched and not result.reused
    assert service.has_session("phone-a")
    popen.assert_called_once_with(
        [
            str(executable),
            "-s",
            "phone-a",
            "--window-title",
            "IGBot - phone-a",
            "--no-audio",
        ],
        cwd=executable.parent,
    )


def test_duplicate_launch_reuses_existing_process(tmp_path, mocker):
    service = ScrcpyService(tmp_path)
    process = _Process()
    service._processes["phone-a"] = process
    foreground = mocker.patch.object(service, "_bring_to_foreground")
    popen = mocker.patch("subprocess.Popen")

    result = service.launch("phone-a")

    assert result.reused and not result.launched
    foreground.assert_called_once_with(process.pid)
    popen.assert_not_called()


def test_process_cleanup_removes_exited_session(tmp_path):
    service = ScrcpyService(tmp_path)
    process = _Process()
    service._processes["phone-a"] = process
    process.return_code = 1

    assert service.cleanup() == ("phone-a",)
    assert not service.has_session("phone-a")


def test_missing_scrcpy_executable_is_reported(tmp_path, mocker):
    service = ScrcpyService(tmp_path)
    mocker.patch.object(service, "_bundled_candidates", return_value=())
    mocker.patch("shutil.which", return_value=None)

    with pytest.raises(RuntimeError, match="scrcpy is unavailable"):
        service._find_executable()


def test_bundled_scrcpy_is_preferred_over_environment_and_path(tmp_path, mocker):
    service = ScrcpyService(tmp_path)
    bundled = tmp_path / "tools" / "scrcpy" / "scrcpy.exe"
    bundled.parent.mkdir(parents=True)
    bundled.touch()
    environment_copy = tmp_path / "environment" / "scrcpy.exe"
    environment_copy.parent.mkdir()
    environment_copy.touch()
    mocker.patch.dict("os.environ", {"SCRCPY_PATH": str(environment_copy)})
    which = mocker.patch("shutil.which", return_value="system-scrcpy.exe")

    assert service._find_executable() == bundled.resolve()
    which.assert_not_called()


def test_environment_directory_is_used_after_bundled_locations(tmp_path, mocker):
    service = ScrcpyService(tmp_path)
    configured_directory = tmp_path / "configured"
    configured_directory.mkdir()
    executable = configured_directory / "scrcpy.exe"
    executable.touch()
    mocker.patch.object(service, "_bundled_candidates", return_value=())
    mocker.patch.dict("os.environ", {"SCRCPY_PATH": str(configured_directory)})
    which = mocker.patch("shutil.which")

    assert service._find_executable() == executable.resolve()
    which.assert_not_called()


def test_offline_device_is_rejected(tmp_path, mocker):
    service = ScrcpyService(tmp_path)
    mocker.patch(
        "subprocess.run",
        side_effect=subprocess.CalledProcessError(
            1, ["adb"], stderr="error: device offline"
        ),
    )

    with pytest.raises(RuntimeError, match="offline or disconnected"):
        service.launch("phone-a")


def test_unauthorized_device_is_rejected(tmp_path, mocker):
    service = ScrcpyService(tmp_path)
    mocker.patch(
        "subprocess.run",
        side_effect=subprocess.CalledProcessError(
            1, ["adb"], stderr="error: device unauthorized"
        ),
    )

    with pytest.raises(RuntimeError, match="unauthorized"):
        service.launch("phone-a")
