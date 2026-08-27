from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AccountTemplate:
    name: str
    directory: Path
