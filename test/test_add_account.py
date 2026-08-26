import json
from pathlib import Path

import pytest
import yaml
from PySide6.QtWidgets import QApplication, QLineEdit

from IGBot.core.device import AssignedAccount, DeviceRecord
from IGBot.services.account_assignment_service import AccountAssignmentService
from IGBot.services.device_inventory_service import DeviceInventoryService
from IGBot.ui.controllers.device_controller import DeviceController
from IGBot.ui.widgets.add_account_dialog import AddAccountDialog


def _service(tmp_path):
    accounts = tmp_path / "accounts"
    accounts.mkdir()
    templates = tmp_path / "config-examples"
    templates.mkdir()
    (templates / "config.yml").write_text(
        "# existing defaults\n"
        "username: myusername # account name\n"
        "# device: put_your_device_id_there\n"
        "app-id: com.instagram.android\n"
        "screen-sleep: true\n",
        encoding="utf-8",
    )
    (templates / "filters.yml").write_text("skip-private: true\n", encoding="utf-8")
    service = DeviceInventoryService(
        inventory_path=tmp_path / "data" / "devices.json",
        account_assignments=AccountAssignmentService(accounts),
        workspace_root=tmp_path,
    )
    service._save_state(
        {"devices": [{"serial": "phone-a", "phone_name": "T1"}], "deleted": []}
    )
    return service


def test_add_account_copies_templates_and_assigns_current_phone(tmp_path):
    service = _service(tmp_path)

    account = service.add_account("real_account", "password:value#1", "phone-a")

    directory = tmp_path / "accounts" / "real_account"
    config = yaml.safe_load((directory / "config.yml").read_text(encoding="utf-8"))
    assert account.username == "real_account"
    assert account.device_id == "phone-a"
    assert account.app_id == ""
    assert config["username"] == "real_account"
    assert "password" not in config
    assert config["device"] == "phone-a"
    assert config["app-id"] == ""
    assert config["screen-sleep"] is True
    assert (directory / "filters.yml").is_file()
    metadata = json.loads((directory / "account.json").read_text(encoding="utf-8"))
    assert metadata["username"] == "real_account"
    assert metadata["password"] == "password:value#1"
    assert metadata["assigned_device_id"] == "phone-a"
    assert metadata["created_at"]

    restarted = AccountAssignmentService(tmp_path / "accounts")
    restored = restarted.load_configuration(directory / "config.yml")
    assert restored["password"] == "password:value#1"


@pytest.mark.parametrize(
    ("username", "password", "message"),
    (
        ("", "secret", "username"),
        ("real_account", "", "password"),
        ("../escape", "secret", "valid Instagram username"),
    ),
)
def test_add_account_rejects_invalid_credentials(tmp_path, username, password, message):
    service = _service(tmp_path)

    with pytest.raises(ValueError, match=message):
        service.add_account(username, password, "phone-a")

    assert list((tmp_path / "accounts").iterdir()) == []


def test_add_account_rejects_duplicate_username_case_insensitively(tmp_path):
    service = _service(tmp_path)
    service.add_account("Real_Account", "first-password", "phone-a")

    with pytest.raises(ValueError, match="already exists"):
        service.add_account("real_account", "second-password", "phone-a")

    assert len(list((tmp_path / "accounts").iterdir())) == 1


def test_add_account_rejects_unmanaged_destination(tmp_path):
    service = _service(tmp_path)

    with pytest.raises(ValueError, match="managed device inventory"):
        service.add_account("real_account", "secret", "unknown-phone")

    assert list((tmp_path / "accounts").iterdir()) == []


def test_add_account_removes_partial_directory_after_template_failure(tmp_path):
    service = _service(tmp_path)
    (tmp_path / "config-examples" / "config.yml").write_text(
        "username: myusername\n", encoding="utf-8"
    )

    with pytest.raises(RuntimeError, match="missing required configuration"):
        service.add_account("real_account", "secret", "phone-a")

    assert not (tmp_path / "accounts" / "real_account").exists()


def test_add_account_dialog_uses_current_phone_and_masks_password():
    application = QApplication.instance() or QApplication([])
    dialog = AddAccountDialog(DeviceRecord("phone-a", "T1", True))

    assert dialog.phone_name.text() == "T1"
    assert dialog.device_id.text() == "phone-a"
    assert dialog.password.echoMode() == QLineEdit.Password
    assert not dialog.add_button.isEnabled()

    dialog.username.setText("real_account")
    dialog.password.setText("secret")

    assert dialog.add_button.isEnabled()
    assert application is not None


def test_account_creation_refreshes_inventory_and_logs_without_password(mocker, caplog):
    controller = DeviceController(mocker.Mock())
    controller._records = {"phone-a": DeviceRecord("phone-a", "T1", True)}
    refresh = mocker.patch.object(controller, "refresh")
    account = AssignedAccount(
        "real_account",
        "phone-a",
        "com.instagram.android",
        Path("accounts/real_account/config.yml"),
    )

    with caplog.at_level("INFO"):
        controller._on_account_created(account)

    refresh.assert_called_once()
    assert "Added account real_account to T1" in caplog.text


def test_account_creation_worker_surfaces_validation_failures(mocker):
    service = mocker.Mock()
    controller = DeviceController(service)
    started = mocker.patch.object(controller._thread_pool, "start")
    failures = []
    controller.account_creation_failed.connect(failures.append)

    controller.add_account("real_account", "secret", "phone-a")
    task = started.call_args.args[0]
    service.add_account.side_effect = ValueError("username already exists")
    task.run()

    assert failures == ["username already exists"]
