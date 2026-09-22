"""Account-local username-list storage for Specific Users workflows."""

from pathlib import Path


class SpecificListsService:
    FILENAMES = (
        "followspecific.txt",
        "likespecific.txt",
        "dmspecific.txt",
        "commentspecific.txt",
        "unfollowspecific.txt",
    )

    def __init__(self, account_directory: str | Path) -> None:
        self.directory = Path(account_directory) / "Lists"

    def initialize(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        for filename in self.FILENAMES:
            (self.directory / filename).touch(exist_ok=True)

    def load(self, filename: str) -> list[str]:
        self._validate(filename)
        self.initialize()
        return [
            line.strip()
            for line in (self.directory / filename)
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]

    def save(self, filename: str, usernames: list[str]) -> None:
        self._validate(filename)
        self.initialize()
        content = "".join(
            f"{username.strip()}\n" for username in usernames if username.strip()
        )
        (self.directory / filename).write_text(content, encoding="utf-8")

    def _validate(self, filename: str) -> None:
        if filename not in self.FILENAMES:
            raise ValueError(f"Unsupported Specific Users list: {filename}")
