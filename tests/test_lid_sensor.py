"""The MacBook lid angle reader, with a fake hidapi (no hardware needed)."""

import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

from ocusense.lid_sensor import LidSensor


class FakeDevice:
    def __init__(self, reports):
        self.reports = list(reports)
        self.opened = None
        self.closed = False

    def open_path(self, path):
        self.opened = path

    def get_feature_report(self, report_id, size):
        report = self.reports.pop(0)
        if isinstance(report, Exception):
            raise report
        return report

    def close(self):
        self.closed = True


def fake_hid(device, sensor=True):
    devices = [{"usage_page": 0xFF00, "usage": 3, "path": b"other"}]
    if sensor:
        devices.append({"usage_page": 0x20, "usage": 0x8A, "path": b"lid"})
    return SimpleNamespace(enumerate=lambda vendor, product: devices, device=lambda: device)


class LidSensorTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("OCUSENSE_NO_LID_SENSOR", None)

    def sensor(self, hid_module):
        patcher = mock.patch.dict(sys.modules, {"hid": hid_module})
        patcher.start()
        self.addCleanup(patcher.stop)
        return LidSensor(interval=0.5)

    def test_reads_degrees_from_the_feature_report(self):
        device = FakeDevice([[1, 118, 0], [1, 0x2C, 0x01]])  # 118°, then 300° (two bytes, little-endian)
        sensor = self.sensor(fake_hid(device))
        self.assertEqual(sensor.read(0.0), 118.0)
        self.assertEqual(device.opened, b"lid")  # the orientation interface, not the others
        self.assertEqual(sensor.read(0.2), 118.0)  # within the interval: the last value, no new read
        self.assertEqual(sensor.read(0.6), 300.0)

    def test_no_sensor_on_this_mac(self):
        sensor = self.sensor(fake_hid(FakeDevice([]), sensor=False))
        self.assertIsNone(sensor.read(0.0))
        self.assertFalse(sensor.available)

    def test_no_hidapi(self):
        sensor = self.sensor(None)  # "import hid" fails
        self.assertIsNone(sensor.read(0.0))

    def test_switched_off_in_tests(self):
        os.environ["OCUSENSE_NO_LID_SENSOR"] = "1"
        sensor = self.sensor(fake_hid(FakeDevice([[1, 118, 0]])))
        self.assertIsNone(sensor.read(0.0))

    def test_a_failing_sensor_is_closed(self):
        device = FakeDevice([[1, 118, 0], OSError("gone")])
        sensor = self.sensor(fake_hid(device))
        self.assertEqual(sensor.read(0.0), 118.0)
        self.assertIsNone(sensor.read(1.0))
        self.assertTrue(device.closed)
        self.assertIsNone(sensor.read(2.0))  # doesn't keep trying


if __name__ == "__main__":
    unittest.main()
