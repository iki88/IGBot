"""Platform-provider boundary for runtime network observations."""

from IGBot.runtime.network.android import AndroidNetworkProvider
from IGBot.runtime.network.contracts import NetworkProvider
from IGBot.runtime.network.models import NetworkCheckResult

__all__ = [
    "AndroidNetworkProvider",
    "NetworkCheckResult",
    "NetworkProvider",
]
