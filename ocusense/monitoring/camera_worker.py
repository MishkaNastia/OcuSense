"""Runs the camera + EyeMonitor in a background thread so the window never freezes.

The camera itself is opened on the main thread (open_camera): on macOS,
OpenCV can only ask for camera permission from the main thread. On Windows it
tries DirectShow, then Media Foundation (see ocusense/system.py).
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
from ocusense.monitoring.pipeline import EyeMonitor, FrameResult
from ocusense.system import IS_WINDOWS, camera_backends


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
    brightness: float = None  # average picture brightness 0–255, for the lighting check (never saved)


def open_camera(index: int = CAMERA_INDEX, backends=None, check_frame: bool | None = None) -> cv2.VideoCapture | None:
    """Open the webcam on the calling (main) thread. Returns None if it can't.

    On Windows a camera that another app is using can still "open"; reading one
    frame tells the difference, so the next capture API is tried instead.
    """
    backends = camera_backends() if backends is None else backends
    check_frame = IS_WINDOWS if check_frame is None else check_frame
    for backend in backends:
        camera = cv2.VideoCapture(index) if backend is None else cv2.VideoCapture(index, backend)
        if camera.isOpened() and (not check_frame or camera.read()[0]):
            return camera
        camera.release()
    return None


def picture_brightness(frame_bgr: np.ndarray) -> float:
    """Average brightness 0–255 from a tiny copy of the frame (cheap; the number is all that is kept)."""
    small = cv2.resize(frame_bgr, (32, 24), interpolation=cv2.INTER_AREA)
    return float(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).mean())


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
        brightness=picture_brightness(result.frame),
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

    def request_calibration(self) -> None:
        with self._lock:
            self._calibration_requested = True

    def run(self) -> None:
        while not self.isInterruptionRequested():
            ok, frame = self.camera.read()
            if not ok:
                self.failed.emit("The camera stopped sending pictures. Is another app using it?")
                return
            now = time.monotonic()
            with self._lock:
                calibrate, self._calibration_requested = self._calibration_requested, False
            if calibrate:
                self.monitor.start_calibration(now)
            result = self.monitor.process(frame, now)
            update = snapshot(self.monitor, result, now)
            update.source = self
            self.updated.emit(update)
