"""Runs the camera + EyeMonitor in a background thread so the window never freezes.

The camera itself is opened on the main thread (open_camera): on macOS,
OpenCV can only ask for camera permission from the main thread.
"""

import threading
import time
from dataclasses import dataclass, field

import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from ocusense.config import CAMERA_INDEX, PREVIEW_WIDTH
from ocusense.core.calibration import STEPS
from ocusense.core.posture import PostureCalibration
from ocusense.monitoring.pipeline import EyeMonitor, FrameResult


@dataclass
class MonitorUpdate:
    """A snapshot of one processed frame, safe to hand to the window."""
    now: float
    face_found: bool
    reliable: bool
    reason: str
    openness: tuple
    blinked: bool
    events: list
    blinks: int
    calibrated: bool
    cal_status: str
    cal_step: int  # index into STEPS, or None
    cal_measuring: bool
    cal_seconds_left: float
    cal_error: str
    samples: list = field(default_factory=list)
    preview: QImage = None
    source: object = None  # the CameraWorker (camera run) that produced it
    observation: object = None  # core.models.FrameObservation for the measurements
    calibration_info: object = None  # core.models.CalibrationInfo in use for this frame, or None
    closeness: float = None  # face size now ÷ at calibration, for the distance reminder
    posture: object = None  # core.models.PostureReading on this frame, or None
    posture_status: object = None  # core.models.PostureStatus, or None before posture calibration
    posture_cal_status: str = PostureCalibration.IDLE
    posture_cal_seconds_left: float = 0.0
    posture_cal_error: str = ""


def open_camera(index: int = CAMERA_INDEX) -> cv2.VideoCapture | None:
    """Open the webcam on the calling (main) thread. Returns None if it can't."""
    camera = cv2.VideoCapture(index)
    if not camera.isOpened():
        camera.release()
        return None
    return camera


def to_qimage(frame_bgr: np.ndarray, width: int = PREVIEW_WIDTH) -> QImage:
    height = int(frame_bgr.shape[0] * width / frame_bgr.shape[1])
    small = cv2.resize(frame_bgr, (width, height), interpolation=cv2.INTER_AREA)
    rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
    return QImage(rgb.data, width, height, 3 * width, QImage.Format.Format_RGB888).copy()


def snapshot(monitor: EyeMonitor, result: FrameResult, now: float) -> MonitorUpdate:
    m = result.measurement
    cal = monitor.calibrator
    step = cal.step
    return MonitorUpdate(
        now=now,
        face_found=result.landmarks is not None,
        reliable=bool(m and m.reliable),
        reason=(m.reason if m and not m.reliable else ""),
        openness=result.openness,
        blinked=result.blinked,
        events=list(result.events),
        blinks=monitor.counter.count,
        calibrated=monitor.calibration is not None,
        cal_status=cal.status,
        cal_step=STEPS.index(step) if step else None,
        cal_measuring=cal.measuring(now) if step else False,
        cal_seconds_left=cal.seconds_left(now),
        cal_error=cal.error,
        samples=list(monitor.history.samples),
        preview=to_qimage(result.frame),
        observation=result.observation,
        calibration_info=monitor.calibration_info,
        closeness=result.closeness,
        posture=result.posture,
        posture_status=result.posture_status,
        posture_cal_status=monitor.posture_calibrator.status,
        posture_cal_seconds_left=monitor.posture_calibrator.seconds_left(now),
        posture_cal_error=monitor.posture_calibrator.error,
    )


class CameraWorker(QThread):
    """Reads frames from an already-open camera and runs the pipeline on each one.

    Results are sent with the `updated` signal; Qt delivers them on the
    interface thread, so widgets are only ever touched there."""

    updated = Signal(object)  # MonitorUpdate
    failed = Signal(str)

    def __init__(self, monitor, camera, parent=None):
        super().__init__(parent)
        self.monitor = monitor
        self.camera = camera
        self._lock = threading.Lock()
        self._calibration_requested = False
        self._posture_calibration_requested = False

    def request_calibration(self) -> None:
        with self._lock:
            self._calibration_requested = True

    def request_posture_calibration(self) -> None:
        with self._lock:
            self._posture_calibration_requested = True

    def run(self) -> None:
        while not self.isInterruptionRequested():
            ok, frame = self.camera.read()
            if not ok:
                self.failed.emit("The camera stopped sending pictures. Is another app using it?")
                return
            now = time.monotonic()
            with self._lock:
                calibrate, self._calibration_requested = self._calibration_requested, False
                posture, self._posture_calibration_requested = self._posture_calibration_requested, False
            if calibrate:
                self.monitor.start_calibration(now)
            if posture:
                self.monitor.start_posture_calibration(now)
            result = self.monitor.process(frame, now)
            update = snapshot(self.monitor, result, now)
            update.source = self
            self.updated.emit(update)
