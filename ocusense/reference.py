"""The saved reference for blink timing: the first 10 minutes of one session.

Every live session is compared with it (core/baseline_drift.py). There is one
reference at a time, kept as reference.json next to the recordings folder:

    ~/Library/Application Support/OcuSense/reference.json

It holds the reference's intervals as (onset_a, onset_b) pairs in seconds since
the reference period started, so it can be refitted or plotted later, plus the fit
(maximum-likelihood log-normal), when and from what it was made, and the
calibration in use. Numbers only — no images.

If there is no reference, the first 10 minutes of the next session become it, as
long as they hold at least MIN_REFERENCE_INTERVALS intervals. It is kept when you
recalibrate; Settings › Data & privacy can discard it so that the next session
makes a new one.
"""

import json
import math
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from ocusense.core.baseline_drift import BASELINE_SECONDS, fit_lognormal
from ocusense.recording import default_directory

MIN_REFERENCE_INTERVALS = 50
FILE_VERSION = 1


class ReferenceFileError(Exception):
    """reference.json exists but can't be used; the message says why."""


def default_path() -> Path:
    """reference.json beside the recordings folder.

    OCUSENSE_REFERENCE_FILE overrides it. When only OCUSENSE_RECORDINGS_DIR is set
    (tests), the file goes inside that folder, so tests never touch the real one.
    """
    override = os.environ.get("OCUSENSE_REFERENCE_FILE")
    if override:
        return Path(override)
    if os.environ.get("OCUSENSE_RECORDINGS_DIR"):
        return default_directory() / "reference.json"
    return default_directory().parent / "reference.json"


@dataclass(frozen=True)
class Reference:
    pairs: tuple  # ((onset_a, onset_b), …) seconds since `started_at`, both onsets in the first `seconds`
    mu: float
    sigma: float  # MLE, ddof = 0
    n: int
    started_at: str  # ISO time the reference period started
    created_at: str  # ISO time it was saved
    source: str  # "live session" or the recording's file names
    calibration: dict | None  # calibration and thresholds in use, as saved with recordings
    seconds: float = BASELINE_SECONDS

    @property
    def intervals(self) -> list[float]:
        return [b - a for a, b in self.pairs]

    @property
    def median(self) -> float:
        """Median time between blinks of the fitted log-normal, exp(mu), in seconds."""
        return math.exp(self.mu)

    def label(self) -> str:
        started = datetime.fromisoformat(self.started_at)
        return f"{started:%-d %b %Y, %H:%M}"


def from_pairs(pairs, started_at: datetime, source: str, calibration: dict | None,
               seconds: float = BASELINE_SECONDS) -> Reference | None:
    """A reference from the reference period's intervals; None if there are too few to rely on."""
    pairs = tuple((round(a, 4), round(b, 4)) for a, b in pairs)
    fit = fit_lognormal([b - a for a, b in pairs])
    if fit is None or fit[2] < MIN_REFERENCE_INTERVALS or fit[1] == 0:
        return None
    mu, sigma, n = fit
    return Reference(pairs, mu, sigma, n, started_at.isoformat(timespec="seconds"),
                     datetime.now().isoformat(timespec="seconds"), source, calibration, seconds)


def load(path: Path | None = None) -> Reference | None:
    """The saved reference, or None if there is none. Raises ReferenceFileError if it can't be read."""
    path = path or default_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        values = {name: data[name] for name in Reference.__dataclass_fields__ if name in data}
        values["pairs"] = tuple((float(a), float(b)) for a, b in values["pairs"])
        return Reference(**values)
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ReferenceFileError(f"{path.name} can’t be read: {error}") from error


def save(reference: Reference, path: Path | None = None) -> Path:
    """Write the reference (replacing any previous one) via a temporary file, so it is never half-written."""
    path = path or default_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"version": FILE_VERSION, **asdict(reference),
            "definition": "intervals = onset-to-onset seconds between consecutive blinks in one valid segment, "
                          "both onsets in the first `seconds` of the session; log-normal MLE on ln(interval), "
                          "sigma with ddof = 0"}
    data["pairs"] = [list(p) for p in reference.pairs]
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(data, indent=1))
    temporary.replace(path)
    return path


def discard(path: Path | None = None) -> None:
    """Remove the saved reference, so the next session makes a new one."""
    (path or default_path()).unlink(missing_ok=True)
