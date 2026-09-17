from pathlib import Path

import pytest
import yaml

from IGBot.services.account_assignment_service import AccountAssignmentService
from IGBot.services.account_identity import AccountDirectoryKind
from IGBot.services.archive_service import ARCHIVED_ACCOUNTS, ArchiveService
from IGBot.services.transfer_service import TransferService


def _templates(tmp_path: Path) -> Path:
    templates = tmp_path / "config-examples"
    templates.mkdir()
    (templates / "config.yml").write_text(
        "username: example\n# device: example\napp-id: com.instagram.android\n",
        encoding="utf-8",
    )
    (templates / "filters.yml").write_text("skip_private: false\n", encoding="utf-8")
    return templates


def _account(service: AccountAssignmentService, username: str, device: str = "phone-a"):
    directory = service.accounts_directory / username
    directory.mkdir(parents=True)
    config = directory / "config.yml"
    config.write_text(
        f"username: {username}\ndevice: {device}\napp-id: com.instagram.android\n",
        encoding="utf-8",
    )
    return service._load_account(config)


def test_inventory_and_creation_share_canonical_config_definition(tmp_path):
    accounts = tmp_path / "accounts"
    accounts.mkdir()
    service = AccountAssignmentService(accounts)
    canonical = _account(service, "existing")
    orphan = accounts / "orphan"
    orphan.mkdir()
    (orphan / "sessions.json").write_text("[]", encoding="utf-8")

    assert service.identities.classify(canonical.config_path.parent) == (
        AccountDirectoryKind.ACCOUNT
    )
    assert service.identities.classify(orphan) == AccountDirectoryKind.ORPHAN
    assert [item.username for item in service.load_by_device()["phone-a"]] == [
        "existing"
    ]
    assert [item.username for item in service.orphaned_accounts()] == ["orphan"]

    with pytest.raises(ValueError, match="already exists"):
        service.create_account("existing", "secret", "phone-a", _templates(tmp_path))


def test_create_account_recovers_orphan_without_replacing_runtime_files(tmp_path):
    accounts = tmp_path / "accounts"
    orphan = accounts / "recovered"
    orphan.mkdir(parents=True)
    runtime_database = orphan / "runtime.db"
    history = orphan / "interacted_users.json"
    sessions = orphan / "sessions.json"
    runtime_database.write_bytes(b"runtime-state")
    history.write_text('{"preserved": true}', encoding="utf-8")
    sessions.write_text('[{"preserved": true}]', encoding="utf-8")
    service = AccountAssignmentService(accounts)

    recovered = service.create_account(
        "recovered", "secret", "phone-a", _templates(tmp_path)
    )

    assert recovered.config_path == orphan / "config.yml"
    assert runtime_database.read_bytes() == b"runtime-state"
    assert history.read_text(encoding="utf-8") == '{"preserved": true}'
    assert sessions.read_text(encoding="utf-8") == '[{"preserved": true}]'
    assert service.load_by_device()["phone-a"] == (recovered,)
    assert service.orphaned_accounts() == ()


def test_username_rename_preserves_all_account_runtime_data(tmp_path):
    accounts = tmp_path / "accounts"
    service = AccountAssignmentService(accounts)
    account = _account(service, "before")
    runtime_database = account.config_path.parent / "runtime.db"
    history = account.config_path.parent / "history" / "sessions.json"
    history.parent.mkdir()
    runtime_database.write_bytes(b"database")
    history.write_text("sessions", encoding="utf-8")

    renamed = service.update_configuration(
        account, "after", "secret", "com.instagram.android"
    )

    assert renamed.config_path.parent == accounts / "after"
    assert not (accounts / "before").exists()
    assert (accounts / "after" / "runtime.db").read_bytes() == b"database"
    assert (accounts / "after" / "history" / "sessions.json").read_text() == (
        "sessions"
    )
    assert yaml.safe_load(renamed.config_path.read_bytes())["username"] == "after"


def test_phone_move_changes_assignment_without_moving_runtime_files(tmp_path):
    accounts = tmp_path / "accounts"
    service = AccountAssignmentService(accounts)
    account = _account(service, "moving")
    runtime_database = account.config_path.parent / "runtime.db"
    runtime_database.write_bytes(b"database")

    TransferService(service).transfer(
        "moving", "phone-a", "phone-b", {"phone-a", "phone-b"}
    )

    assert runtime_database.read_bytes() == b"database"
    assert service.load_by_device()["phone-b"][0].config_path.parent == (
        accounts / "moving"
    )
    assert "phone-a" not in service.load_by_device()


def test_archive_and_restore_keep_canonical_account_and_runtime_data(tmp_path):
    accounts = tmp_path / "accounts"
    service = AccountAssignmentService(accounts)
    account = _account(service, "archivable")
    runtime_database = account.config_path.parent / "runtime.db"
    runtime_database.write_bytes(b"database")
    archive = ArchiveService(service)

    archived = archive.archive("archivable", "phone-a")
    restored = archive.restore("archivable", "phone-b", {"phone-a", "phone-b"})

    assert archived.valid
    assert restored.valid
    assert runtime_database.read_bytes() == b"database"
    assert service.identities.classify(account.config_path.parent) == (
        AccountDirectoryKind.ACCOUNT
    )
    assert ARCHIVED_ACCOUNTS not in service.load_by_device()
    assert service.load_by_device()["phone-b"][0].username == "archivable"
