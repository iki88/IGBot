import pytest

from IGBot.core.device import DeviceRecord
from IGBot.services.account_assignment_service import AccountAssignmentService
from IGBot.services.transfer_service import TransferService
from IGBot.ui.controllers.device_controller import DeviceController


def _service(tmp_path, configs):
    accounts_directory = tmp_path / "accounts"
    accounts_directory.mkdir()
    for folder, username, device in configs:
        directory = accounts_directory / folder
        directory.mkdir()
        (directory / "config.yml").write_text(
            f"username: {username}\ndevice: {device}\n", encoding="utf-8"
        )
    return TransferService(AccountAssignmentService(accounts_directory))


def test_transfer_validation_resolves_configured_username_not_folder_name(tmp_path):
    service = _service(tmp_path, [("testaccount", "real_account", "phone-a")])

    result = service.validate_transfer(
        "real_account", "phone-a", "phone-b", {"phone-a", "phone-b"}
    )

    assert result.valid is True
    assert result.config_path == tmp_path / "accounts" / "testaccount" / "config.yml"


def test_transfer_validation_rejects_unknown_destination(tmp_path):
    service = _service(tmp_path, [("account", "real_account", "phone-a")])

    result = service.validate_transfer(
        "real_account", "phone-a", "missing", {"phone-a", "phone-b"}
    )

    assert result.valid is False
    assert "destination" in result.error


def test_transfer_validation_rejects_same_device(tmp_path):
    service = _service(tmp_path, [("account", "real_account", "phone-a")])

    result = service.validate_transfer(
        "real_account", "phone-a", "phone-a", {"phone-a"}
    )

    assert result.valid is False
    assert "differ" in result.error


def test_transfer_validation_rejects_ambiguous_account_identity(tmp_path):
    service = _service(
        tmp_path,
        [("first", "real_account", "phone-a"), ("second", "real_account", "phone-a")],
    )

    result = service.validate_transfer(
        "real_account", "phone-a", "phone-b", {"phone-a", "phone-b"}
    )

    assert result.valid is False
    assert "Multiple" in result.error


def test_transfer_validation_never_changes_account_configuration(tmp_path):
    service = _service(tmp_path, [("account", "real_account", "phone-a")])
    config_path = tmp_path / "accounts" / "account" / "config.yml"
    original = config_path.read_bytes()

    service.validate_transfer(
        "real_account", "phone-a", "phone-b", {"phone-a", "phone-b"}
    )

    assert config_path.read_bytes() == original


def test_transfer_updates_only_existing_device_assignment(tmp_path):
    service = _service(tmp_path, [("testaccount", "real_account", "phone-a")])
    config_path = tmp_path / "accounts" / "testaccount" / "config.yml"
    config_path.write_text(
        "# preserve comment\nusername: real_account\ndevice: phone-a # assigned\n"
        "app-id: com.instagram.android\n",
        encoding="utf-8",
    )

    result = service.transfer(
        "real_account", "phone-a", "phone-b", {"phone-a", "phone-b"}
    )

    assert result.valid
    assert config_path.read_text(encoding="utf-8") == (
        "# preserve comment\nusername: real_account\ndevice: phone-b # assigned\n"
        "app-id: com.instagram.android\n"
    )


def test_transfer_rejects_duplicate_destination_without_writing(tmp_path):
    service = _service(
        tmp_path,
        [("first", "real_account", "phone-a"), ("second", "real_account", "phone-b")],
    )
    config_path = tmp_path / "accounts" / "first" / "config.yml"
    original = config_path.read_bytes()

    with pytest.raises(ValueError, match="already contains"):
        service.transfer("real_account", "phone-a", "phone-b", {"phone-a", "phone-b"})

    assert config_path.read_bytes() == original


def test_successful_transfer_generates_audit_log(tmp_path, caplog):
    service = _service(tmp_path, [("account", "real_account", "phone-a")])

    with caplog.at_level("INFO"):
        service.transfer("real_account", "phone-a", "phone-b", {"phone-a", "phone-b"})

    assert "Transferred account real_account" in caplog.text
    assert "phone-a" in caplog.text
    assert "phone-b" in caplog.text


def test_transfer_restores_original_configuration_when_verification_fails(
    tmp_path, monkeypatch
):
    service = _service(tmp_path, [("account", "real_account", "phone-a")])
    config_path = tmp_path / "accounts" / "account" / "config.yml"
    original = config_path.read_bytes()
    original_write = service._write_atomic
    calls = 0

    def write_with_initial_corruption(path, content):
        nonlocal calls
        calls += 1
        original_write(path, "device: incorrect\n" if calls == 1 else content)

    monkeypatch.setattr(service, "_write_atomic", write_with_initial_corruption)

    with pytest.raises(RuntimeError, match="original was restored"):
        service.transfer("real_account", "phone-a", "phone-b", {"phone-a", "phone-b"})

    assert config_path.read_bytes() == original


def test_completed_transfer_refreshes_inventory_and_logs_phone_names(mocker, caplog):
    controller = DeviceController(mocker.Mock())
    refresh = mocker.patch.object(controller, "refresh")
    source = DeviceRecord("phone-a", "T1", True)
    destination = DeviceRecord("phone-b", "T5", True)

    with caplog.at_level("INFO"):
        controller._on_transfer_completed("real_account", source, destination)

    refresh.assert_called_once()
    assert "Transferred account real_account: T1 → T5" in caplog.text
