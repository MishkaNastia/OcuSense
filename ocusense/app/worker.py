"""Runs the camera + EyeMonitor in a background thread so the window never freezes.

The camera itself is opened on the main thread (open_camera): on macOS,
OpenCV can only ask for camera permission from the main thread.
"""

import threading
import time
from dataclasses import dataclass, field

import cv2
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from ocusense.core.calibration import STEPS

PREVIEW_WIDTH = 480


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
    source: object = None  # the MonitorThread (camera run) that produced it


def open_camera(index=0):
    """Open the webcam on the calling (main) thread. Returns None if it can't."""
    camera = cv2.VideoCapture(index)
    if not camera.isOpened():
        camera.release()
        return None
    return camera


def to_qimage(frame_bgr, width=PREVIEW_WIDTH):
    height = int(frame_bgr.shape[0] * width / frame_bgr.shape[1])
    small = cv2.resize(frame_bgr, (width, height), interpolation=cv2.INTER_AREA)
    rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
    return QImage(rgb.data, width, height, 3 * width, QImage.Format.Format_RGB888).copy()


def snapshot(monitor, result, now):
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
    )


class MonitorThread(QThread):
    updated = Signal(object)  # MonitorUpdate
    failed = Signal(str)

    def __init__(self, monitor, camera, parent=None):
        super().__init__(parent)
        self.monitor = monitor
        self.camera = camera
        self._lock = threading.Lock()
        self._calibration_requested = False

    def request_calibration(self):
        with self._lock:
            self._calibration_requested = True

    def run(self):
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
