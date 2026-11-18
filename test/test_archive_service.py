import threading

import pytest

from IGBot.core.device import DeviceRecord
from IGBot.core.session_engine import SessionState
from IGBot.notifications import (
    InProcessBlockingRetryRegistry,
    NotificationService,
    NotificationSeverity,
    NotificationType,
)
from IGBot.notifications.database import NotificationsDatabase
from IGBot.services.account_assignment_service import AccountAssignmentService
from IGBot.services.archive_service import (
    ARCHIVE_REQUIRES_STOPPED_DEVICE,
    ARCHIVED_ACCOUNTS,
    ArchiveService,
)
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


@pytest.mark.parametrize("state", (SessionState.RUNNING, SessionState.STOPPING))
def test_archive_rejects_active_phone_at_operation_boundary(tmp_path, state):
    accounts_directory = tmp_path / "accounts"
    accounts_directory.mkdir()
    directory = accounts_directory / "folder"
    directory.mkdir()
    config_path = directory / "config.yml"
    config_path.write_text(
        "username: real_account\ndevice: phone-a\n", encoding="utf-8"
    )
    service = ArchiveService(
        AccountAssignmentService(accounts_directory),
        phone_is_active=lambda serial: (
            serial == "phone-a"
            and state in {
                SessionState.STARTING,
                SessionState.RUNNING,
                SessionState.WAITING,
                SessionState.STOPPING,
            }
        ),
    )

    result = service.archive("real_account", "phone-a")

    assert not result.valid
    assert result.error == ARCHIVE_REQUIRES_STOPPED_DEVICE
    assert "device: phone-a" in config_path.read_text(encoding="utf-8")


def test_archive_allows_fully_stopped_phone(tmp_path):
    accounts_directory = tmp_path / "accounts"
    accounts_directory.mkdir()
    directory = accounts_directory / "folder"
    directory.mkdir()
    config_path = directory / "config.yml"
    config_path.write_text(
        "username: real_account\ndevice: phone-a\n", encoding="utf-8"
    )
    state = SessionState.STOPPED
    service = ArchiveService(
        AccountAssignmentService(accounts_directory),
        phone_is_active=lambda _serial: state
        in {
            SessionState.STARTING,
            SessionState.RUNNING,
            SessionState.WAITING,
            SessionState.STOPPING,
        },
    )

    result = service.archive("real_account", "phone-a")

    assert result.valid
    assert "device: ARCHIVED_ACCOUNTS" in config_path.read_text(encoding="utf-8")


def test_successful_archive_resolves_only_that_accounts_notifications(tmp_path):
    accounts_directory = tmp_path / "accounts"
    accounts_directory.mkdir()
    assignment_service = AccountAssignmentService(accounts_directory)
    for username in ("archived", "other"):
        directory = accounts_directory / username
        directory.mkdir()
        (directory / "config.yml").write_text(
            f"username: {username}\ndevice: phone-a\n", encoding="utf-8"
        )
    notifications = NotificationService(tmp_path)
    notifications.create(
        "archived",
        NotificationType.HUMAN_CAPTCHA,
        NotificationSeverity.CRITICAL,
    )
    notifications.create(
        "other",
        NotificationType.ZERO_INTERACTIONS,
        NotificationSeverity.WARNING,
    )
    service = ArchiveService(
        assignment_service, notification_service=notifications
    )

    result = service.archive("archived", "phone-a")

    assert result.valid
    assert tuple(item.username for item in notifications.active()) == ("other",)


def test_failed_archive_does_not_resolve_notifications(tmp_path):
    accounts_directory = tmp_path / "accounts"
    accounts_directory.mkdir()
    notifications = NotificationService(tmp_path)
    notifications.create(
        "missing",
        NotificationType.ACCOUNT_DISABLED,
        NotificationSeverity.CRITICAL,
    )
    service = ArchiveService(
        AccountAssignmentService(accounts_directory),
        notification_service=notifications,
    )

    result = service.archive("missing", "phone-a")

    assert not result.valid
    assert notifications.active()[0].username == "missing"


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


def test_delete_archived_purges_only_owned_notification_state(tmp_path):
    service = _service(tmp_path, [("folder", "real_account", ARCHIVED_ACCOUNTS)])
    notifications = NotificationService(tmp_path)
    service._notification_service = notifications
    directory = tmp_path / "accounts" / "folder"
    notifications.create(
        "real_account",
        NotificationType.ACCOUNT_DISABLED,
        NotificationSeverity.CRITICAL,
    )
    notifications.create(
        "other_account",
        NotificationType.ZERO_INTERACTIONS,
        NotificationSeverity.WARNING,
    )
    with NotificationsDatabase(tmp_path) as database:
        database.connection.executemany(
            """INSERT INTO account_lifecycle
               (account_key, username, device, tag, first_successful_session_at,
                consecutive_zero_interaction_sessions, updated_at)
               VALUES (?, ?, '', '', NULL, 0, 'now')""",
            (
                (str(directory.resolve()).casefold(), "real_account"),
                (str((tmp_path / "accounts" / "other").resolve()).casefold(), "other_account"),
            ),
        )
        database.connection.commit()

    result = service.delete_archived("real_account")

    assert result.valid
    assert tuple(item.username for item in notifications.all()) == ("other_account",)
    with NotificationsDatabase(tmp_path) as database:
        lifecycle = database.connection.execute(
            "SELECT username FROM account_lifecycle ORDER BY username"
        ).fetchall()
    assert [row["username"] for row in lifecycle] == ["other_account"]


def test_notification_cleanup_failure_restores_account_directory(tmp_path, mocker):
    service = _service(tmp_path, [("folder", "real_account", ARCHIVED_ACCOUNTS)])
    directory = tmp_path / "accounts" / "folder"
    important = directory / "important.txt"
    important.write_text("keep", encoding="utf-8")
    service._notification_service = mocker.Mock()
    service._notification_service.purge_account.side_effect = OSError("database locked")

    result = service.delete_archived("real_account")

    assert not result.valid
    assert "notification cleanup failed" in result.error
    assert important.read_text(encoding="utf-8") == "keep"
    assert (directory / "config.yml").is_file()


def test_delete_rejects_account_directory_symlink(tmp_path):
    accounts = tmp_path / "accounts"
    accounts.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    (external / "config.yml").write_text(
        f"username: real_account\ndevice: {ARCHIVED_ACCOUNTS}\n", encoding="utf-8"
    )
    link = accounts / "linked"
    try:
        link.symlink_to(external, target_is_directory=True)
    except OSError:
        pytest.skip("Directory symlinks require additional privileges on this platform")
    assignment = AccountAssignmentService(accounts)
    account = assignment._load_account(link / "config.yml")
    assert account is not None
    service = ArchiveService(assignment)
    service._account_assignments.load_by_device = lambda: {
        ARCHIVED_ACCOUNTS: (account,)
    }

    result = service.delete_archived("real_account")

    assert not result.valid
    assert "unsafe linked or reparse-point" in result.error
    assert (external / "config.yml").is_file()


def test_delete_rejects_nested_link_without_touching_external_data(tmp_path):
    service = _service(tmp_path, [("folder", "real_account", ARCHIVED_ACCOUNTS)])
    directory = tmp_path / "accounts" / "folder"
    external = tmp_path / "external"
    external.mkdir()
    protected = external / "protected.txt"
    protected.write_text("untouched", encoding="utf-8")
    try:
        (directory / "external-link").symlink_to(external, target_is_directory=True)
    except OSError:
        pytest.skip("Directory symlinks require additional privileges on this platform")

    result = service.delete_archived("real_account")

    assert not result.valid
    assert "unsafe linked or reparse-point" in result.error
    assert protected.read_text(encoding="utf-8") == "untouched"
    assert directory.is_dir()


def test_delete_rejects_nested_windows_junction_marker(tmp_path, monkeypatch):
    service = _service(tmp_path, [("folder", "real_account", ARCHIVED_ACCOUNTS)])
    directory = tmp_path / "accounts" / "folder"
    junction = directory / "nested-junction"
    junction.mkdir()
    original_is_junction = getattr(type(junction), "is_junction", None)
    if original_is_junction is None:
        pytest.skip("Path.is_junction is unavailable on this Python version")

    monkeypatch.setattr(
        type(junction),
        "is_junction",
        lambda path: path.name == "nested-junction" or original_is_junction(path),
    )

    result = service.delete_archived("real_account")

    assert not result.valid
    assert "unsafe linked or reparse-point" in result.error
    assert directory.is_dir()


def test_restore_and_delete_are_serialized_by_account_operation_lock(tmp_path, mocker):
    service = _service(tmp_path, [("folder", "real_account", ARCHIVED_ACCOUNTS)])
    restore_entered = threading.Event()
    release_restore = threading.Event()
    delete_entered = threading.Event()

    def restore_locked(*_args):
        restore_entered.set()
        assert release_restore.wait(timeout=2)
        return mocker.Mock(valid=True)

    def delete_locked(*_args):
        delete_entered.set()
        return mocker.Mock(valid=True)

    mocker.patch.object(service, "_restore_locked", side_effect=restore_locked)
    mocker.patch.object(service, "_delete_archived_locked", side_effect=delete_locked)
    restore_thread = threading.Thread(
        target=service.restore, args=("real_account", "phone-a", {"phone-a"})
    )
    delete_thread = threading.Thread(
        target=service.delete_archived, args=("real_account",)
    )

    restore_thread.start()
    assert restore_entered.wait(timeout=2)
    delete_thread.start()
    assert not delete_entered.wait(timeout=0.1)
    release_restore.set()
    restore_thread.join(timeout=2)
    delete_thread.join(timeout=2)

    assert delete_entered.is_set()


def test_deletion_preserves_shared_and_other_account_data(tmp_path):
    service = _service(
        tmp_path,
        [
            ("deleted", "real_account", ARCHIVED_ACCOUNTS),
            ("other", "other_account", ARCHIVED_ACCOUNTS),
        ],
    )
    deleted = tmp_path / "accounts" / "deleted"
    other = tmp_path / "accounts" / "other"
    (other / "runtime.db").write_bytes(b"other runtime")
    global_profiles = tmp_path / "global_profiles.db"
    global_profiles.write_bytes(b"shared profiles")
    application_log = tmp_path / "Logs" / "application.log"
    application_log.parent.mkdir()
    application_log.write_bytes(b"shared log")
    before_profiles = global_profiles.read_bytes()
    before_log = application_log.read_bytes()

    result = service.delete_archived("real_account")

    assert result.valid
    assert not deleted.exists()
    assert (other / "runtime.db").read_bytes() == b"other runtime"
    assert global_profiles.read_bytes() == before_profiles
    assert application_log.read_bytes() == before_log


def test_delete_clears_only_deleted_username_blocking_state(tmp_path):
    service = _service(tmp_path, [("folder", "real_account", ARCHIVED_ACCOUNTS)])
    today = __import__("datetime").datetime.now().astimezone().date()
    InProcessBlockingRetryRegistry.record_today("real_account")
    InProcessBlockingRetryRegistry.record_today("other_account")

    result = service.delete_archived("real_account")

    assert result.valid
    assert not InProcessBlockingRetryRegistry.blocked_on("real_account", today)
    assert InProcessBlockingRetryRegistry.blocked_on("other_account", today)
    InProcessBlockingRetryRegistry.discard("other_account")


def test_archive_and_restore_do_not_clear_blocking_state(tmp_path):
    service = _service(tmp_path, [("folder", "real_account", "phone-a")])
    today = __import__("datetime").datetime.now().astimezone().date()
    InProcessBlockingRetryRegistry.record_today("real_account")

    archived = service.archive("real_account", "phone-a")
    restored = service.restore("real_account", "phone-a", {"phone-a"})

    assert archived.valid
    assert restored.valid
    assert InProcessBlockingRetryRegistry.blocked_on("real_account", today)
    InProcessBlockingRetryRegistry.discard("real_account")


def test_deleted_username_can_be_created_again_with_fresh_account_data(tmp_path):
    service = _service(
        tmp_path, [("same_user", "same_user", ARCHIVED_ACCOUNTS)]
    )
    directory = tmp_path / "accounts" / "same_user"
    (directory / "runtime.db").write_bytes(b"old runtime")
    (directory / "analytics.db").write_bytes(b"old analytics")
    notifications = NotificationService(tmp_path)
    service._notification_service = notifications
    notifications.create(
        "same_user",
        NotificationType.HUMAN_CAPTCHA,
        NotificationSeverity.CRITICAL,
    )
    InProcessBlockingRetryRegistry.record_today("same_user")
    templates = tmp_path / "config-examples"
    templates.mkdir()
    (templates / "config.yml").write_text(
        'username: ""\ndevice: ""\napp-id: ""\n', encoding="utf-8"
    )

    deleted = service.delete_archived("same_user")
    recreated = service._account_assignments.create_account(
        "same_user", "new password", "phone-a", templates
    )

    assert deleted.valid
    assert recreated.username == "same_user"
    assert not (directory / "runtime.db").exists()
    assert not (directory / "analytics.db").exists()
    assert notifications.all() == ()
    assert not InProcessBlockingRetryRegistry.blocked_on(
        "same_user", __import__("datetime").datetime.now().astimezone().date()
    )


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
