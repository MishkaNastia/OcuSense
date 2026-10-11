"""Everything that differs between macOS and Windows, in one place.

The rest of OcuSense asks this module instead of checking sys.platform itself:

    user_data_dir()       where OcuSense keeps its files (never inside the app folder,
                          so replacing or updating the app never deletes them)
                            macOS:   ~/Library/Application Support/OcuSense
                            Windows: %LOCALAPPDATA%\\OcuSense
                            other:   $XDG_DATA_HOME/OcuSense or ~/.local/share/OcuSense
                          OCUSENSE_DATA_DIR overrides it (e.g. for a portable copy or tests).
    camera_backends()     which OpenCV camera APIs to try, in order
    camera_permission()   macOS: has OcuSense been allowed to use the camera yet?
    camera_help()         what to do when the camera can't be opened, in this system's words
    reduce_motion()       the system's "reduce motion / animations off" setting
    COMPUTER              "Mac" / "PC" / "computer", for messages like "stays on this Mac"
    NOTIFICATION_NAME     "Mac notification" / "Windows notification" / "notification"
    TRAY_NAME             "menu bar" / "system tray"
    THIS_APP              "the Mac app" / "the Windows app" (wording only; macOS text is unchanged)

Webcam frames are always processed on this computer; nothing here sends anything anywhere.
"""

import os
import sys
from pathlib import Path

IS_MAC = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"

COMPUTER = "Mac" if IS_MAC else "PC" if IS_WINDOWS else "computer"
NOTIFICATION_NAME = ("Mac notification" if IS_MAC else "Windows notification" if IS_WINDOWS
                     else "desktop notification")
TRAY_NAME = "menu bar" if IS_MAC else "system tray"
THIS_APP = "the Mac app" if IS_MAC else "the Windows app" if IS_WINDOWS else "the desktop app"
STOP_SHORTCUT = "⌘." if IS_MAC else "Ctrl+."  # the Stop shortcut, as each system writes it
APP_ID = "OcuSense.OcuSense"  # Windows: the app's identity for the taskbar and notifications
THIS_APP_START = THIS_APP[0].upper() + THIS_APP[1:]  # at the start of a sentence
NOTIFICATION_START = NOTIFICATION_NAME[0].upper() + NOTIFICATION_NAME[1:]


def user_data_dir(platform: str | None = None, environ=None, home: Path | None = None) -> Path:
    """The folder for OcuSense's own files (settings, calibration, recordings, collection).

    The arguments exist for tests; normally call it without any.
    """
    platform = platform or sys.platform
    environ = os.environ if environ is None else environ
    home = home or Path.home()
    override = environ.get("OCUSENSE_DATA_DIR")
    if override:
        return Path(override)
    if platform == "darwin":
        return home / "Library" / "Application Support" / "OcuSense"
    if platform == "win32":
        base = environ.get("LOCALAPPDATA") or environ.get("APPDATA")
        return (Path(base) if base else home / "AppData" / "Local") / "OcuSense"
    base = environ.get("XDG_DATA_HOME")
    return (Path(base) if base else home / ".local" / "share") / "OcuSense"


def camera_backends(platform: str | None = None) -> list[int | None]:
    """OpenCV capture APIs to try, in order (None = OpenCV's default for this system).

    Windows: DirectShow first — it opens most webcams quickly and reports "busy"
    cleanly — then Media Foundation (OpenCV's default there).
    """
    import cv2

    platform = platform or sys.platform
    if platform == "win32":
        return [cv2.CAP_DSHOW, cv2.CAP_MSMF]
    return [None]


_AV_LOADED = False


def _capture_device():
    """macOS AVCaptureDevice, loaded straight from the system framework (no extra package)."""
    global _AV_LOADED
    import objc
    if not _AV_LOADED:
        objc.loadBundle("AVFoundation", {}, bundle_path="/System/Library/Frameworks/AVFoundation.framework")
        objc.registerMetaDataForSelector(  # the completion handler is a block taking one BOOL
            b"AVCaptureDevice", b"requestAccessForMediaType:completionHandler:",
            {"arguments": {3: {"callable": {"retval": {"type": b"v"},
                                            "arguments": {0: {"type": b"^v"}, 1: {"type": b"Z"}}}}}})
        _AV_LOADED = True
    return objc.lookUpClass("AVCaptureDevice")


def camera_permission() -> str:
    """"granted", "denied", "undetermined" (macOS hasn't asked yet) or "unknown" (other systems)."""
    if not IS_MAC:
        return "unknown"
    try:
        status = int(_capture_device().authorizationStatusForMediaType_("vide"))  # AVMediaTypeVideo
    except Exception:
        return "unknown"
    return {0: "undetermined", 1: "denied", 2: "denied", 3: "granted"}.get(status, "unknown")


def request_camera_permission(answered) -> bool:
    """macOS: show the "allow camera" question; answered(granted) is called later, on another thread."""
    if not IS_MAC:
        return False
    try:
        _capture_device().requestAccessForMediaType_completionHandler_("vide", lambda granted: answered(bool(granted)))
    except Exception:
        return False
    return True


def camera_help(platform: str | None = None) -> str:
    platform = platform or sys.platform
    if platform == "darwin":
        return ("Could not open the camera. On a Mac: System Settings › Privacy & Security › Camera, "
                "allow this app (or Terminal / VS Code when running from there), then reopen it. "
                "If another app (a video call?) is using the camera, close it and try again.")
    if platform == "win32":
        return ("Could not open the camera. In Windows: Settings › Privacy & security › Camera, turn on "
                "“Camera access” and “Let desktop apps access your camera”. Windows lets only one app use "
                "a webcam at a time, so close Teams, Zoom, the Camera app or a browser call, then press Start again.")
    return ("Could not open the camera. Check that a webcam is connected, that this app may use it, "
            "and that no other app is using it, then press Start again.")


_activity = None  # macOS: the token that keeps App Nap away while OcuSense runs


def keep_running_in_background() -> bool:
    """macOS: stop App Nap from slowing OcuSense down while another app is in front.

    App Nap delays the timers of background apps, which would make Pomodoro, eye rest and
    reminder notifications arrive late. Idle system sleep is still allowed. Returns True
    when the request was made.
    """
    global _activity
    if not IS_MAC or _activity is not None:
        return _activity is not None
    try:
        from Foundation import NSActivityUserInitiatedAllowingIdleSystemSleep, NSProcessInfo
        _activity = NSProcessInfo.processInfo().beginActivityWithOptions_reason_(
            NSActivityUserInitiatedAllowingIdleSystemSleep, "Eye monitoring, Pomodoro and reminders run in the background")
    except Exception:
        return False
    return _activity is not None


def set_windows_app_id() -> bool:
    """Windows: give OcuSense its own identity, so its taskbar button and notifications say OcuSense."""
    if not IS_WINDOWS:
        return False
    try:
        import ctypes
        return ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID) == 0  # S_OK
    except Exception:
        return False


def reduce_motion() -> bool:
    """True when the system asks apps to keep animations to a minimum."""
    if IS_MAC:
        try:
            from AppKit import NSWorkspace
            return bool(NSWorkspace.sharedWorkspace().accessibilityDisplayShouldReduceMotion())
        except Exception:  # AppKit unavailable
            return False
    if IS_WINDOWS:
        try:  # Settings › Accessibility › Visual effects › Animation effects
            import ctypes
            enabled = ctypes.c_bool(True)
            SPI_GETCLIENTAREAANIMATION = 0x1042
            if ctypes.windll.user32.SystemParametersInfoW(SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(enabled), 0):
                return not enabled.value
        except Exception:
            return False
    return False
