"""Exclusive boundary between the IGBot runtime and legacy execution providers.

No other native runtime package may import or communicate with InstaAddict.
Concrete adapters will be introduced only when compatibility behaviour is
implemented in a later sprint.
"""

from IGBot.runtime.compatibility.contracts import (
    DMAdapter,
    FollowAdapter,
    InstaAddictAdapter,
    LikeAdapter,
    ModuleAdapter,
    UnfollowAdapter,
)
from IGBot.runtime.compatibility.models import (
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
)

__all__ = [
    "DMAdapter",
    "ExecutionRequest",
    "ExecutionResult",
    "ExecutionStatus",
    "FollowAdapter",
    "InstaAddictAdapter",
    "LikeAdapter",
    "ModuleAdapter",
    "UnfollowAdapter",
]
