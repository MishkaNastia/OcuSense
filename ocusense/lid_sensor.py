"""The MacBook lid (screen) angle, in degrees, from the built-in lid angle sensor.

Recent MacBook Pros have a hinge sensor that macOS exposes as an Apple HID device
(vendor 0x05AC, product 0x8104, sensor page 0x20, usage 0x8A "orientation"). Its
feature report 1 holds the angle as a 16-bit number: [1, low byte, high byte].

It is read straight through IOKit (ctypes, no extra package) with synchronous calls
only: nothing is scheduled on a run loop, so it doesn't matter which thread reads it
or that camera threads come and go. (hidapi schedules on the first thread's run loop
and crashed the app once that thread had ended.)

Apple doesn't document the sensor, so everything here is optional: on Macs without
it, elsewhere, when it can't be opened, or with OCUSENSE_NO_LID_SENSOR set (tests),
read() returns None and posture uses the camera alone. Readings are never stored.
"""

import ctypes
import os
import sys
import time

from ocusense.config import LID_READ_INTERVAL

VENDOR_ID, PRODUCT_ID = 0x05AC, 0x8104
USAGE_PAGE, USAGE = 0x20, 0x8A
REPORT_ID = 1


class IOKitBackend:
    """Finds, opens and reads the sensor with IOKit. All calls are synchronous."""
    FEATURE_REPORT = 2  # kIOHIDReportTypeFeature
    UTF8 = 0x08000100  # kCFStringEncodingUTF8
    SINT32 = 3  # kCFNumberSInt32Type

    def __init__(self):
        self.cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        self.io = ctypes.CDLL("/System/Library/Frameworks/IOKit.framework/IOKit")
        cf, io, ptr, index = self.cf, self.io, ctypes.c_void_p, ctypes.c_long
        cf.CFStringCreateWithCString.restype, cf.CFStringCreateWithCString.argtypes = ptr, (ptr, ctypes.c_char_p, ctypes.c_uint32)
        cf.CFNumberCreate.restype, cf.CFNumberCreate.argtypes = ptr, (ptr, index, ptr)
        cf.CFDictionaryCreateMutable.restype, cf.CFDictionaryCreateMutable.argtypes = ptr, (ptr, index, ptr, ptr)
        cf.CFDictionarySetValue.argtypes = (ptr, ptr, ptr)
        cf.CFSetGetCount.restype, cf.CFSetGetCount.argtypes = index, (ptr,)
        cf.CFSetGetValues.argtypes = (ptr, ptr)
        cf.CFRetain.restype, cf.CFRetain.argtypes = ptr, (ptr,)
        cf.CFRelease.argtypes = (ptr,)
        io.IOHIDManagerCreate.restype, io.IOHIDManagerCreate.argtypes = ptr, (ptr, ctypes.c_uint32)
        io.IOHIDManagerSetDeviceMatching.argtypes = (ptr, ptr)
        io.IOHIDManagerCopyDevices.restype, io.IOHIDManagerCopyDevices.argtypes = ptr, (ptr,)
        io.IOHIDDeviceOpen.restype, io.IOHIDDeviceOpen.argtypes = ctypes.c_int32, (ptr, ctypes.c_uint32)
        io.IOHIDDeviceClose.restype, io.IOHIDDeviceClose.argtypes = ctypes.c_int32, (ptr, ctypes.c_uint32)
        io.IOHIDDeviceGetReport.restype = ctypes.c_int32
        io.IOHIDDeviceGetReport.argtypes = (ptr, ctypes.c_int, index, ptr, ctypes.POINTER(index))

    def _matching(self):
        cf = self.cf
        keys = ctypes.c_byte.in_dll(cf, "kCFTypeDictionaryKeyCallBacks")
        values = ctypes.c_byte.in_dll(cf, "kCFTypeDictionaryValueCallBacks")
        matching = cf.CFDictionaryCreateMutable(None, 0, ctypes.byref(keys), ctypes.byref(values))
        for key, value in (("VendorID", VENDOR_ID), ("ProductID", PRODUCT_ID),
                           ("PrimaryUsagePage", USAGE_PAGE), ("PrimaryUsage", USAGE)):
            k = cf.CFStringCreateWithCString(None, key.encode(), self.UTF8)
            number = ctypes.c_int32(value)
            v = cf.CFNumberCreate(None, self.SINT32, ctypes.byref(number))
            cf.CFDictionarySetValue(matching, k, v)
            cf.CFRelease(k)
            cf.CFRelease(v)
        return matching

    def open(self):
        """The opened sensor device (a CF reference), or None if this Mac doesn't have one."""
        cf, io = self.cf, self.io
        manager = io.IOHIDManagerCreate(None, 0)  # never scheduled on a run loop, never opened
        if not manager:
            return None
        matching = self._matching()
        io.IOHIDManagerSetDeviceMatching(manager, matching)
        cf.CFRelease(matching)
        devices = io.IOHIDManagerCopyDevices(manager)
        device = None
        if devices:
            if cf.CFSetGetCount(devices) > 0:
                found = (ctypes.c_void_p * cf.CFSetGetCount(devices))()
                cf.CFSetGetValues(devices, found)
                device = cf.CFRetain(found[0])  # keep it after the set and the manager are released
            cf.CFRelease(devices)
        cf.CFRelease(manager)
        if device and io.IOHIDDeviceOpen(device, 0) != 0:
            cf.CFRelease(device)
            device = None
        return device

    def read(self, device) -> float | None:
        buffer = (ctypes.c_uint8 * 8)()
        length = ctypes.c_long(len(buffer))
        if self.io.IOHIDDeviceGetReport(device, self.FEATURE_REPORT, REPORT_ID, buffer, ctypes.byref(length)) != 0:
            raise OSError("the lid sensor didn't answer")
        if length.value < 3:
            return None
        return float(buffer[1] | buffer[2] << 8)

    def close(self, device) -> None:
        self.io.IOHIDDeviceClose(device, 0)
        self.cf.CFRelease(device)


class LidSensor:
    def __init__(self, interval: float = LID_READ_INTERVAL, backend=None):
        self.interval = interval
        self.available: bool | None = None  # None until the first try; False = no sensor here
        self._backend = backend
        self._device = None
        self._last_read: float | None = None
        self._angle: float | None = None

    def _open(self) -> None:
        self.available = False
        if os.environ.get("OCUSENSE_NO_LID_SENSOR"):
            return
        try:
            if self._backend is None:
                if sys.platform != "darwin":
                    return
                self._backend = IOKitBackend()
            device = self._backend.open()
        except Exception:  # no IOKit, no sensor, or access refused: camera only
            return
        if device:
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
            self._angle = self._backend.read(self._device)
        except Exception:  # the sensor went away: stop trying
            self.close()
            self._angle = None
        return self._angle

    def close(self) -> None:
        if self._device is not None:
            try:
                self._backend.close(self._device)
            except Exception:
                pass
        self._device = None
        self.available = False
