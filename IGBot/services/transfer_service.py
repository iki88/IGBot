import logging
import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from atomicwrites import atomic_write

from IGBot.core.device import AssignedAccount
from IGBot.services.account_assignment_service import AccountAssignmentService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TransferValidationResult:
    """Structured outcome of a read-only account transfer preflight."""

    valid: bool
    username: str
    source_serial: str
    destination_serial: str
    config_path: Path | None = None
    error: str | None = None


class TransferService:
    """Validates account identity and safely updates existing device assignments."""

    def __init__(self, account_assignments: AccountAssignmentService) -> None:
        self._account_assignments = account_assignments

    def validate_transfer(
        self,
        username: str,
        source_serial: str,
        destination_serial: str,
        managed_serials: set[str],
    ) -> TransferValidationResult:
        username = username.strip()
        source_serial = source_serial.strip()
        destination_serial = destination_serial.strip()

        def invalid(message: str) -> TransferValidationResult:
            return TransferValidationResult(
                False, username, source_serial, destination_serial, error=message
            )

        if not username:
            return invalid("An account username is required.")
        if source_serial not in managed_serials:
            return invalid("The source device is not managed.")
        if destination_serial not in managed_serials:
            return invalid("The destination device is not managed.")
        if source_serial == destination_serial:
            return invalid("The destination must differ from the current device.")

        assignments = self._account_assignments.load_by_device()
        matches = [
            account
            for account in assignments.get(source_serial, ())
            if account.username == username
        ]
        if len(matches) != 1:
            message = (
                "The account is not assigned to the source device."
                if not matches
                else "Multiple account configurations match this account."
            )
            return invalid(message)

        if any(
            account.username == username
            for account in assignments.get(destination_serial, ())
        ):
            return invalid("The destination already contains this account.")

        account = matches[0]
        path_error = self._validate_config_path(account)
        if path_error:
            return invalid(path_error)
        return TransferValidationResult(
            True,
            username,
            source_serial,
            destination_serial,
            config_path=account.config_path,
        )

    def _validate_config_path(self, account: AssignedAccount) -> str | None:
        config_path = account.config_path
        accounts_root = self._account_assignments.accounts_directory.resolve()
        try:
            resolved_path = config_path.resolve(strict=True)
            resolved_path.relative_to(accounts_root)
        except (OSError, ValueError):
            return "The account configuration is outside the managed accounts root."
        if not resolved_path.is_file():
            return "The account configuration is not a regular file."
        return None

    def transfer(
        self,
        username: str,
        source_serial: str,
        destination_serial: str,
        managed_serials: set[str],
    ) -> TransferValidationResult:
        result = self.validate_transfer(
            username, source_serial, destination_serial, managed_serials
        )
        if not result.valid or result.config_path is None:
            raise ValueError(result.error or "Account transfer validation failed.")

        self._update_assignment(result)
        logger.info(
            "Transferred account %s: %s → %s",
            result.username,
            result.source_serial,
            result.destination_serial,
        )
        return result

    def _update_assignment(self, result: TransferValidationResult) -> None:
        """Atomically update one validated assignment without logging or refreshing."""
        if result.config_path is None:
            raise ValueError("The account configuration path is required.")
        config_path = result.config_path
        original = config_path.read_bytes()
        try:
            content = original.decode("utf-8")
            parsed = yaml.safe_load(content)
        except (UnicodeDecodeError, yaml.YAMLError) as error:
            raise ValueError(
                "The account configuration could not be validated."
            ) from error
        if not isinstance(parsed, dict):
            raise TypeError("The account configuration must contain a YAML mapping.")
        if (
            str(parsed.get("username") or config_path.parent.name).strip()
            != result.username
        ):
            raise ValueError("The account identity changed before transfer.")
        if str(parsed.get("device") or "").strip() != result.source_serial:
            raise ValueError("The account assignment changed before transfer.")

        pattern = re.compile(
            r"(?m)^(device[ \t]*:[ \t]*)([^#\r\n]*?)([ \t]*(?:#[^\r\n]*)?)\r?$"
        )
        matches = list(pattern.finditer(content))
        if len(matches) != 1 or matches[0].group(2).strip() != result.source_serial:
            raise ValueError("The existing device assignment is missing or ambiguous.")
        match = matches[0]
        updated = (
            content[: match.start(2)]
            + result.destination_serial
            + content[match.end(2) :]
        )
        if config_path.read_bytes() != original:
            raise RuntimeError("The account configuration changed during transfer.")

        self._write_atomic(config_path, updated)
        try:
            verified = config_path.read_bytes()
            if verified != updated.encode("utf-8"):
                raise RuntimeError(
                    "The account configuration did not match the expected update."
                )
            verified_config = yaml.safe_load(verified)
            if (
                not isinstance(verified_config, dict)
                or str(verified_config.get("device") or "").strip()
                != result.destination_serial
            ):
                raise RuntimeError(
                    "The updated account assignment could not be verified."
                )
        except (OSError, yaml.YAMLError, RuntimeError) as error:
            self._write_atomic(config_path, original.decode("utf-8"))
            if config_path.read_bytes() != original:
                raise RuntimeError(
                    "The original account configuration could not be restored."
                ) from error
            raise RuntimeError(
                "Account transfer verification failed; the original was restored."
            ) from error

    @staticmethod
    def _write_atomic(path: Path, content: str) -> None:
        with atomic_write(path, overwrite=True, encoding="utf-8", newline="") as output:
            output.write(content)
