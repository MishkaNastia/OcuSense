# PyInstaller build recipe for the portable Windows version (x64).
# Build on Windows from the project folder with:  python packaging\build_windows.py
# Result: dist\OcuSense\OcuSense.exe (+ its _internal folder), zipped as dist\OcuSense-windows-x64.zip.
# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, get_package_paths

ROOT = Path(SPECPATH).parent
VERSION = "0.1.0"

# MediaPipe loads its native library from mediapipe/tasks/c/ at runtime (libmediapipe.dll
# on Windows), so it must end up at exactly that place inside the bundle.
_, mediapipe_dir = get_package_paths("mediapipe")
mediapipe_lib = (str(Path(mediapipe_dir) / "tasks" / "c" / "libmediapipe.dll"), "mediapipe/tasks/c")

datas = [(str(ROOT / "models" / "face_landmarker.task"), "models"),
         (str(ROOT / "ocusense" / "assets"), "ocusense/assets")]  # games and Art shop pictures
if (ROOT / "ocusense" / "supabase.json").exists():  # the accounts project, when set up (docs/accounts.md)
    datas.append((str(ROOT / "ocusense" / "supabase.json"), "ocusense"))

a = Analysis(
    [str(ROOT / "packaging" / "run_ocusense.py")],
    pathex=[str(ROOT)],
    binaries=[mediapipe_lib],
    datas=datas,
    hiddenimports=collect_submodules("mediapipe.tasks.python") + ["mediapipe.tasks.c"],
    excludes=["tkinter", "IPython", "pytest", "AppKit", "Foundation", "UserNotifications", "objc"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="OcuSense",
    console=False,  # a windowed app: no black console window
    icon=str(ROOT / "packaging" / "OcuSense.ico"),
    version=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="OcuSense")
