from IGBot.core.account import Account


class SessionEngine:
    def __init__(self, account: Account):
        self.account = account

    def start(self):
        if self.account.is_running:
            print(f"{self.account.username} is already running.")
            return

        self.account.is_running = True
        print(f"Starting session for {self.account.username}")

    def stop(self):
        if not self.account.is_running:
            print(f"{self.account.username} is already stopped.")
            return

        self.account.is_running = False
        print(f"Stopping session for {self.account.username}")

    def status(self):
        return {
            "username": self.account.username,
            "running": self.account.is_running,
            "follows": self.account.follows_done,
            "likes": self.account.likes_done,
            "comments": self.account.comments_done,
            "stories": self.account.stories_done,
            "dms": self.account.dms_done,
        }
