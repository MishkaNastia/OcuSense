"""macOS notifications (Notification Centre), shown even while OcuSense is in the background.

Inside the packaged OcuSense.app, notifications go through Apple's UserNotifications
framework, so they appear with the OcuSense name and icon. Before each one, the
current permission is read straight from macOS (never a remembered answer); the very
first time, macOS asks "Allow notifications from OcuSense?". If the person turned
notifications off for OcuSense, nothing is shown — their choice is respected.
macOS normally hides an app's notifications while that app is in front; OcuSense
registers a small delegate (_ShowInFront) so they appear as banners anyway.

Elsewhere (e.g. `python -m ocusense`, where Apple's API needs a real app bundle) or if
the framework is unavailable, it falls back to the system's `osascript` ("display
notification", shown under Script Editor). The text is passed as arguments, never pasted
into the script. With OCUSENSE_NO_NOTIFICATIONS set (tests), nothing is shown.

On Windows (and other systems) notifications are shown by the OcuSense icon in the
system tray (Qt's QSystemTrayIcon.showMessage, a Windows notification), which the tray
registers with set_fallback(). Without a tray, nothing is shown.
"""

import os
import subprocess
import sys
import zlib

SCRIPT = ("on run argv", "display notification (item 1 of argv) with title (item 2 of argv)", "end run")
# UNAuthorizationStatus values
NOT_DETERMINED, DENIED, AUTHORIZED, PROVISIONAL, EPHEMERAL = 0, 1, 2, 3, 4

_native = None  # (UserNotifications module, notification centre) once loaded, or False if unavailable
_delegate = None  # kept alive here: the notification centre only holds a weak reference
_fallback = None  # off macOS: callable(message, title) -> bool, set by the system tray icon


def set_fallback(show) -> None:
    """Off macOS: how to show a notification (the system tray icon registers this)."""
    global _fallback
    _fallback = show


def post(message: str, title: str = "OcuSense") -> bool:
    """Show a notification without waiting for it. Returns False if it couldn't be shown."""
    if os.environ.get("OCUSENSE_NO_NOTIFICATIONS"):
        return False
    if sys.platform != "darwin":
        if _fallback is None:
            return False
        try:
            return bool(_fallback(message, title))
        except Exception:
            return False
    if getattr(sys, "frozen", False) and _post_native(message, title):  # frozen: inside OcuSense.app
        return True
    return _post_osascript(message, title)


def _post_osascript(message: str, title: str) -> bool:
    command = ["osascript"]
    for line in SCRIPT:
        command += ["-e", line]
    try:
        subprocess.Popen(command + [message, title], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        return False
    return True


def presentation_options(api) -> int:
    """Banner + Notification Centre list (macOS 11+), or the older "alert" style."""
    if hasattr(api, "UNNotificationPresentationOptionBanner"):
        return int(api.UNNotificationPresentationOptionBanner | api.UNNotificationPresentationOptionList)
    return int(api.UNNotificationPresentationOptionAlert)


_delegate_class = None


def front_delegate(api):
    """A delegate that tells macOS to show OcuSense's notifications even while OcuSense is in front."""
    global _delegate_class
    if _delegate_class is None:
        import objc
        from Foundation import NSObject

        protocol = objc.protocolNamed("UNUserNotificationCenterDelegate")

        class _ShowInFront(NSObject, protocols=[protocol]):
            def userNotificationCenter_willPresentNotification_withCompletionHandler_(self, center, note, handler):
                handler(presentation_options(api))

        _delegate_class = _ShowInFront
    return _delegate_class.alloc().init()


def _load_native():
    global _native, _delegate
    if _native is None:
        try:
            import UserNotifications as api
            center = api.UNUserNotificationCenter.currentNotificationCenter()
            _native = (api, center)
        except Exception:  # framework missing or no app bundle: use osascript instead
            _native = False
            return None
        try:
            _delegate = front_delegate(api)
            center.setDelegate_(_delegate)
        except Exception:  # without it, notifications still show while OcuSense is in the background
            _delegate = None
    return _native or None


def _post_native(message: str, title: str) -> bool:
    """Send through Apple's framework (OcuSense name and icon). False if it can't be used here."""
    native = _load_native()
    if native is None:
        return False
    api, center = native

    def deliver():
        content = api.UNMutableNotificationContent.alloc().init()
        content.setTitle_(title)
        content.setBody_(message)
        # One identifier per kind of reminder: a new one replaces the previous of the same kind only.
        identifier = f"app.ocusense.{zlib.crc32(title.encode()):08x}"
        center.addNotificationRequest_withCompletionHandler_(
            api.UNNotificationRequest.requestWithIdentifier_content_trigger_(identifier, content, None), None)

    def answered(granted, _error):  # Apple's thread
        if granted:
            deliver()

    def setting(settings):  # Apple's thread: macOS's current choice for OcuSense
        status = int(settings.authorizationStatus())
        if status in (AUTHORIZED, PROVISIONAL, EPHEMERAL):
            deliver()
        elif status == NOT_DETERMINED:
            center.requestAuthorizationWithOptions_completionHandler_(api.UNAuthorizationOptionAlert, answered)
        # DENIED: notifications are off for OcuSense in System Settings — respect that

    center.getNotificationSettingsWithCompletionHandler_(setting)
    return True
