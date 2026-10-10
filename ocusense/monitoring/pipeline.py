"""One step of eye monitoring per camera frame, with no user interface.

The interface (OpenCV prototype or PySide6 app) opens the camera, calls
EyeMonitor.process() for every frame, and decides how to show the result.
Frames are analysed in memory and never stored.
"""

import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision

from ocusense.config import MEASUREMENT_VERSION, MODEL_PATH
from ocusense.core.blink_counter import BlinkCounter
from ocusense.core.calibration import GuidedCalibration
from ocusense.core.eye_metrics import measure_eyes
from ocusense.core.history import ScoreHistory
from ocusense.core.models import CalibrationInfo, FrameObservation


# Events that process() can report, so the interface can react to them.
CLOSED_STEP_FINISHED = "closed_step_finished"  # eyes may open again
CALIBRATION_DONE = "calibration_done"
CALIBRATION_FAILED = "calibration_failed"


def create_landmarker(model_path: Path = MODEL_PATH):
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
    openness: tuple = None  # (left, right, both) clipped personal openness used by the detector, or None
    blinked: bool = False  # True if this frame completed a blink
    events: list = field(default_factory=list)
    observation: FrameObservation = None  # timestamped input for the measurements
    closeness: float = None  # face size now ÷ at calibration (distance reminder), or None


class EyeMonitor:
    def __init__(self, model_path: Path = MODEL_PATH):
        self.counter = BlinkCounter()  # both eyes together (the main count)
        # One extra counter per eye, fed with that eye's own openness. These
        # also count one-eyed winks, which the main count ignores.
        self.eye_counters = {"left": BlinkCounter(), "right": BlinkCounter()}
        self.calibrator = GuidedCalibration()
        self.calibration = None  # PersonalCalibration once calibrated
        self.calibration_info: CalibrationInfo | None = None  # what produced the current calibration
        self.history = ScoreHistory()  # last few seconds of openness, for the graph
        self.landmarker = create_landmarker(model_path)
        self._start = time.monotonic()
        self._last_timestamp_ms = -1

    def reset_session(self) -> None:
        """Start a new session: forget blink counts and graph history, keep the calibration."""
        self.counter = BlinkCounter()
        self.eye_counters = {"left": BlinkCounter(), "right": BlinkCounter()}
        self.history.clear()

    def interrupt(self) -> None:
        """Monitoring paused: treat it like lost tracking, so no blink can span the pause.

        Uses the detector's existing rule (None = forget a half-finished blink).
        Call only while no frame is being processed (the camera worker is stopped).
        """
        self.counter.update(None)
        for counter in self.eye_counters.values():
            counter.update(None)

    def start_calibration(self, now: float) -> None:
        self.calibration = None  # forget the old one; never mix old and new
        self.calibration_info = None
        self.history.clear()
        self.calibrator.start(now)

    def process(self, camera_frame: np.ndarray, now: float) -> FrameResult:
        """Analyse one BGR camera frame taken at `now` (time.monotonic(), seconds)."""
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
        was_calibrating = calibrator.status == GuidedCalibration.RUNNING
        if was_calibrating:
            step_before = calibrator.step.name
            calibrator.update(now, reliable_ears, measurement.face_scale if reliable_ears else None)
            if calibrator.step is None or calibrator.step.name != step_before:
                if step_before == "closed":
                    result.events.append(CLOSED_STEP_FINISHED)
            if calibrator.status == GuidedCalibration.DONE:
                self.calibration = calibrator.result
                self.calibration_info = CalibrationInfo(
                    calibrated_at=datetime.now(),
                    left_open_ear=self.calibration.left.open_ear, left_closed_ear=self.calibration.left.closed_ear,
                    right_open_ear=self.calibration.right.open_ear, right_closed_ear=self.calibration.right.closed_ear,
                    close_below=self.counter.close_below, reopen_above=self.counter.reopen_above,
                    measurement_version=MEASUREMENT_VERSION,
                    reference_face_scale=self.calibration.face_scale,
                )
                result.events.append(CALIBRATION_DONE)
            elif calibrator.status == GuidedCalibration.FAILED:
                result.events.append(CALIBRATION_FAILED)
        raw = None
        if not was_calibrating and self.calibration is not None and reliable_ears is not None:
            result.openness = self.calibration.openness(reliable_ears)
            raw = self.calibration.raw_openness(reliable_ears)
            reference = getattr(self.calibration, "face_scale", None)
            if reference and measurement.face_scale:
                result.closeness = measurement.face_scale / reference

        # None = calibrating or paused: resets any half-finished blink.
        # The detector is unchanged; we only read its state before and after.
        openness = result.openness
        state_before = self.counter.state
        result.blinked = self.counter.update(openness[2] if openness else None)
        state_after = self.counter.state
        ears = measurement.ears if measurement else {}
        result.observation = FrameObservation(
            t=now,
            valid=openness is not None,
            left_raw=raw[0] if raw else None,
            right_raw=raw[1] if raw else None,
            left_ear=ears.get("left"),
            right_ear=ears.get("right"),
            detector_closed=state_after == BlinkCounter.CLOSED,
            closing_started=state_before == BlinkCounter.OPEN and state_after == BlinkCounter.CLOSED,
            blink_completed=result.blinked,
        )
        if self.calibration is not None:
            self.history.add(now, openness, result.blinked)
        self.eye_counters["left"].update(openness[0] if openness else None)
        self.eye_counters["right"].update(openness[1] if openness else None)
        return result

    def close(self) -> None:
        self.landmarker.close()
