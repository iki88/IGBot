#!/usr/bin/env python3
"""
Alternating GramAddict runner for two accounts.
Runs one account's session, then switches to the other.
Working hours and sleep intervals are managed here instead of in individual configs.

Usage:
    python run_both.py
"""

import random
import subprocess
import sys
import time
from datetime import datetime, timedelta

# ─── Configuration ───────────────────────────────────────────────────────────

ACCOUNTS = [
    "accounts/blanklight_/config.yml",
    "accounts/stickerlight/config.yml",
]

# Working hours: list of (start_hour, start_min, end_hour, end_min)
# Leave empty to run 24/7 with no time restrictions
WORKING_HOURS = []

# Minutes to sleep between switching accounts (randomized within range)
SLEEP_BETWEEN_ACCOUNTS_MIN = 10
SLEEP_BETWEEN_ACCOUNTS_MAX = 25

# Minutes to sleep after a full cycle (both accounts done) before restarting
SLEEP_BETWEEN_CYCLES_MIN = 30
SLEEP_BETWEEN_CYCLES_MAX = 60

# Maximum number of full cycles (-1 for infinite)
MAX_CYCLES = -1

# ─── Helpers ─────────────────────────────────────────────────────────────────

def log(msg):
    timestamp = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    print(f"[{timestamp}] [run_both] {msg}")


def is_inside_working_hours():
    """Check if current time is within any of the defined working hour windows."""
    if not WORKING_HOURS:
        return True
    now = datetime.now()
    for start_h, start_m, end_h, end_m in WORKING_HOURS:
        start = now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
        end = now.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
        if start <= now <= end:
            return True
    return False


def seconds_until_next_working_window():
    """Calculate seconds until the next working hour window opens."""
    now = datetime.now()
    candidates = []
    for start_h, start_m, end_h, end_m in WORKING_HOURS:
        # Today's window
        start_today = now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
        end_today = now.replace(hour=end_h, minute=end_m, second=0, microsecond=0)

        if now < start_today:
            candidates.append(start_today)
        elif now <= end_today:
            return 0  # Currently inside this window

        # Tomorrow's window
        start_tomorrow = start_today + timedelta(days=1)
        candidates.append(start_tomorrow)

    if not candidates:
        return 3600  # Fallback: check again in 1 hour

    next_start = min(candidates)
    return max(0, int((next_start - now).total_seconds()))


def wait_for_working_hours():
    """Block until we're inside working hours."""
    if is_inside_working_hours():
        return

    wait_seconds = seconds_until_next_working_window()
    if wait_seconds > 0:
        resume_time = datetime.now() + timedelta(seconds=wait_seconds)
        log(f"Outside working hours. Sleeping until {resume_time.strftime('%H:%M:%S (%Y/%m/%d)')} ({wait_seconds // 60} minutes).")
        time.sleep(wait_seconds)


def run_account(config_path):
    """Run a single GramAddict session for the given config. Returns exit code."""
    account_name = config_path.split("/")[1]
    log(f"{'=' * 50}")
    log(f"Starting session: {account_name}")
    log(f"Config: {config_path}")
    log(f"{'=' * 50}")

    result = subprocess.run(
        [sys.executable, "run.py", "--config", config_path],
        cwd="C:\\Users\\Admin\\Documents\\gramaddict-joeahkim",
    )

    if result.returncode == 0:
        log(f"Session for {account_name} completed successfully.")
    else:
        log(f"Session for {account_name} exited with code {result.returncode}.")

    return result.returncode


def sleep_random(min_minutes, max_minutes, reason=""):
    """Sleep for a random duration between min and max minutes."""
    minutes = random.randint(min_minutes, max_minutes)
    wake_time = datetime.now() + timedelta(minutes=minutes)
    log(f"Sleeping {minutes} minutes{f' ({reason})' if reason else ''}. Will resume at {wake_time.strftime('%H:%M:%S')}.")
    time.sleep(minutes * 60)


# ─── Main Loop ───────────────────────────────────────────────────────────────

def main():
    cycle = 0
    log("Starting alternating runner for accounts: " + ", ".join(
        cfg.split("/")[1] for cfg in ACCOUNTS
    ))
    log(f"Working hours: {WORKING_HOURS}")

    try:
        while True:
            cycle += 1
            if MAX_CYCLES > 0 and cycle > MAX_CYCLES:
                log(f"Reached max cycles ({MAX_CYCLES}). Exiting.")
                break

            log(f"{'#' * 50}")
            log(f"CYCLE {cycle}")
            log(f"{'#' * 50}")

            wait_for_working_hours()

            for i, config in enumerate(ACCOUNTS):
                # Re-check working hours before each account
                if not is_inside_working_hours():
                    log("Outside working hours. Pausing until next window.")
                    wait_for_working_hours()

                run_account(config)

                # Sleep between accounts (not after the last one in the cycle)
                if i < len(ACCOUNTS) - 1:
                    sleep_random(
                        SLEEP_BETWEEN_ACCOUNTS_MIN,
                        SLEEP_BETWEEN_ACCOUNTS_MAX,
                        reason="switching accounts",
                    )

            # Sleep between cycles
            sleep_random(
                SLEEP_BETWEEN_CYCLES_MIN,
                SLEEP_BETWEEN_CYCLES_MAX,
                reason="between cycles",
            )

    except KeyboardInterrupt:
        log("CTRL-C detected. Stopping alternating runner.")
        sys.exit(0)


if __name__ == "__main__":
    main()
