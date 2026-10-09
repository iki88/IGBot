"""Native runtime eligibility boundary consumed by the phone scheduler."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from IGBot.core.device import AssignedAccount
from IGBot.runtime.database import DailyLimitResolver
from IGBot.services.message_storage_service import MessageStorageService


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

    configured_methods = configuration.get("igbot-follow-methods")
    methods = (
        {str(method) for method in configured_methods}
        if isinstance(configured_methods, (list, tuple))
        else None
    )
    specific_users = configuration.get("blogger")
    if methods is not None and "blogger" not in methods:
        specific_users = None
    if _enabled(specific_users):
        return _has_usernames(specific_users)
    source_keys = (
        ("igbot-follow-sources-followers", "blogger-followers"),
        ("igbot-follow-sources-following", "blogger-following"),
    )
    return any(
        (methods is None or method in methods)
        and _has_usernames(configuration.get(module_key))
        for module_key, method in source_keys
    )


def native_follow_configuration_ready(configuration: Mapping[str, object]) -> bool:
    """Report whether Follow is enabled with one complete native provider."""

    return _enabled(
        configuration.get("follow-percentage")
    ) and follow_provider_is_configured(configuration)


def native_unfollow_configuration_ready(configuration: Mapping[str, object]) -> bool:
    """Report whether one implemented native Unfollow provider is enabled."""

    if not bool(configuration.get("igbot-unfollow-enabled")):
        return False
    method = str(configuration.get("igbot-unfollow-method") or "search")
    return method in {
        "search",
        "following-list-search",
        "specific-users",
        "all-followings",
    }


def native_like_configuration_ready(configuration: Mapping[str, object]) -> bool:
    """Report whether one implemented native Like provider can run."""

    followers = configuration.get("igbot-like-sources-followers")
    configured_methods = configuration.get("igbot-like-methods")
    methods = (
        {str(method) for method in configured_methods}
        if isinstance(configured_methods, (list, tuple))
        else None
    )
    specific_ready = (methods is None or "blogger" in methods) and _has_usernames(
        configuration.get("blogger")
    )
    followers_ready = (
        methods is None or "blogger-followers" in methods
    ) and _has_usernames(followers)
    return _enabled(configuration.get("likes-percentage")) and (
        specific_ready or followers_ready
    )


def native_dm_configuration_ready(
    configuration: Mapping[str, object], account_directory: str | Path | None = None
) -> bool:
    """Report whether the native DM module is enabled."""

    if not _enabled(configuration.get("pm-percentage")):
        return False
    if account_directory is None:
        return True
    storage = MessageStorageService(account_directory)
    return bool(storage.load(storage.WELCOME_DM).strip())


def native_account_configuration_ready(configuration: Mapping[str, object]) -> bool:
    """Report whether any implemented native module is fully configured."""

    return (
        native_follow_configuration_ready(configuration)
        or native_unfollow_configuration_ready(configuration)
        or native_like_configuration_ready(configuration)
        or native_dm_configuration_ready(configuration)
    )


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
    resolver = DailyLimitResolver(account.config_path.parent)
    if native_follow_configuration_ready(configuration):
        capacity["follow"] = resolver.capacity(
            "follow", configuration.get("total-follows-limit")
        ).remaining
    if native_unfollow_configuration_ready(configuration):
        capacity["unfollow"] = resolver.capacity(
            "unfollow", configuration.get("total-unfollows-limit")
        ).remaining
    if native_like_configuration_ready(configuration):
        capacity["like"] = resolver.capacity(
            "like", configuration.get("total-likes-limit")
        ).remaining
    if native_dm_configuration_ready(configuration, account.config_path.parent):
        capacity["dm"] = resolver.capacity(
            "dm", configuration.get("total-pm-limit")
        ).remaining
    return capacity
