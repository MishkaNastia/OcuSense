"""Saves the time log (ocusense/core/timelog.py) on this Mac:

    ~/Library/Application Support/OcuSense/timelog.json

Every change is written straight away (atomically), so a running timer survives
quitting OcuSense: it keeps counting and shows again at the next launch.
OCUSENSE_TIMELOG_FILE overrides the file; with only OCUSENSE_PREFERENCES_FILE set
(tests) it sits next to that file. A damaged file is never overwritten: it is kept
as it is and changes are switched off until it is fixed or moved away.
"""

import copy
import json
import os
from pathlib import Path

from ocusense.core.timelog import TimeLog
from ocusense.preferences import default_path as preferences_path


def default_path() -> Path:
    override = os.environ.get("OCUSENSE_TIMELOG_FILE")
    return Path(override) if override else preferences_path().with_name("timelog.json")


class TimeLogStore:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else default_path()
        self.log = TimeLog()
        self.error = ""
        self.read_only = False
        try:
            self.log = TimeLog.from_dict(json.loads(self.path.read_text()))
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError):
            self.read_only = True
            self.error = (f"The saved time log ({self.path.name}) could not be read. It was left untouched; "
                          "changes are switched off until it is fixed or moved away.")

    def change(self, action):
        """Run action(log); keep and save the result, or roll back if saving fails. Returns action's result."""
        if self.read_only:
            return None
        before = copy.deepcopy(self.log)
        result = action(self.log)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(self.log.to_dict(), indent=2) + "\n")
            temporary.replace(self.path)
            self.error = ""
        except OSError as error:
            self.log = before
            self.error = f"Couldn’t save the time log ({error.strerror or error}). The change was not kept."
            return None
        return result
