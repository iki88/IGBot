import json

import pytest

from IGBot.core.phone_manager import DeviceDiscoveryResult
from IGBot.services.account_assignment_service import AccountAssignmentService
from IGBot.services.archive_service import ARCHIVED_ACCOUNTS
from IGBot.services.device_inventory_service import DeviceInventoryService


def _service(tmp_path):
    accounts_directory = tmp_path / "accounts"
    accounts_directory.mkdir()
    return DeviceInventoryService(
        inventory_path=tmp_path / "data" / "devices.json",
        account_assignments=AccountAssignmentService(accounts_directory),
    )


def test_refresh_preserves_manual_order_and_marks_disconnected_phone_offline(
    tmp_path, mocker
):
    service = _service(tmp_path)
    service._save_state(
        {
            "devices": [
                {"serial": "phone-b", "phone_name": ""},
                {"serial": "phone-a", "phone_name": ""},
            ],
            "deleted": [],
        }
    )
    discover = mocker.patch(
        "IGBot.services.device_inventory_service.PhoneManager.discover_devices",
        side_effect=[
            DeviceDiscoveryResult(["phone-b", "phone-a"]),
            DeviceDiscoveryResult(["phone-a"]),
        ],
    )

    first = service.refresh()
    second = service.refresh()

    assert [device.serial for device in first.devices] == ["phone-b", "phone-a"]
    assert [device.serial for device in second.devices] == ["phone-b", "phone-a"]
    assert second.devices[0].connected is False
    assert second.devices[0].status == "Offline"
    assert second.devices[1].connected is True
    assert discover.call_count == 2


def test_refresh_counts_only_real_assigned_accounts(tmp_path, mocker):
    accounts_directory = tmp_path / "accounts"
    assigned = accounts_directory / "assigned"
    unassigned = accounts_directory / "unassigned"
    assigned.mkdir(parents=True)
    unassigned.mkdir()
    (assigned / "config.yml").write_text(
        "username: real_account\ndevice: phone-a\napp-id: com.instagram.android\n",
        encoding="utf-8",
    )
    (unassigned / "config.yml").write_text("username: not_assigned\n", encoding="utf-8")
    service = DeviceInventoryService(
        inventory_path=tmp_path / "devices.json",
        account_assignments=AccountAssignmentService(accounts_directory),
    )
    service._save_state(
        {"devices": [{"serial": "phone-a", "phone_name": ""}], "deleted": []}
    )
    mocker.patch(
        "IGBot.services.device_inventory_service.PhoneManager.discover_devices",
        return_value=DeviceDiscoveryResult(["phone-a"]),
    )

    snapshot = service.refresh()

    assert [account.username for account in snapshot.devices[0].accounts] == [
        "real_account"
    ]


def test_delete_blocks_populated_phone_without_modifying_account_data(tmp_path, mocker):
    accounts_directory = tmp_path / "accounts"
    account_directory = accounts_directory / "assigned"
    account_directory.mkdir(parents=True)
    config_path = account_directory / "config.yml"
    config_path.write_text(
        "username: real_account\ndevice: phone-a\napp-id: com.instagram.android\n",
        encoding="utf-8",
    )
    service = DeviceInventoryService(
        inventory_path=tmp_path / "data" / "devices.json",
        account_assignments=AccountAssignmentService(accounts_directory),
    )
    service._save_state(
        {"devices": [{"serial": "phone-a", "phone_name": ""}], "deleted": []}
    )
    mocker.patch(
        "IGBot.services.device_inventory_service.PhoneManager.discover_devices",
        side_effect=[
            DeviceDiscoveryResult(["phone-a"]),
            DeviceDiscoveryResult(["phone-a"]),
            DeviceDiscoveryResult([]),
            DeviceDiscoveryResult(["phone-a"]),
        ],
    )
    service.refresh()
    original_config = config_path.read_bytes()

    with pytest.raises(RuntimeError, match="currently contains assigned accounts"):
        service.delete("phone-a")

    saved = json.loads((tmp_path / "data" / "devices.json").read_text())
    assert [device["serial"] for device in saved["devices"]] == ["phone-a"]
    assert saved["deleted"] == []
    assert config_path.read_bytes() == original_config


def test_delete_permanently_removes_empty_phone(tmp_path, mocker):
    service = _service(tmp_path)
    service._save_state(
        {"devices": [{"serial": "phone-a", "phone_name": ""}], "deleted": []}
    )
    mocker.patch(
        "IGBot.services.device_inventory_service.PhoneManager.discover_devices",
        side_effect=[
            DeviceDiscoveryResult(["phone-a"]),
            DeviceDiscoveryResult(["phone-a"]),
            DeviceDiscoveryResult([]),
            DeviceDiscoveryResult(["phone-a"]),
        ],
    )

    service.refresh()
    service.delete("phone-a")

    assert service.refresh().devices == ()
    assert service.refresh().devices == ()
    assert service.refresh().devices == ()
    saved = json.loads((tmp_path / "data" / "devices.json").read_text())
    assert saved["deleted"] == ["phone-a"]


def test_legacy_suppression_is_migrated_to_permanent_deletion(tmp_path, mocker):
    service = _service(tmp_path)
    inventory_path = tmp_path / "data" / "devices.json"
    inventory_path.parent.mkdir()
    inventory_path.write_text(
        json.dumps({"devices": [], "suppressed": ["phone-a"]}),
        encoding="utf-8",
    )
    mocker.patch(
        "IGBot.services.device_inventory_service.PhoneManager.discover_devices",
        return_value=DeviceDiscoveryResult(["phone-a"]),
    )

    snapshot = service.refresh()

    assert snapshot.devices == ()
    saved = json.loads(inventory_path.read_text(encoding="utf-8"))
    assert saved == {"devices": [], "deleted": ["phone-a"]}


def test_connected_devices_require_explicit_onboarding(tmp_path, mocker):
    service = _service(tmp_path)
    mocker.patch(
        "IGBot.services.device_inventory_service.PhoneManager.discover_devices",
        return_value=DeviceDiscoveryResult(["phone-a", "phone-b"]),
    )

    assert service.refresh().devices == ()
    assert service.unmanaged_devices() == ("phone-a", "phone-b")

    service.add_device("phone-a", "Office 01")

    snapshot = service.refresh()
    assert [(item.serial, item.phone_name) for item in snapshot.devices] == [
        ("phone-a", "Office 01")
    ]
    assert service.unmanaged_devices() == ("phone-b",)


def test_rename_persists_without_changing_device_identifier(tmp_path, mocker):
    service = _service(tmp_path)
    mocker.patch(
        "IGBot.services.device_inventory_service.PhoneManager.discover_devices",
        return_value=DeviceDiscoveryResult(["phone-a"]),
    )
    service.add_device("phone-a", "Original")

    service.rename_device("phone-a", "Samsung Office")

    device = service.refresh().devices[0]
    assert device.serial == "phone-a"
    assert device.phone_name == "Samsung Office"


def test_device_folder_uses_stable_serial(tmp_path, mocker):
    service = _service(tmp_path)
    mocker.patch(
        "IGBot.services.device_inventory_service.PhoneManager.discover_devices",
        return_value=DeviceDiscoveryResult(["phone-a"]),
    )
    service.add_device("phone-a", "Office")

    directory = service.device_directory("phone-a")

    assert directory == tmp_path / "phones" / "phone-a"
    assert directory.is_dir()


def test_archived_container_reads_only_real_archived_accounts(tmp_path):
    service = _service(tmp_path)
    archived = tmp_path / "archived" / "real_account"
    archived.mkdir(parents=True)
    (archived / "config.yml").write_text("username: real_account\n", encoding="utf-8")

    accounts = service.archived_accounts()

    assert [account.username for account in accounts] == ["real_account"]


def test_archived_workspace_reads_reserved_account_assignments(tmp_path):
    service = _service(tmp_path)
    account = tmp_path / "accounts" / "archived_account"
    account.mkdir()
    (account / "config.yml").write_text(
        f"username: real_account\ndevice: {ARCHIVED_ACCOUNTS}\n",
        encoding="utf-8",
    )

    accounts = service.archived_accounts()

    assert [item.username for item in accounts] == ["real_account"]


def test_archiving_removes_account_from_phone_and_updates_counts(tmp_path, mocker):
    service = _service(tmp_path)
    service._save_state(
        {"devices": [{"serial": "phone-a", "phone_name": "T1"}], "deleted": []}
    )
    account = tmp_path / "accounts" / "real_account"
    account.mkdir()
    (account / "config.yml").write_text(
        "username: real_account\ndevice: phone-a\n", encoding="utf-8"
    )
    mocker.patch(
        "IGBot.services.device_inventory_service.PhoneManager.discover_devices",
        return_value=DeviceDiscoveryResult(["phone-a"]),
    )
    assert len(service.refresh().devices[0].accounts) == 1

    result = service.archive_service.archive("real_account", "phone-a")

    assert result.valid
    assert len(service.refresh().devices[0].accounts) == 0
    assert [item.username for item in service.archived_accounts()] == ["real_account"]
