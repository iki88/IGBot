import shutil
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from IGBot.services.account_assignment_service import AccountAssignmentService
from IGBot.services.transfer_service import TransferService, TransferValidationResult

ARCHIVED_ACCOUNTS = "ARCHIVED_ACCOUNTS"


@dataclass(frozen=True)
class ArchiveValidationResult:
    """Structured result of a read-only account archive preflight."""

    valid: bool
    username: str
    source_serial: str
    config_path: Path | None = None
    error: str | None = None


class ArchiveService:
    """Safely validate and archive existing account device assignments."""

    def __init__(self, account_assignments: AccountAssignmentService) -> None:
        self._account_assignments = account_assignments
        self._transfer_validation = TransferService(account_assignments)

    def validate_archive(
        self, username: str, source_serial: str
    ) -> ArchiveValidationResult:
        username = username.strip()
        source_serial = source_serial.strip()

        def invalid(message: str) -> ArchiveValidationResult:
            return ArchiveValidationResult(
                False, username, source_serial, error=message
            )

        if not username:
            return invalid("An account username is required.")
        if not source_serial:
            return invalid("The account must be assigned to an active device.")

        assignments = self._account_assignments.load_by_device()
        archived = [
            account
            for account in assignments.get(ARCHIVED_ACCOUNTS, ())
            if account.username == username
        ]
        if source_serial == ARCHIVED_ACCOUNTS or archived:
            return invalid("The account is already archived.")

        matches = [
            account
            for account in assignments.get(source_serial, ())
            if account.username == username
        ]
        if not matches:
            return invalid("The account is not assigned to the source device.")
        if len(matches) != 1:
            return invalid("Multiple account configurations match this account.")

        account = matches[0]
        path_error = self._transfer_validation._validate_config_path(account)
        if path_error:
            return invalid(path_error)
        return ArchiveValidationResult(
            True, username, source_serial, config_path=account.config_path
        )

    def archive(self, username: str, source_serial: str) -> ArchiveValidationResult:
        """Archive one account through the shared verified atomic assignment writer."""
        result = self.validate_archive(username, source_serial)
        if not result.valid or result.config_path is None:
            return result

        assignment = TransferValidationResult(
            valid=True,
            username=result.username,
            source_serial=result.source_serial,
            destination_serial=ARCHIVED_ACCOUNTS,
            config_path=result.config_path,
        )
        try:
            self._transfer_validation._update_assignment(assignment)
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            return ArchiveValidationResult(
                False,
                result.username,
                result.source_serial,
                config_path=result.config_path,
                error=str(error),
            )
        return result

    def restore(
        self, username: str, destination_serial: str, managed_serials: set[str]
    ) -> TransferValidationResult:
        """Restore an archived account using the existing verified assignment writer."""
        result = self._transfer_validation.validate_transfer(
            username,
            ARCHIVED_ACCOUNTS,
            destination_serial,
            managed_serials | {ARCHIVED_ACCOUNTS},
        )
        if not result.valid or result.config_path is None:
            return result

        try:
            self._transfer_validation._update_assignment(result)
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            return TransferValidationResult(
                False,
                result.username,
                result.source_serial,
                result.destination_serial,
                config_path=result.config_path,
                error=str(error),
            )
        return result

    def delete_archived(self, username: str) -> ArchiveValidationResult:
        """Permanently delete one verified archived account with recovery protection."""
        username = username.strip()

        def invalid(message: str) -> ArchiveValidationResult:
            return ArchiveValidationResult(
                False, username, ARCHIVED_ACCOUNTS, error=message
            )

        if not username:
            return invalid("An account username is required.")

        assignments = self._account_assignments.load_by_device()
        archived = [
            account
            for account in assignments.get(ARCHIVED_ACCOUNTS, ())
            if account.username == username
        ]
        if len(archived) != 1:
            return invalid(
                "The account is not archived."
                if not archived
                else "Multiple archived account configurations match this account."
            )
        if any(
            account.username == username
            for device_id, accounts in assignments.items()
            if device_id != ARCHIVED_ACCOUNTS
            for account in accounts
        ):
            return invalid("The account is still assigned to an active device.")

        account = archived[0]
        directory = account.config_path.parent
        if not directory.is_dir():
            return invalid("The archived account directory does not exist.")
        if directory.is_symlink() or (
            hasattr(directory, "is_junction") and directory.is_junction()
        ):
            return invalid("The archived account directory cannot be a linked folder.")

        accounts_root = self._account_assignments.accounts_directory.resolve()
        if directory.resolve().parent != accounts_root:
            return invalid(
                "The account directory is outside the managed accounts root."
            )
        path_error = self._transfer_validation._validate_config_path(account)
        if path_error:
            return invalid(path_error)

        current = self._account_assignments._load_account(account.config_path)
        if (
            current is None
            or current.username != username
            or current.device_id != ARCHIVED_ACCOUNTS
        ):
            return invalid("The account is no longer archived.")

        try:
            with TemporaryDirectory(prefix="igbot-archive-delete-") as backup_root:
                backup = Path(backup_root) / "account"
                shutil.copytree(directory, backup)
                try:
                    shutil.rmtree(directory)
                except OSError as error:
                    try:
                        shutil.copytree(backup, directory, dirs_exist_ok=True)
                    except OSError as restore_error:
                        raise RuntimeError(
                            "Account deletion failed and the original account "
                            f"could not be restored: {restore_error}"
                        ) from error
                    return invalid(
                        f"Account deletion failed; the original was restored: {error}"
                    )
        except (OSError, RuntimeError) as error:
            return invalid(str(error))

        return ArchiveValidationResult(
            True, username, ARCHIVED_ACCOUNTS, config_path=account.config_path
        )
