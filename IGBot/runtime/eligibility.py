"""Native runtime eligibility boundary consumed by the phone scheduler."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, time, timedelta, timezone

from IGBot.core.device import AssignedAccount
from IGBot.runtime.database import RuntimeDatabase
from IGBot.runtime.follow.daily_limits import remaining_daily_follows
from IGBot.runtime.unfollow.following_list_database import FollowingListDatabase


def _enabled(value: object) -> bool:
    return value not in (None, False, 0, "", "0")


def _has_usernames(value: object) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple)):
        return any(str(username).strip() for username in value)
    return False


def follow_provider_is_configured(configuration: Mapping[str, object]) -> bool:
    """Match the native Follow factory's provider selection and readiness rules."""

    specific_users = configuration.get("blogger")
    if _enabled(specific_users):
        return _has_usernames(specific_users)
    return any(
        _has_usernames(configuration.get(key))
        for key in ("blogger-followers", "blogger-following")
    )


def native_follow_configuration_ready(configuration: Mapping[str, object]) -> bool:
    """Report whether Follow is enabled with one complete native provider."""

    return _enabled(
        configuration.get("follow-percentage")
    ) and follow_provider_is_configured(configuration)


def native_unfollow_configuration_ready(configuration: Mapping[str, object]) -> bool:
    """Report whether one implemented native Unfollow provider is enabled."""

    method = str(configuration.get("igbot-unfollow-method") or "search")
    if method in {"all-followings", "specific-users"}:
        return bool(configuration.get("igbot-unfollow-enabled"))
    return method in {"search", "following-list-search"} and any(
        _enabled(configuration.get(key))
        for key in ("unfollow", "unfollow-non-followers")
    )


def native_account_configuration_ready(configuration: Mapping[str, object]) -> bool:
    """Report whether any implemented native module is fully configured."""

    return native_follow_configuration_ready(
        configuration
    ) or native_unfollow_configuration_ready(configuration)


def native_account_is_runnable(
    account: AssignedAccount, configuration: Mapping[str, object]
) -> bool:
    """Report whether any implemented native interaction module can run now."""

    return any(
        capacity > 0
        for capacity in native_account_execution_capacity(
            account, configuration
        ).values()
    )


def native_account_execution_capacity(
    account: AssignedAccount, configuration: Mapping[str, object]
) -> dict[str, int]:
    """Return current persisted capacity for every runnable native module.

    The scheduler treats this mapping as opaque. Future modules can expose their
    capacity here without adding module-specific scheduling logic.
    """

    capacity: dict[str, int] = {}
    if native_follow_configuration_ready(configuration):
        capacity["follow"] = remaining_daily_follows(
            account.config_path.parent,
            configuration.get("total-follows-limit"),
        )
    if native_unfollow_configuration_ready(configuration):
        current = datetime.now(timezone.utc)
        start = datetime.combine(current.date(), time.min, tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        try:
            limit = max(
                0,
                int(str(configuration.get("total-unfollows-limit")).split("-", 1)[-1]),
            )
        except (TypeError, ValueError):
            limit = 100_000
        method = str(configuration.get("igbot-unfollow-method") or "search")
        if method == "all-followings":
            with FollowingListDatabase(account.config_path.parent) as database:
                completed = database.count_unfollowed_between(
                    start.strftime("%Y-%m-%d %H:%M:%S"),
                    end.strftime("%Y-%m-%d %H:%M:%S"),
                )
        elif method == "specific-users":
            with RuntimeDatabase(account.config_path.parent) as database:
                completed = (
                    database.specific_unfollow.count_successful_unfollows_between(
                        start.isoformat(), end.isoformat()
                    )
                )
        else:
            with RuntimeDatabase(account.config_path.parent) as database:
                completed = database.follow.count_unfollowed_between(
                    start.isoformat(), end.isoformat()
                )
        capacity["unfollow"] = max(0, limit - completed)
    return capacity
