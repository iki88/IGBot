"""Specific-account recipient and persistence adapters for native DM."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.database import RuntimeDatabase
from IGBot.runtime.database.timestamps import utc_timestamp
from IGBot.runtime.dm.module import DMRecipient
from IGBot.runtime.ignore import IgnoreService


class SpecificDMSynchronizer:
    def synchronize(
        self,
        account_directory: str | Path,
        ignore_service: IgnoreService | None = None,
    ) -> tuple[str, ...]:
        directory = Path(account_directory)
        path = directory / "Lists" / "dmspecific.txt"
        usernames = (
            IgnoreService.normalize_many(path.read_text(encoding="utf-8").splitlines())
            if path.is_file()
            else ()
        )
        if ignore_service is not None:
            usernames = tuple(
                username
                for username in usernames
                if not ignore_service.is_ignored(username)
            )
        with RuntimeDatabase(directory) as database:
            database.specific_dm.synchronize_dm_usernames(tuple(usernames))
        return tuple(usernames)


class SpecificDMRecipients:
    def pending(self, context: RuntimeContext) -> tuple[DMRecipient, ...]:
        with RuntimeDatabase(context.session.account_directory) as database:
            rows = database.specific_dm.pending_dm_users()
        return tuple(
            DMRecipient(user_id, username, "specific_users")
            for user_id, username in rows
        )


class SpecificDMPersistence:
    def persist(
        self,
        context: RuntimeContext,
        recipient: DMRecipient,
        status: str,
        message: str,
    ) -> None:
        sent_at = (
            utc_timestamp(datetime.now(timezone.utc)) if status == "SUCCESS" else None
        )
        with RuntimeDatabase(context.session.account_directory) as database:
            database.specific_dm.mark_specific_dm_result(
                recipient.username, status=status, sent_at=sent_at
            )
        context.logger.info(
            "[DM] Database updated", username=recipient.username, status=status
        )
