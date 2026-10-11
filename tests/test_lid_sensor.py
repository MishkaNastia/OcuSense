"""The MacBook lid angle reader, with a fake IOKit backend (no hardware needed)."""

import os
import unittest
from unittest import mock

from ocusense.lid_sensor import LidSensor


class FakeBackend:
    def __init__(self, readings, device="lid"):
        self.readings = list(readings)
        self.device = device
        self.opened = 0
        self.closed = []

    def open(self):
        self.opened += 1
        return self.device

    def read(self, device):
        value = self.readings.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    def close(self, device):
        self.closed.append(device)


class LidSensorTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("OCUSENSE_NO_LID_SENSOR", None)

    def test_reads_degrees_at_most_every_interval(self):
        backend = FakeBackend([118.0, 300.0])
        sensor = LidSensor(interval=0.5, backend=backend)
        self.assertEqual(sensor.read(0.0), 118.0)
        self.assertEqual(sensor.read(0.2), 118.0)  # within the interval: the last value, no new read
        self.assertEqual(sensor.read(0.6), 300.0)
        self.assertEqual(backend.opened, 1)

    def test_no_sensor_on_this_mac(self):
        sensor = LidSensor(backend=FakeBackend([], device=None))
        self.assertIsNone(sensor.read(0.0))
        self.assertFalse(sensor.available)

    def test_a_backend_that_cant_start(self):
        class Broken:
            def open(self):
                raise OSError("no IOKit here")
        self.assertIsNone(LidSensor(backend=Broken()).read(0.0))

    def test_switched_off_in_tests(self):
        os.environ["OCUSENSE_NO_LID_SENSOR"] = "1"
        backend = FakeBackend([118.0])
        self.assertIsNone(LidSensor(backend=backend).read(0.0))
        self.assertEqual(backend.opened, 0)

    def test_a_failing_sensor_is_closed(self):
        backend = FakeBackend([118.0, OSError("gone")])
        sensor = LidSensor(interval=0.5, backend=backend)
        self.assertEqual(sensor.read(0.0), 118.0)
        self.assertIsNone(sensor.read(1.0))
        self.assertEqual(backend.closed, ["lid"])
        self.assertIsNone(sensor.read(2.0))  # doesn't keep trying

    def test_close_releases_the_device(self):
        backend = FakeBackend([118.0])
        sensor = LidSensor(backend=backend)
        sensor.read(0.0)
        sensor.close()
        self.assertEqual(backend.closed, ["lid"])
        self.assertFalse(sensor.available)


if __name__ == "__main__":
    unittest.main()
