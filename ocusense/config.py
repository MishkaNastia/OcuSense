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

# --- Distance reminder (ocusense/core/proximity.py) ---
# The face looks bigger the closer it is (apparent size ∝ 1 / distance). "Closeness" is the
# distance between the eye centres now ÷ the same distance during calibration, where the
# person sits about an arm's length away. 1.6 ≈ at 60 % of the calibration distance.
PROXIMITY_WARN_RATIO = 1.6  # remind when this much closer than at calibration…
PROXIMITY_SUSTAIN_SECONDS = 3.0  # …for this long (a quick lean forward doesn't count)
PROXIMITY_CLEAR_RATIO = 1.3  # back below this = moved back (two levels stop on/off flicker)
PROXIMITY_COOLDOWN_SECONDS = 300.0  # default: at most one reminder every 5 minutes…
# …adjustable in Settings › Reminders to one of these (seconds), from 5 s to 10 minutes
PROXIMITY_COOLDOWN_CHOICES = (5, 10, 15, 30, 60, 120, 180, 300, 600)

# --- Posture (ocusense/core/posture.py) ---
# Distance in cm uses the iris as a ruler: the visible iris is about the same width in all
# adults, so distance ≈ focal length (px) × iris width (mm) ÷ iris width in the picture (px).
IRIS_DIAMETER_MM = 11.7  # average adult iris diameter
# ENGINEERING CHOICE: the webcam's focal length in pixels, as a multiple of the frame width.
# 1.0 ≈ a 53° horizontal field of view, typical for laptop webcams (a 60° camera would be 0.87).
# Not measured per camera, so the cm values are approximate; tune this if they are off.
FOCAL_LENGTH_PER_FRAME_WIDTH = 1.0
# The posture baseline: the first minute of every study session (or after "Recalibrate posture"),
# working normally in the posture you want to keep. Fresh each session, because the laptop, chair
# or screen may have moved since the last one; long enough to show how you really sit.
POSTURE_CALIBRATION_SECONDS = 60.0
POSTURE_MIN_SAMPLES = 300  # frames with everything measured needed in that minute (~10 s at 30 frames/s)
POSTURE_MAX_PITCH_SPREAD = 5.0  # degrees (robust spread); more = the posture kept changing, not one baseline
POSTURE_SUSTAIN_SECONDS = 20.0  # a limit must be exceeded this long, without a real break, to count…
POSTURE_GRACE_SECONDS = 3.0  # …where back inside the limit (or no face) for up to this long isn't a break:
#                              the camera's frame-to-frame wobble near a limit mustn't restart the count
POSTURE_PITCH_DROP_DEGREES = 12.0  # head dropped: chin this much lower than at calibration
POSTURE_ROLL_DEGREES = 10.0  # head tilted sideways this much from calibration, either way
POSTURE_MIN_DISTANCE_CM = 50.0  # closer than this to the screen…
POSTURE_CLOSER_FRACTION = 0.20  # …or this much closer than at calibration (0.20 = 20 %)
POSTURE_CENTRE_DROP = 0.05  # slumped: face centre this much lower in the picture (fraction of the frame height)…
POSTURE_SLUMP_GROWTH = 0.05  # …AND the face this much bigger (sliding down almost always brings the head forward;
#                              lower but not bigger could be a tilted screen). With the lid angle sensor the tilt is
#                              corrected, so lower alone is enough.

POSTURE_REMINDER_GAP_SECONDS = 600.0  # a message when posture turns poor: one per poor stretch, at most every 10 min

# --- Screen tilt (ocusense/lid_sensor.py; built-in camera of MacBooks with a lid angle sensor) ---
# The camera sits in the lid: tilting the screen moves the face up or down in the picture and changes
# the measured head angle. Small tilts are corrected from the lid angle; a clear one recalibrates.
LID_RECALIBRATE_DEGREES = 5.0  # the screen moved at least this much since the posture baseline…
LID_SETTLE_SECONDS = 2.0  # …and then stayed within ±1° this long: "you tilted your screen, recalibrating now"
LID_READ_INTERVAL = 0.5  # seconds between lid angle readings

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
