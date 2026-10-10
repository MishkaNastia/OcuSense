"""One step of eye monitoring per camera frame, with no user interface.

The interface (OpenCV prototype or PySide6 app) opens the camera, calls
EyeMonitor.process() for every frame, and decides how to show the result.
Frames are analysed in memory and never stored.
"""

import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions, vision

from .blink_counter import BlinkCounter
from .calibration import GuidedCalibration
from .eye_metrics import measure_eyes
from .history import ScoreHistory

MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "face_landmarker.task"

# Events that process() can report, so the interface can react to them.
CLOSED_STEP_FINISHED = "closed_step_finished"  # eyes may open again
CALIBRATION_DONE = "calibration_done"
CALIBRATION_FAILED = "calibration_failed"


def create_landmarker(model_path=MODEL_PATH):
    options = vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(model_path)),
        running_mode=vision.RunningMode.VIDEO,
        num_faces=1,
    )
    return vision.FaceLandmarker.create_from_options(options)


@dataclass
class FrameResult:
    frame: object  # the mirrored camera frame (BGR), as it should be shown
    landmarks: object  # MediaPipe face landmarks, or None if no face
    measurement: object  # EyeMeasurement, or None if no face
    openness: tuple = None  # (left, right, both) personal eye openness, or None
    blinked: bool = False  # True if this frame completed a blink
    events: list = field(default_factory=list)


class EyeMonitor:
    def __init__(self, model_path=MODEL_PATH):
        self.counter = BlinkCounter()  # both eyes together (the main count)
        # One extra counter per eye, fed with that eye's own openness. These
        # also count one-eyed winks, which the main count ignores.
        self.eye_counters = {"left": BlinkCounter(), "right": BlinkCounter()}
        self.calibrator = GuidedCalibration()
        self.calibration = None  # PersonalCalibration once calibrated
        self.history = ScoreHistory()  # last few seconds of openness, for the graph
        self.landmarker = create_landmarker(model_path)
        self._start = time.monotonic()
        self._last_timestamp_ms = -1

    def reset_session(self):
        """Start a new session: forget blink counts and graph history, keep the calibration."""
        self.counter = BlinkCounter()
        self.eye_counters = {"left": BlinkCounter(), "right": BlinkCounter()}
        self.history.clear()

    def start_calibration(self, now):
        self.calibration = None  # forget the old one; never mix old and new
        self.history.clear()
        self.calibrator.start(now)

    def process(self, camera_frame, now):
        """Analyse one camera frame taken at time `now` (time.monotonic())."""
        # Mirror the image so it behaves like a mirror. The eye names
        # ("left"/"right") in eye_metrics depend on this.
        frame = cv2.flip(camera_frame, 1)
        height, width = frame.shape[:2]

        # MediaPipe expects RGB colours; OpenCV gives BGR.
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

        # VIDEO mode needs a timestamp that always increases.
        timestamp_ms = max(int((now - self._start) * 1000), self._last_timestamp_ms + 1)
        self._last_timestamp_ms = timestamp_ms
        detection = self.landmarker.detect_for_video(mp_image, timestamp_ms)

        landmarks = detection.face_landmarks[0] if detection.face_landmarks else None
        measurement = measure_eyes(landmarks, width, height) if landmarks else None
        reliable_ears = measurement.ears if measurement and measurement.reliable else None
        result = FrameResult(frame, landmarks, measurement)

        # --- calibration or counting ---
        calibrator = self.calibrator
        if calibrator.status == GuidedCalibration.RUNNING:
            step_before = calibrator.step.name
            calibrator.update(now, reliable_ears)
            if calibrator.step is None or calibrator.step.name != step_before:
                if step_before == "closed":
                    result.events.append(CLOSED_STEP_FINISHED)
            if calibrator.status == GuidedCalibration.DONE:
                self.calibration = calibrator.result
                result.events.append(CALIBRATION_DONE)
            elif calibrator.status == GuidedCalibration.FAILED:
                result.events.append(CALIBRATION_FAILED)
        elif self.calibration is not None and reliable_ears is not None:
            result.openness = self.calibration.openness(reliable_ears)

        # None = calibrating or paused: resets any half-finished blink.
        openness = result.openness
        result.blinked = self.counter.update(openness[2] if openness else None)
        if self.calibration is not None:
            self.history.add(now, openness, result.blinked)
        self.eye_counters["left"].update(openness[0] if openness else None)
        self.eye_counters["right"].update(openness[1] if openness else None)
        return result

    def close(self):
        self.landmarker.close()
