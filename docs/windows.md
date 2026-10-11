# OcuSense on Windows

OcuSense is one Python codebase for macOS and Windows. Everything that differs between
the two systems lives in `ocusense/system.py`. Windows packaging sits next to the Mac
packaging in `packaging/`.

> **Status: prepared, not yet verified on Windows.** The Windows support was written
> and tested on a Mac. No Windows executable has been built or run yet. Treat the first
> Windows build as a test build until the checklist below has been completed on a real
> Windows PC.

## What is different on Windows

| Topic | macOS | Windows |
|---|---|---|
| Your data (settings, calibration, recordings, garden, time log) | `~/Library/Application Support/OcuSense` | `%LOCALAPPDATA%\OcuSense` (never inside the app folder, so replacing the app keeps it) |
| Camera | OpenCV default (AVFoundation) | DirectShow first, then Media Foundation; a camera that "opens" but sends no picture (busy) is skipped |
| Camera problems | System Settings › Privacy & Security › Camera | message points to Settings › Privacy & security › Camera ("Let desktop apps access your camera") and says to close Teams/Zoom/Camera, since Windows lets one app use a webcam at a time |
| Status icon | menu bar, monochrome template icon | system tray, full-colour icon; a click opens the window |
| Notifications | Notification Centre (UserNotifications) | shown by the tray icon (Qt `showMessage`, appears as a Windows notification) |
| Reduce motion | Accessibility › Reduce motion | Accessibility › Visual effects › Animation effects off |
| Sign-in token | macOS Keychain | Windows Credential Manager ("app.ocusense.OcuSense/refresh-token") |
| Fonts | system font (SF Pro) | system font (Segoe UI); numbers in the fixed system font |
| Window icon | from OcuSense.app | set by the app; the .exe has `OcuSense.ico`; the app sets its own taskbar identity (AppUserModelID) so notifications say OcuSense |
| Screen tilt (posture) | MacBook lid sensor, when present | not available: posture uses the camera only |
| Title bar | blended into the window | the normal Windows title bar |
| Face model | loaded from its bytes on both systems, so folder names with non-English letters work |  |

Monitoring keeps running while other apps are in front: the camera runs in its own
thread, independent of window focus. Stop and Quit release the camera on both systems
(`MainWindow._stop_camera`). Webcam frames are processed in memory on the computer and
never saved or sent anywhere.

The pinned dependencies all publish Windows x64 wheels (`mediapipe==1.1.0`,
`PySide6-Essentials==6.12.0`, `pyinstaller==6.22.3`, `opencv-contrib-python` through
MediaPipe), so Windows uses exactly the same versions as the Mac. **Target: Windows 10/11
x64.** Windows on ARM isn't targeted yet: MediaPipe has an arm64 wheel, but the
OpenCV it needs doesn't.

## Building it

### Option A — on GitHub (no Windows PC needed)

The workflow `.github/workflows/windows-build.yml` only runs when someone starts it.
It doesn't run on push, it can't publish anything, and it only reads the repository.

1. For login in the Windows build, add two **repository variables** once (GitHub › Settings ›
   Secrets and variables › Actions › Variables): `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY`.
   They're the same public values as in `ocusense/supabase.json`. Without them the build works,
   but its Log in page says accounts aren't set up.
2. On GitHub, go to **Actions › "Windows build (manual)" › Run workflow**, and choose
   the branch.
3. When it finishes, download **OcuSense-windows-x64** from the run's *Artifacts*
   section. It's a zip that is kept for 14 days and is not a public release.

The workflow:
- installs the pinned dependencies,
- builds with `packaging/build_windows.py`,
- runs the built app's camera-free self-test (the model loads and a frame is
  analysed), and uploads the zip,
- then runs the unit tests on Windows. A failure there shows as a red run, but the zip
  is still uploaded so it can be inspected.

### Option B — on a Windows PC

Install 64-bit Python 3.14 from python.org, then in the project folder:

```bat
py -3.14 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt -r requirements-build.txt
.venv\Scripts\python packaging\build_windows.py
```

The result is `dist\OcuSense\OcuSense.exe` (keep it next to its `_internal` folder) and
`dist\OcuSense-windows-x64.zip`.

## Installing the portable build

1. Unzip `OcuSense-windows-x64.zip` anywhere, for example in your Documents.
2. Open `OcuSense\OcuSense.exe`.
3. To update, replace the folder with the new one. Your data in
   `%LOCALAPPDATA%\OcuSense` stays.

**Security warning:** this build is **not code-signed**, so Windows SmartScreen may
show "Windows protected your PC" the first time. Only run builds you downloaded
yourself from your own GitHub Actions run or built yourself. Don't turn off
SmartScreen or antivirus protection to run it. Signing the app with a code-signing
certificate (a paid service, not set up) is what removes the warning for everyone.

## Still to verify on a real Windows PC

None of these have been checked yet:

- [ ] The GitHub workflow builds, and the self-test passes (`dist\self-test.txt`).
- [ ] The unit tests pass on Windows.
- [ ] `OcuSense.exe` opens with its icon, and the window and fonts look right.
- [ ] Camera:
  - [ ] the built-in webcam starts with DirectShow;
  - [ ] with camera access off in Settings, the message tells you what to do;
  - [ ] with Teams/Zoom using the camera, the "another app" message appears;
  - [ ] the camera light turns off after Stop and after Quit.
- [ ] Calibration, monitoring, the blink counting, the graphs and Statistics work.
- [ ] Monitoring continues while another app is in front and while OcuSense is minimised.
- [ ] The tray icon appears; clicking it opens the window; the menu actions work.
- [ ] Notifications (distance reminder, Pomodoro) appear as Windows notifications.
- [ ] Display scaling at 100 %, 125 %, 150 % and 200 %, including moving the window
      between monitors with different scaling. (This was only simulated on a Mac with
      `QT_SCALE_FACTOR`.)
- [ ] Games, the Garden and the Gallery work; garden progress survives replacing the app
      folder.
- [ ] Data is in `%LOCALAPPDATA%\OcuSense`, and nothing is written next to the .exe.
- [ ] How SmartScreen and antivirus react to the unsigned build.

## What was tested on the Mac

- The unit tests run on macOS. They cover the Windows data paths, the order of camera
  APIs and skipping a busy camera (with a fake camera), Windows wording for camera
  help, tray notifications as the Windows path, and that no Windows-incompatible date
  formats are left in the code.
- The Mac app still builds and passes its self-test.
- Screenshots at 150 % scaling (simulated with `QT_SCALE_FACTOR=1.5`) and in a narrow
  window.
