"""Documented application defaults.

These are the same for every user. Each person's own calibration (their open
and closed EAR references) is measured at runtime and is NOT stored here.

Units: times are in seconds, openness values are 0–1 ("personal eye openness"),
sizes are in pixels. Conversions for display (e.g. seconds → milliseconds)
happen only in the interface.
"""

import sys
from pathlib import Path

# --- Blink rule (personal eye openness, 0 = as closed as in calibration, 1 = as open) ---
CLOSE_BELOW = 0.35  # eyes count as closed below this...
REOPEN_ABOVE = 0.65  # ...and as open again only above this (two values stop wobble double-counting)

# --- Calibration acceptance (see core/calibration.py; step timings live with the steps there) ---
MIN_SAMPLES = 15  # reliable frames needed per calibration phase
MIN_RELATIVE_SEPARATION = 0.25  # closed reference must be at least 25% below the open one
MAX_SPREAD_FRACTION = 0.25  # allowed wobble within a phase, relative to the open–closed gap
MIN_CALIBRATION_BLINKS = 3  # blinks that must be detected in the final calibration step

# --- Tracking quality (measurement pauses when these fail) ---
MIN_EYE_WIDTH_PX = 15  # smaller: face too far away / too small to measure
MIN_EYE_WIDTH_RATIO = 0.6  # one eye much narrower than the other: head turned

# --- Live graph and session recording ---
GRAPH_SECONDS = 10.0  # history shown in the live eye-openness graph
# ENGINEERING CHOICE: two valid frames further apart than this are treated as a
# gap (missing observation), not as observed time. At ~30 frames/s, normal frames
# are ~0.033 s apart; 0.5 s allows brief hiccups but never bridges real dropouts.
MAX_FRAME_GAP = 0.5
UNTRACKED_MIN = 2.0  # seconds without tracking before it is drawn as a gap on the timeline
MIN_TRACKED_PER_MINUTE = 20.0  # seconds of valid observation needed to show a per-minute value
MIN_SESSION_SECONDS = 10.0  # shorter sessions are not kept for Statistics

# --- Rolling "last 60 seconds" measurements ---
ROLLING_WINDOW_SECONDS = 60.0
# ENGINEERING CHOICE (MVP): blink rate and time classified as closed are shown only
# after this much VALID observation inside the window; before that: "Collecting data".
# Not a clinical standard — chosen so a few blinks don't produce a misleading rate.
MIN_VALID_SECONDS_FOR_RATE = 30.0
PROCESSING_RATE_WINDOW = 5.0  # seconds used to measure the actual frames-per-second

# Changes whenever a measurement definition changes, so later analysis can tell
# sessions apart. v2: closure duration and closed time use the detector's own
# closing/reopening transitions (v1 used time below the closing threshold).
MEASUREMENT_VERSION = "ear-personal-v2"

# --- Raw EAR recording (ocusense/recording.py) ---
RECORDING_CHUNK_SECONDS = 600.0  # a new CSV file every 10 minutes (and on pause, stop and quit)

# --- Camera ---
CAMERA_INDEX = 0  # 0 = the built-in webcam
PREVIEW_WIDTH = 480  # pixels; width of the preview image sent to the interface

# --- Files ---
MODEL_RELATIVE_PATH = Path("models") / "face_landmarker.task"


def resource_root() -> Path:
    """The project folder during development, or the bundled resources inside OcuSense.app."""
    bundle = getattr(sys, "_MEIPASS", None)  # set by PyInstaller in the packaged app
    return Path(bundle) if bundle else Path(__file__).resolve().parent.parent


def resource_path(relative: Path | str) -> Path:
    return resource_root() / relative


MODEL_PATH = resource_path(MODEL_RELATIVE_PATH)
