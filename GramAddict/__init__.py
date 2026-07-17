"""InstaAddict - Human-like Instagram bot powered by UIAutomator2"""

__version__ = "3.2.12"
__tested_ig_version__ = "438.0.0.28.88"

from GramAddict.core.bot_flow import start_bot


def run(**kwargs):
    start_bot(**kwargs)
