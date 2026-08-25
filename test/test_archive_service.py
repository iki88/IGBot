from IGBot.core.device import DeviceRecord
from IGBot.services.account_assignment_service import AccountAssignmentService
from IGBot.services.archive_service import ARCHIVED_ACCOUNTS, ArchiveService
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
    return ArchiveService(AccountAssignmentService(accounts_directory))


def test_archive_validation_accepts_one_active_account(tmp_path):
    service = _service(tmp_path, [("folder", "real_account", "phone-a")])

    result = service.validate_archive("real_account", "phone-a")

    assert result.valid
    assert result.config_path == tmp_path / "accounts" / "folder" / "config.yml"


def test_archive_validation_rejects_already_archived_account(tmp_path):
    service = _service(tmp_path, [("folder", "real_account", ARCHIVED_ACCOUNTS)])

    result = service.archive("real_account", ARCHIVED_ACCOUNTS)

    assert not result.valid
    assert "already archived" in result.error


def test_archive_validation_rejects_duplicate_username(tmp_path):
    service = _service(
        tmp_path,
        [("first", "real_account", "phone-a"), ("second", "real_account", "phone-a")],
    )

    result = service.archive("real_account", "phone-a")

    assert not result.valid
    assert "Multiple" in result.error


def test_archive_validation_rejects_missing_configuration(tmp_path):
    service = _service(tmp_path, [])

    result = service.archive("missing", "phone-a")

    assert not result.valid
    assert "not assigned" in result.error


def test_archive_validation_never_changes_configuration(tmp_path):
    service = _service(tmp_path, [("folder", "real_account", "phone-a")])
    config_path = tmp_path / "accounts" / "folder" / "config.yml"
    original = config_path.read_bytes()

    service.validate_archive("real_account", "phone-a")

    assert config_path.read_bytes() == original


def test_archive_updates_only_existing_device_assignment(tmp_path):
    service = _service(tmp_path, [("folder", "real_account", "phone-a")])
    config_path = tmp_path / "accounts" / "folder" / "config.yml"
    config_path.write_text(
        "# preserve comment\nusername: real_account\ndevice: phone-a # assigned\n"
        "app-id: com.instagram.android\n",
        encoding="utf-8",
    )

    result = service.archive("real_account", "phone-a")

    assert result.valid
    assert config_path.read_text(encoding="utf-8") == (
        "# preserve comment\nusername: real_account\n"
        "device: ARCHIVED_ACCOUNTS # assigned\n"
        "app-id: com.instagram.android\n"
    )


def test_archive_returns_failure_for_already_archived_account_without_changes(tmp_path):
    service = _service(tmp_path, [("folder", "real_account", ARCHIVED_ACCOUNTS)])
    config_path = tmp_path / "accounts" / "folder" / "config.yml"
    original = config_path.read_bytes()

    result = service.archive("real_account", ARCHIVED_ACCOUNTS)

    assert not result.valid
    assert config_path.read_bytes() == original


def test_archive_restores_configuration_when_verification_fails(tmp_path, monkeypatch):
    service = _service(tmp_path, [("folder", "real_account", "phone-a")])
    config_path = tmp_path / "accounts" / "folder" / "config.yml"
    original = config_path.read_bytes()
    writer = service._transfer_validation._write_atomic
    calls = 0

    def write_with_initial_corruption(path, content):
        nonlocal calls
        calls += 1
        writer(path, "device: incorrect\n" if calls == 1 else content)

    monkeypatch.setattr(
        service._transfer_validation, "_write_atomic", write_with_initial_corruption
    )

    result = service.archive("real_account", "phone-a")

    assert not result.valid
    assert "original was restored" in result.error
    assert config_path.read_bytes() == original


def test_archive_returns_structured_failure_for_invalid_account(tmp_path):
    service = _service(tmp_path, [])

    result = service.archive("missing", "phone-a")

    assert not result.valid
    assert "not assigned" in result.error


def test_successful_archive_refreshes_inventory_and_logs_phone_name(mocker, caplog):
    controller = DeviceController(mocker.Mock())
    controller._records = {"phone-a": DeviceRecord("phone-a", "T1", True)}
    refresh = mocker.patch.object(controller, "refresh")
    result = mocker.Mock(valid=True, username="real_account", source_serial="phone-a")

    with caplog.at_level("INFO"):
        controller._on_archive_completed(result)

    refresh.assert_called_once()
    assert "Archived account real_account: T1 → Archived" in caplog.text


def test_archive_request_starts_worker_and_surfaces_worker_exceptions(mocker):
    service = mocker.Mock()
    controller = DeviceController(service)
    task_started = mocker.patch.object(controller._thread_pool, "start")
    failures = []
    controller.archive_failed.connect(failures.append)

    controller.request_account_archive("real_account", "phone-a")

    task_started.assert_called_once()
    task = task_started.call_args.args[0]
    service.archive_service.archive.side_effect = RuntimeError("write failed")
    task.run()

    assert failures == ["write failed"]


def test_restore_updates_only_existing_archived_device_assignment(tmp_path):
    service = _service(tmp_path, [("folder", "real_account", ARCHIVED_ACCOUNTS)])
    config_path = tmp_path / "accounts" / "folder" / "config.yml"
    config_path.write_text(
        "# preserve comment\nusername: real_account\n"
        "device: ARCHIVED_ACCOUNTS # archived\n"
        "app-id: com.instagram.android\n",
        encoding="utf-8",
    )

    result = service.restore("real_account", "phone-a", {"phone-a"})

    assert result.valid
    assert config_path.read_text(encoding="utf-8") == (
        "# preserve comment\nusername: real_account\n"
        "device: phone-a # archived\n"
        "app-id: com.instagram.android\n"
    )


def test_restore_rejects_unmanaged_destination_without_changes(tmp_path):
    service = _service(tmp_path, [("folder", "real_account", ARCHIVED_ACCOUNTS)])
    config_path = tmp_path / "accounts" / "folder" / "config.yml"
    original = config_path.read_bytes()

    result = service.restore("real_account", "missing", {"phone-a"})

    assert not result.valid
    assert "destination" in result.error
    assert config_path.read_bytes() == original


def test_restore_rejects_already_active_account_without_changes(tmp_path):
    service = _service(tmp_path, [("folder", "real_account", "phone-a")])
    config_path = tmp_path / "accounts" / "folder" / "config.yml"
    original = config_path.read_bytes()

    result = service.restore("real_account", "phone-b", {"phone-a", "phone-b"})

    assert not result.valid
    assert "not assigned" in result.error
    assert config_path.read_bytes() == original


def test_restore_rejects_duplicate_account_on_destination(tmp_path):
    service = _service(
        tmp_path,
        [
            ("archived", "real_account", ARCHIVED_ACCOUNTS),
            ("active", "real_account", "phone-a"),
        ],
    )

    result = service.restore("real_account", "phone-a", {"phone-a"})

    assert not result.valid
    assert "already contains" in result.error


def test_restore_rolls_back_when_verification_fails(tmp_path, monkeypatch):
    service = _service(tmp_path, [("folder", "real_account", ARCHIVED_ACCOUNTS)])
    config_path = tmp_path / "accounts" / "folder" / "config.yml"
    original = config_path.read_bytes()
    writer = service._transfer_validation._write_atomic
    calls = 0

    def write_with_initial_corruption(path, content):
        nonlocal calls
        calls += 1
        writer(path, "device: incorrect\n" if calls == 1 else content)

    monkeypatch.setattr(
        service._transfer_validation, "_write_atomic", write_with_initial_corruption
    )

    result = service.restore("real_account", "phone-a", {"phone-a"})

    assert not result.valid
    assert "original was restored" in result.error
    assert config_path.read_bytes() == original


def test_successful_restore_refreshes_archived_and_logs_phone_name(mocker, caplog):
    controller = DeviceController(mocker.Mock())
    controller._records = {"phone-a": DeviceRecord("phone-a", "T3", True)}
    refresh = mocker.patch.object(controller, "refresh")
    refresh_archived = mocker.patch.object(controller, "load_archived_accounts")
    result = mocker.Mock(
        valid=True,
        username="real_account",
        destination_serial="phone-a",
    )

    with caplog.at_level("INFO"):
        controller._on_restore_completed(result)

    refresh.assert_called_once()
    refresh_archived.assert_called_once()
    assert "Restored account real_account: Archived → T3" in caplog.text


def test_failed_restore_surfaces_validation_error_without_refresh(mocker):
    controller = DeviceController(mocker.Mock())
    refresh = mocker.patch.object(controller, "refresh")
    failures = []
    controller.restore_failed.connect(failures.append)
    result = mocker.Mock(valid=False, error="The destination device is not managed.")

    controller._on_restore_completed(result)

    assert failures == ["The destination device is not managed."]
    refresh.assert_not_called()


def test_delete_archived_account_removes_entire_account_directory(tmp_path):
    service = _service(tmp_path, [("folder", "real_account", ARCHIVED_ACCOUNTS)])
    directory = tmp_path / "accounts" / "folder"
    nested = directory / "session"
    nested.mkdir()
    (nested / "state.json").write_text("session data", encoding="utf-8")

    result = service.delete_archived("real_account")

    assert result.valid
    assert not directory.exists()


def test_delete_archived_rejects_active_account_without_changes(tmp_path):
    service = _service(tmp_path, [("folder", "real_account", "phone-a")])
    config_path = tmp_path / "accounts" / "folder" / "config.yml"
    original = config_path.read_bytes()

    result = service.delete_archived("real_account")

    assert not result.valid
    assert "not archived" in result.error
    assert config_path.read_bytes() == original


def test_delete_archived_rejects_account_also_assigned_to_active_device(tmp_path):
    service = _service(
        tmp_path,
        [
            ("archived", "real_account", ARCHIVED_ACCOUNTS),
            ("active", "real_account", "phone-a"),
        ],
    )

    result = service.delete_archived("real_account")

    assert not result.valid
    assert "active device" in result.error
    assert (tmp_path / "accounts" / "archived").is_dir()


def test_delete_archived_rejects_missing_account_directory(tmp_path, mocker):
    service = _service(tmp_path, [("folder", "real_account", ARCHIVED_ACCOUNTS)])
    assignments = service._account_assignments.load_by_device()
    directory = tmp_path / "accounts" / "folder"
    (directory / "config.yml").unlink()
    directory.rmdir()
    mocker.patch.object(
        service._account_assignments, "load_by_device", return_value=assignments
    )

    result = service.delete_archived("real_account")

    assert not result.valid
    assert "directory does not exist" in result.error


def test_delete_archived_restores_original_after_partial_failure(tmp_path, monkeypatch):
    service = _service(tmp_path, [("folder", "real_account", ARCHIVED_ACCOUNTS)])
    directory = tmp_path / "accounts" / "folder"
    extra = directory / "important.txt"
    extra.write_text("preserve me", encoding="utf-8")
    original_rmtree = __import__("shutil").rmtree
    calls = 0

    def fail_first_removal(path, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            extra.unlink()
            raise OSError("deletion interrupted")
        return original_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(
        "IGBot.services.archive_service.shutil.rmtree", fail_first_removal
    )

    result = service.delete_archived("real_account")

    assert not result.valid
    assert "original was restored" in result.error
    assert extra.read_text(encoding="utf-8") == "preserve me"
    assert (directory / "config.yml").is_file()


def test_successful_archived_deletion_refreshes_and_generates_audit_log(mocker, caplog):
    controller = DeviceController(mocker.Mock())
    refresh = mocker.patch.object(controller, "refresh")
    refresh_archived = mocker.patch.object(controller, "load_archived_accounts")
    result = mocker.Mock(valid=True, username="real_account")

    with caplog.at_level("INFO"):
        controller._on_archived_account_deleted(result)

    refresh.assert_called_once()
    refresh_archived.assert_called_once()
    assert "Deleted archived account real_account: Archived → Deleted" in caplog.text


def test_failed_archived_deletion_surfaces_error_without_refresh(mocker):
    controller = DeviceController(mocker.Mock())
    refresh = mocker.patch.object(controller, "refresh")
    failures = []
    controller.account_deletion_failed.connect(failures.append)
    result = mocker.Mock(valid=False, error="The account is not archived.")

    controller._on_archived_account_deleted(result)

    assert failures == ["The account is not archived."]
    refresh.assert_not_called()
