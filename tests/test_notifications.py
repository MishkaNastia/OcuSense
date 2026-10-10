"""macOS notifications: the text goes in as arguments, never into the script."""

import os
import unittest
from unittest import mock

from ocusense import notifications


class NotificationTest(unittest.TestCase):
    def test_message_is_passed_as_arguments(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(notifications.sys, "platform", "darwin"), \
                mock.patch.object(notifications.subprocess, "Popen") as popen:
            self.assertTrue(notifications.post('Say "hi" & quit', "Title"))
        command = popen.call_args.args[0]
        self.assertEqual(command[0], "osascript")
        self.assertEqual(command[-2:], ['Say "hi" & quit', "Title"])
        self.assertNotIn("hi", " ".join(command[:-2]))

    def test_disabled_in_tests_and_elsewhere(self):
        with mock.patch.object(notifications.subprocess, "Popen") as popen:
            with mock.patch.dict(os.environ, {"OCUSENSE_NO_NOTIFICATIONS": "1"}):
                self.assertFalse(notifications.post("x"))
            with mock.patch.object(notifications.sys, "platform", "linux"):
                self.assertFalse(notifications.post("x"))
        popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
