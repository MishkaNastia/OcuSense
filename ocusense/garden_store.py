"""Atomic local garden saves. Failed writes roll back the pending transaction."""
import copy
import json
import os
from pathlib import Path
from ocusense.core.garden import Garden
from ocusense.preferences import default_path


class GardenStore:
    def __init__(self, path=None):
        self.path = Path(path or os.environ.get('OCUSENSE_GARDEN_FILE') or default_path().with_name('garden.json'))
        self.error = ''
        self.read_only = False
        self.garden = Garden()
        try:
            self.garden = Garden.from_dict(json.loads(self.path.read_text()))
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError):
            self.error = 'The saved garden could not be read. It has been preserved; garden changes are disabled.'
            self.read_only = True

    def change(self, action):
        if self.read_only:
            return False
        before = copy.deepcopy(self.garden)
        result = action(self.garden)
        if not result:
            return result
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix('.tmp')
            temporary.write_text(json.dumps(self.garden.to_dict(), indent=2) + '\n')
            temporary.replace(self.path)
            self.error = ''
        except OSError:
            self.garden = before
            self.error = 'Could not save the garden. This change was not applied; please try again.'
            return False
        return result
