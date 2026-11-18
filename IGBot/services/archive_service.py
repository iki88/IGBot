import logging
import os
import shutil
import stat
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from IGBot.notifications import NotificationService
from IGBot.notifications.blocking import InProcessBlockingRetryRegistry
from IGBot.services.account_assignment_service import AccountAssignmentService
from IGBot.services.transfer_service import TransferService, TransferValidationResult

ARCHIVED_ACCOUNTS = "ARCHIVED_ACCOUNTS"
ARCHIVE_REQUIRES_STOPPED_DEVICE = (
    "Please stop the device before archiving an account."
)
logger = logging.getLogger(__name__)


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

    def __init__(
        self,
        account_assignments: AccountAssignmentService,
        *,
        phone_is_active: Callable[[str], bool] = lambda _serial: False,
        notification_service: NotificationService | None = None,
    ) -> None:
        self._account_assignments = account_assignments
        self._transfer_validation = TransferService(account_assignments)
        self._phone_is_active = phone_is_active
        self._notification_service = notification_service
        self._account_operation_lock = threading.RLock()

    def set_phone_is_active(self, phone_is_active: Callable[[str], bool]) -> None:
        """Install the authoritative phone-runtime guard used at archive time."""

        self._phone_is_active = phone_is_active

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

        # Recheck at the operation boundary.  The phone may have started after
        # the operator opened or confirmed the archive dialog.
        if self._phone_is_active(result.source_serial):
            return ArchiveValidationResult(
                False,
                result.username,
                result.source_serial,
                config_path=result.config_path,
                error=ARCHIVE_REQUIRES_STOPPED_DEVICE,
            )

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
        if self._notification_service is not None:
            try:
                self._notification_service.resolve_all_for_account(result.username)
            except Exception:
                logger.exception(
                    "Archived account notification cleanup failed for %s",
                    result.username,
                )
        return result

    def restore(
        self, username: str, destination_serial: str, managed_serials: set[str]
    ) -> TransferValidationResult:
        """Restore an archived account using the existing verified assignment writer."""
        with self._account_operation_lock:
            return self._restore_locked(username, destination_serial, managed_serials)

    def _restore_locked(
        self, username: str, destination_serial: str, managed_serials: set[str]
    ) -> TransferValidationResult:
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
        with self._account_operation_lock:
            return self._delete_archived_locked(username)

    def _delete_archived_locked(self, username: str) -> ArchiveValidationResult:
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
        try:
            unsafe_path = self._unsafe_link_or_reparse_point(directory)
        except OSError as error:
            return invalid(f"The archived account directory could not be inspected: {error}")
        if unsafe_path is not None:
            return invalid(
                "The archived account directory contains an unsafe linked or "
                f"reparse-point path: {unsafe_path}"
            )

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
                    self._restore_deleted_account(backup, directory, error)
                    return invalid(
                        f"Account deletion failed; the original was restored: {error}"
                    )
                try:
                    notification_service = self._notification_service or NotificationService(
                        accounts_root.parent
                    )
                    notification_service.purge_account(username, directory)
                except Exception as error:  # noqa: BLE001 - cross-store recovery boundary
                    self._restore_deleted_account(backup, directory, error)
                    return invalid(
                        "Account notification cleanup failed; the original account "
                        f"was restored: {error}"
                    )
        except (OSError, RuntimeError) as error:
            return invalid(str(error))

        InProcessBlockingRetryRegistry.discard(username)
        return ArchiveValidationResult(
            True, username, ARCHIVED_ACCOUNTS, config_path=account.config_path
        )

    @staticmethod
    def _restore_deleted_account(
        backup: Path, directory: Path, deletion_error: BaseException
    ) -> None:
        try:
            shutil.copytree(backup, directory, dirs_exist_ok=True)
        except OSError as restore_error:
            raise RuntimeError(
                "Account deletion failed and the original account could not be "
                f"restored: {restore_error}"
            ) from deletion_error

    @staticmethod
    def _unsafe_link_or_reparse_point(root: Path) -> Path | None:
        """Return the first unsafe link/reparse point without following it."""

        pending = [root]
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        while pending:
            current = pending.pop()
            current_stat = current.stat(follow_symlinks=False)
            if current.is_symlink() or (
                hasattr(current, "is_junction") and current.is_junction()
            ) or (
                reparse_flag
                and getattr(current_stat, "st_file_attributes", 0) & reparse_flag
            ):
                return current
            if not current.is_dir():
                continue
            with os.scandir(current) as entries:
                for entry in entries:
                    path = Path(entry.path)
                    entry_stat = entry.stat(follow_symlinks=False)
                    if entry.is_symlink() or (
                        hasattr(path, "is_junction") and path.is_junction()
                    ) or (
                        reparse_flag
                        and getattr(entry_stat, "st_file_attributes", 0) & reparse_flag
                    ):
                        return path
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(path)
        return None
