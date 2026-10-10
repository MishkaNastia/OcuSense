"""The MacBook lid (screen) angle, in degrees, from the built-in lid angle sensor.

Recent MacBook Pros have a hinge sensor that macOS exposes as an Apple HID device
(vendor 0x05AC, product 0x8104, sensor page 0x20, usage 0x8A "orientation"). Its
feature report 1 holds the angle as a 16-bit number: [1, low byte, high byte].
Apple doesn't document it, so everything here is optional: on Macs without it, when
it can't be opened, or with OCUSENSE_NO_LID_SENSOR set (tests), read() returns None
and posture uses the camera alone. Readings are never stored.
"""

import os
import time

from ocusense.config import LID_READ_INTERVAL

VENDOR_ID, PRODUCT_ID = 0x05AC, 0x8104
USAGE_PAGE, USAGE = 0x20, 0x8A


class LidSensor:
    def __init__(self, interval: float = LID_READ_INTERVAL):
        self.interval = interval
        self.available: bool | None = None  # None until the first try; False = no sensor here
        self._device = None
        self._last_read: float | None = None
        self._angle: float | None = None

    def _open(self) -> None:
        self.available = False
        if os.environ.get("OCUSENSE_NO_LID_SENSOR"):
            return
        try:
            import hid  # hidapi; only needed on Macs that have the sensor
            info = next((d for d in hid.enumerate(VENDOR_ID, PRODUCT_ID)
                         if d["usage_page"] == USAGE_PAGE and d["usage"] == USAGE), None)
            if info is None:
                return
            device = hid.device()
            device.open_path(info["path"])
        except Exception:  # no hidapi, no sensor, or access refused: camera only
            return
        self._device = device
        self.available = True

    def read(self, now: float | None = None) -> float | None:
        """The lid angle in degrees, read at most every `interval` seconds (the last value in between)."""
        now = time.monotonic() if now is None else now
        if self.available is None:
            self._open()
        if not self.available:
            return None
        if self._last_read is not None and now - self._last_read < self.interval:
            return self._angle
        self._last_read = now
        try:
            data = self._device.get_feature_report(1, 8)
            self._angle = float(int.from_bytes(bytes(data[1:3]), "little")) if len(data) >= 3 else None
        except Exception:  # the sensor went away: stop trying
            self.close()
            self._angle = None
        return self._angle

    def close(self) -> None:
        if self._device is not None:
            try:
                self._device.close()
            except Exception:
                pass
        self._device = None
        self.available = False
