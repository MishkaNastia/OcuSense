"""macOS notifications: the text goes in as arguments, never into the script."""

import os
import sys
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


class FakeCenter:
    """Stands in for Apple's notification centre; `status` is what macOS would report."""

    def __init__(self, status, grant=True):
        self.status, self.grant, self.delivered, self.asked = status, grant, [], 0

    def getNotificationSettingsWithCompletionHandler_(self, handler):
        handler(mock.Mock(authorizationStatus=lambda: self.status))

    def requestAuthorizationWithOptions_completionHandler_(self, _options, handler):
        self.asked += 1
        handler(self.grant, None)

    def addNotificationRequest_withCompletionHandler_(self, request, _handler):
        self.delivered.append(request)


class FakeApi:
    UNAuthorizationOptionAlert = 4

    class UNMutableNotificationContent:
        @classmethod
        def alloc(cls):
            return cls()

        def init(self):
            return self

        def setTitle_(self, title):
            self.title = title

        def setBody_(self, body):
            self.body = body

    class UNNotificationRequest:
        @staticmethod
        def requestWithIdentifier_content_trigger_(identifier, content, _trigger):
            return (identifier, content.title, content.body)


class NativeNotificationTest(unittest.TestCase):
    """Inside OcuSense.app: Apple's framework (OcuSense name and icon), permission read from macOS each time."""

    def post(self, center):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(notifications.sys, "platform", "darwin"), \
                mock.patch.object(notifications.sys, "frozen", True, create=True), \
                mock.patch.object(notifications, "_native", (FakeApi, center)), \
                mock.patch.object(notifications.subprocess, "Popen") as popen:
            result = notifications.post("Go easy on your eyes and move back a little.", "Trying to lick the screen?")
        return result, popen

    def test_allowed_sends_with_the_app_identity(self):
        center = FakeCenter(notifications.AUTHORIZED)
        result, popen = self.post(center)
        self.assertTrue(result)
        popen.assert_not_called()  # not Script Editor
        identifier, title, body = center.delivered[0]
        self.assertTrue(identifier.startswith("app.ocusense."))
        self.assertEqual(title, "Trying to lick the screen?")

    def test_first_time_asks_then_sends(self):
        center = FakeCenter(notifications.NOT_DETERMINED, grant=True)
        self.post(center)
        self.assertEqual((center.asked, len(center.delivered)), (1, 1))

    def test_turned_off_is_respected(self):
        for status in (notifications.DENIED,):
            center = FakeCenter(status)
            result, popen = self.post(center)
            self.assertEqual(center.delivered, [])
            popen.assert_not_called()  # no sneaking around the choice via Script Editor
        declined = FakeCenter(notifications.NOT_DETERMINED, grant=False)
        self.post(declined)
        self.assertEqual(declined.delivered, [])

    def test_different_reminders_do_not_replace_each_other(self):
        center = FakeCenter(notifications.AUTHORIZED)
        self.post(center)
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(notifications.sys, "platform", "darwin"), \
                mock.patch.object(notifications.sys, "frozen", True, create=True), \
                mock.patch.object(notifications, "_native", (FakeApi, center)):
            notifications.post("Hey, you should take a break…", "Time for a break")
        self.assertNotEqual(center.delivered[0][0], center.delivered[1][0])

    def test_falls_back_to_osascript_without_the_framework(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(notifications.sys, "platform", "darwin"), \
                mock.patch.object(notifications.sys, "frozen", True, create=True), \
                mock.patch.object(notifications, "_native", False), \
                mock.patch.object(notifications.subprocess, "Popen") as popen:
            self.assertTrue(notifications.post("x", "y"))
        popen.assert_called_once()


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(sys.platform == "darwin", "macOS notification centre only")
class ShowInFrontTest(unittest.TestCase):
    """macOS hides an app's notifications while it is in front unless a delegate says otherwise."""

    def test_delegate_asks_for_a_banner(self):
        import UserNotifications as api
        from ocusense import notifications
        delegate = notifications.front_delegate(api)
        shown = []
        delegate.userNotificationCenter_willPresentNotification_withCompletionHandler_(None, None, shown.append)
        self.assertEqual(shown, [notifications.presentation_options(api)])
        self.assertTrue(shown[0] & int(api.UNNotificationPresentationOptionBanner))


class EveryNotificationTest(unittest.TestCase):
    def test_test_mode_covers_every_kind(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from ocusense.ui.app import all_notifications
        titles = [title for title, _ in all_notifications()]
        self.assertEqual(len(titles), len(set(titles)))  # each kind its own notification
        for expected in ("Trying to lick the screen?", "Time for a break", "Break’s over"):
            self.assertIn(expected, titles)
        self.assertEqual(len(titles), 8)
