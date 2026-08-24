from dataclasses import dataclass, field
from typing import List


@dataclass
class Account:
    username: str
    device_id: str
    app_id: str

    enabled_sources: List[str] = field(default_factory=list)
    enabled_tools: List[str] = field(default_factory=list)

    is_running: bool = False

    follows_done: int = 0
    likes_done: int = 0
    comments_done: int = 0
    stories_done: int = 0
    dms_done: int = 0
