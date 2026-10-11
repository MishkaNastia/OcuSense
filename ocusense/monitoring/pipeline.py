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
from ocusense.core.models import CalibrationInfo, FrameObservation, PostureReading, PostureStatus
from ocusense.core.posture import PostureCalibration, PostureMonitor, TiltWatcher, read_posture


# Events that process() can report, so the interface can react to them.
CLOSED_STEP_FINISHED = "closed_step_finished"  # eyes may open again
CALIBRATION_DONE = "calibration_done"
CALIBRATION_FAILED = "calibration_failed"
POSTURE_CALIBRATION_DONE = "posture_calibration_done"
POSTURE_CALIBRATION_FAILED = "posture_calibration_failed"
SCREEN_TILTED = "screen_tilted"  # the screen was clearly tilted: posture waits for "Recalibrate now"


def create_landmarker(model_path: Path = MODEL_PATH):
    options = vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(model_path)),
        running_mode=vision.RunningMode.VIDEO,
        num_faces=1,
        output_facial_transformation_matrixes=True,  # head angle for posture (doesn't change the landmarks)
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
    posture: PostureReading = None  # head angle, distance and face position on this frame, or None
    posture_status: PostureStatus = None  # compared with the posture baseline, or None before that


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
        self.posture_enabled = False  # Settings › Monitoring › Posture monitoring
        self.posture_calibrator = PostureCalibration()  # separate from the eye calibration
        self.posture_monitor: PostureMonitor | None = None  # once posture is calibrated
        self.tilt = TiltWatcher()  # screen tilt since the posture baseline (MacBook lid sensor)
        self.posture_needs_recalibration = False  # tilted since the baseline: not judged until recalibrated
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
        if self.posture_monitor is not None:
            self.posture_monitor.reset()

    def set_posture_enabled(self, enabled: bool, now: float) -> None:
        """Turn posture monitoring on (a new baseline starts if the eyes are calibrated) or off (all forgotten)."""
        if enabled == self.posture_enabled:
            return
        self.posture_enabled = enabled
        self.posture_needs_recalibration = False
        self.posture_calibrator = PostureCalibration()
        self.posture_monitor = None
        self.tilt.set_reference(None)
        if enabled and self.calibration is not None:
            self.start_posture_calibration(now)

    def start_posture_calibration(self, now: float) -> None:
        """Record a new posture baseline; the eye calibration and blink counting carry on unchanged."""
        self.posture_calibrator.start(now)
        self.posture_needs_recalibration = False
        self.tilt.set_reference(None)  # taken from the next lid reading

    def _info(self, calibration, calibrated_at: datetime) -> CalibrationInfo:
        return CalibrationInfo(
            calibrated_at=calibrated_at,
            left_open_ear=calibration.left.open_ear, left_closed_ear=calibration.left.closed_ear,
            right_open_ear=calibration.right.open_ear, right_closed_ear=calibration.right.closed_ear,
            close_below=self.counter.close_below, reopen_above=self.counter.reopen_above,
            measurement_version=MEASUREMENT_VERSION,
            reference_face_scale=calibration.face_scale,
        )

    def use_calibration(self, calibration, calibrated_at: datetime) -> None:
        """Use a saved calibration (made earlier, loaded from disk). Call while no frame is being processed."""
        self.calibration = calibration
        self.calibration_info = self._info(calibration, calibrated_at)
        self.history.clear()

    def start_calibration(self, now: float) -> None:
        self.calibration = None  # forget the old one; never mix old and new
        self.calibration_info = None
        self.history.clear()
        self.calibrator.start(now)

    def process(self, camera_frame: np.ndarray, now: float, lid_angle: float | None = None) -> FrameResult:
        """Analyse one BGR camera frame taken at `now` (time.monotonic(), seconds).

        lid_angle: the MacBook screen angle in degrees (lid_sensor.py), or None without the sensor.
        """
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
        if self.posture_enabled:
            self._posture(detection, landmarks, width, height, now, lid_angle, result)

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
                self.calibration_info = self._info(self.calibration, datetime.now())
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

    def _posture(self, detection, landmarks, width: int, height: int, now: float, lid_angle: float | None,
                 result: FrameResult) -> None:
        """Posture is measured beside the eyes and never changes them; plain numbers go to core/posture.py."""
        matrix = None
        if landmarks and detection.facial_transformation_matrixes:
            matrix = [[float(v) for v in row] for row in detection.facial_transformation_matrixes[0]]
        points = [(p.x, p.y) for p in landmarks] if landmarks else []
        result.posture = read_posture(matrix, points, width, height, lid_angle)
        calibrator = self.posture_calibrator
        if calibrator.status == PostureCalibration.RUNNING or self.posture_monitor is not None:
            if self.tilt.reference is None:
                self.tilt.set_reference(lid_angle)  # the angle this baseline is (being) made at
            elif self.tilt.update(now, lid_angle):
                if calibrator.status == PostureCalibration.RUNNING:
                    self.start_posture_calibration(now)  # already recalibrating: just start that minute again
                    self.tilt.set_reference(lid_angle)
                elif not self.posture_needs_recalibration:  # one message until recalibrated
                    # The baseline no longer fits the screen. Say so and wait: the person chooses when to
                    # recalibrate (window: "Recalibrate now"); judging now could give false "slouching".
                    result.events.append(SCREEN_TILTED)
                    self.posture_needs_recalibration = True
                    self.posture_monitor.reset()
        if calibrator.status == PostureCalibration.RUNNING:
            calibrator.update(now, result.posture)
            if calibrator.status == PostureCalibration.DONE:
                self.posture_monitor = PostureMonitor(calibrator.result)
                result.events.append(POSTURE_CALIBRATION_DONE)
            elif calibrator.status == PostureCalibration.FAILED:
                result.events.append(POSTURE_CALIBRATION_FAILED)
            return  # not judged while the baseline is being recorded
        if self.posture_monitor is not None and not self.posture_needs_recalibration:
            result.posture_status = self.posture_monitor.update(now, result.posture)

    def close(self) -> None:
        self.landmarker.close()
