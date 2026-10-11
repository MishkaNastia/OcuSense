"""macOS / Windows differences (ocusense/system.py), checked on whatever system runs the tests,
plus navigating the window while monitoring continues."""

import os
import unittest
from pathlib import Path
from unittest import mock

import cv2

from ocusense import notifications, system
from ocusense.monitoring import camera_worker


class PathsTest(unittest.TestCase):
    home = Path("/home/someone")

    def test_user_data_folder_per_system(self):
        self.assertEqual(system.user_data_dir("darwin", {}, self.home),
                         self.home / "Library" / "Application Support" / "OcuSense")
        self.assertEqual(system.user_data_dir("win32", {"LOCALAPPDATA": r"C:\Users\Mira\AppData\Local"}, self.home),
                         Path(r"C:\Users\Mira\AppData\Local") / "OcuSense")
        self.assertEqual(system.user_data_dir("win32", {}, self.home), self.home / "AppData" / "Local" / "OcuSense")
        self.assertEqual(system.user_data_dir("linux", {}, self.home), self.home / ".local" / "share" / "OcuSense")
        self.assertEqual(system.user_data_dir("win32", {"OCUSENSE_DATA_DIR": "/portable"}, self.home),
                         Path("/portable"))

    def test_data_never_inside_the_app_folder(self):
        from ocusense.config import resource_root
        for platform in ("darwin", "win32"):
            folder = system.user_data_dir(platform, {"LOCALAPPDATA": str(self.home / "Local")}, self.home)
            self.assertNotIn(str(resource_root()), str(folder))

    def test_every_saved_file_uses_the_data_folder(self):
        from ocusense import accounts, calibration_store, preferences, recording
        folder = Path("/data-test")
        clean = {k: v for k, v in os.environ.items() if not k.startswith("OCUSENSE_")}
        with mock.patch.dict(os.environ, clean | {"OCUSENSE_DATA_DIR": str(folder)}, clear=True):
            self.assertEqual(preferences.default_path(), folder / "preferences.json")
            self.assertEqual(calibration_store.default_path(), folder / "calibration.json")
            self.assertEqual(recording.default_directory(), folder / "recordings")
            self.assertEqual(accounts.AccountStore().path, folder / "account.json")

    def test_camera_help_and_backends(self):
        self.assertIn("Privacy & security", system.camera_help("win32"))
        self.assertIn("Teams", system.camera_help("win32"))
        self.assertIn("System Settings", system.camera_help("darwin"))
        self.assertEqual(system.camera_backends("win32"), [cv2.CAP_DSHOW, cv2.CAP_MSMF])
        self.assertEqual(system.camera_backends("darwin"), [None])


class PortableCodeTest(unittest.TestCase):
    def test_no_platform_only_date_formats(self):
        """%-d and friends work on macOS but raise on Windows."""
        import re
        root = Path(__file__).resolve().parents[1] / "ocusense"
        for path in root.rglob("*.py"):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                code = line.split("#")[0]
                self.assertIsNone(re.search(r"%-[a-zA-Z]", code), f"{path.name}:{number}")


class FakeCapture:
    opened = {}  # backend → (opens, gives a frame)

    def __init__(self, index, backend=None):
        self.backend = backend
        self.ok, self.frame = self.opened.get(backend, (False, False))
        self.released = False

    def isOpened(self):
        return self.ok

    def read(self):
        return self.frame, None

    def release(self):
        self.released = True


class CameraTest(unittest.TestCase):
    def test_tries_the_next_api_when_the_camera_is_busy(self):
        FakeCapture.opened = {cv2.CAP_DSHOW: (True, False), cv2.CAP_MSMF: (True, True)}  # DirectShow: busy
        with mock.patch.object(camera_worker.cv2, "VideoCapture", FakeCapture):
            camera = camera_worker.open_camera(0, backends=[cv2.CAP_DSHOW, cv2.CAP_MSMF], check_frame=True)
        self.assertEqual(camera.backend, cv2.CAP_MSMF)

    def test_none_when_no_api_works(self):
        FakeCapture.opened = {}
        with mock.patch.object(camera_worker.cv2, "VideoCapture", FakeCapture):
            self.assertIsNone(camera_worker.open_camera(0, backends=[None], check_frame=False))


class NotificationTest(unittest.TestCase):
    def test_windows_uses_the_tray(self):
        shown = []
        clean = {k: v for k, v in os.environ.items() if k != "OCUSENSE_NO_NOTIFICATIONS"}
        with mock.patch.object(notifications.sys, "platform", "win32"), mock.patch.dict(os.environ, clean, clear=True):
            notifications.set_fallback(None)
            self.assertFalse(notifications.post("hi", "OcuSense"))  # no tray: nothing shown, no crash
            notifications.set_fallback(lambda message, title: shown.append((title, message)) or True)
            self.assertTrue(notifications.post("Move back a little.", "Trying to lick the screen?"))
            notifications.set_fallback(None)
        self.assertEqual(shown, [("Trying to lick the screen?", "Move back a little.")])


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from tests.test_main_window import MODEL_PATH, FakeThread  # noqa: E402


@unittest.skipUnless(MODEL_PATH.exists(), "model file missing - run download_model.py")
class NavigationTest(unittest.TestCase):
    def setUp(self):
        from ocusense.ui.main_window import MainWindow
        self.window = MainWindow()
        self.window.notify = lambda message, title: None
        self.thread = FakeThread()
        self.window._start_camera = lambda: (setattr(self.window, "thread", self.thread), True)[1]

    def tearDown(self):
        self.window.close()

    def test_switching_pages_keeps_monitoring(self):
        w = self.window
        w.monitor.calibration = object()
        w.start()
        self.assertEqual(w.state, "monitoring")
        for key in ("library", "games", "time_log", "statistics", "study", "settings"):
            w.sidebar.items[key].click()
            self.assertEqual(w.state, "monitoring")  # switching pages never interrupts monitoring
            self.assertFalse(self.thread.stopped)


if __name__ == "__main__":
    unittest.main()
