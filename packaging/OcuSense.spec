# PyInstaller build recipe for OcuSense.app (macOS).
# Build from the project folder with:  ./packaging/build_mac.sh
# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, get_package_paths

ROOT = Path(SPECPATH).parent
VERSION = "0.1.0"

# MediaPipe loads its native library from mediapipe/tasks/c/ at runtime, so it
# must end up at exactly that place inside the app.
_, mediapipe_dir = get_package_paths("mediapipe")
mediapipe_lib = (str(Path(mediapipe_dir) / "tasks" / "c" / "libmediapipe.dylib"), "mediapipe/tasks/c")

a = Analysis(
    [str(ROOT / "packaging" / "run_ocusense.py")],
    pathex=[str(ROOT)],
    binaries=[mediapipe_lib],
    datas=[(str(ROOT / "models" / "face_landmarker.task"), "models"),
           (str(ROOT / "ocusense" / "assets"), "ocusense/assets")]  # EyeGame art
    # The Supabase project for accounts, when one is set up (see docs/accounts.md).
    + ([(str(ROOT / "ocusense" / "supabase.json"), "ocusense")] if (ROOT / "ocusense" / "supabase.json").exists() else []),
    hiddenimports=collect_submodules("mediapipe.tasks.python") + ["mediapipe.tasks.c"],
    excludes=["tkinter", "IPython", "pytest"],  # matplotlib stays: MediaPipe vision imports it
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="OcuSense",
    console=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,  # ad-hoc signature: fine for your own Mac
)
coll = COLLECT(exe, a.binaries, a.datas, name="OcuSense")

app = BUNDLE(
    coll,
    name="OcuSense.app",
    icon=str(ROOT / "packaging" / "OcuSense.icns"),
    bundle_identifier="app.ocusense.OcuSense",
    version=VERSION,
    info_plist={
        "CFBundleName": "OcuSense",
        "CFBundleDisplayName": "OcuSense",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "LSMinimumSystemVersion": "14.0",
        "NSHighResolutionCapable": True,
        # Keep timers on time in the background (Pomodoro, reminders and their notifications).
        "NSAppSleepDisabled": True,
        # Shown by macOS when OcuSense first asks for the camera. Required:
        # without it macOS closes the app as soon as it opens the camera.
        "NSCameraUsageDescription": (
            "OcuSense uses the camera to measure eye openness and count blinks. "
            "Images are processed on this Mac and never saved or uploaded."
        ),
    },
)
