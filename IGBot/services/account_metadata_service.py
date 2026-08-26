import json
from datetime import UTC, datetime
from pathlib import Path

from atomicwrites import atomic_write


class AccountMetadataService:
    """Owns IGBot-only account metadata stored outside engine configuration."""

    FILE_NAME = "account.json"
    SCHEMA_VERSION = 1

    def load(self, account_directory: Path) -> dict:
        path = account_directory / self.FILE_NAME
        try:
            metadata = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError(
                f"Could not read account metadata {path}: {error}"
            ) from error
        if not isinstance(metadata, dict):
            raise TypeError("Account metadata must contain a JSON object.")
        return metadata

    def save(
        self,
        account_directory: Path,
        username: str,
        password: str,
        device_id: str,
    ) -> dict:
        existing = self.load(account_directory)
        metadata = dict(existing)
        metadata.update(
            {
                "schema_version": self.SCHEMA_VERSION,
                "username": username,
                "password": password,
                "assigned_device_id": device_id,
                "created_at": existing.get("created_at")
                or datetime.now(UTC).isoformat(),
            }
        )
        self._write(account_directory / self.FILE_NAME, metadata)
        if self.load(account_directory) != metadata:
            raise RuntimeError("The saved account metadata could not be verified.")
        return metadata

    def update_device(self, account_directory: Path, device_id: str) -> None:
        path = account_directory / self.FILE_NAME
        original = path.read_bytes() if path.is_file() else None
        metadata = self.load(account_directory)
        if not metadata:
            return
        try:
            metadata["assigned_device_id"] = device_id
            self._write(path, metadata)
            if self.load(account_directory).get("assigned_device_id") != device_id:
                raise RuntimeError(
                    "The account metadata assignment could not be verified."
                )
        except (OSError, RuntimeError, TypeError, json.JSONDecodeError):
            self.restore(path, original)
            raise

    @staticmethod
    def restore(path: Path, original: bytes | None) -> None:
        if original is None:
            path.unlink(missing_ok=True)
            return
        with atomic_write(path, overwrite=True, mode="wb") as output:
            output.write(original)

    @staticmethod
    def _write(path: Path, metadata: dict) -> None:
        with atomic_write(path, overwrite=True, encoding="utf-8", newline="") as output:
            json.dump(metadata, output, indent=2, ensure_ascii=False)
            output.write("\n")
