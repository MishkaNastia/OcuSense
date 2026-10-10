"""macOS notifications (Notification Centre), shown even while OcuSense is in the background.

Uses the system's `osascript` ("display notification"), so no extra packages are
needed. The text is passed as arguments, never pasted into the script. Elsewhere,
or with OCUSENSE_NO_NOTIFICATIONS set (tests), nothing is shown.
"""

import os
import subprocess
import sys

SCRIPT = ("on run argv", "display notification (item 1 of argv) with title (item 2 of argv)", "end run")


def post(message: str, title: str = "OcuSense") -> bool:
    """Show a notification without waiting for it. Returns False if it couldn't be shown."""
    if sys.platform != "darwin" or os.environ.get("OCUSENSE_NO_NOTIFICATIONS"):
        return False
    command = ["osascript"]
    for line in SCRIPT:
        command += ["-e", line]
    try:
        subprocess.Popen(command + [message, title], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        return False
    return True
