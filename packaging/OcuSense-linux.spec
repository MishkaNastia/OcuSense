# PyInstaller build recipe for the portable Linux version (x86_64, beta).
# Build on Linux from the project folder with:  python packaging/build_linux.py
# Result: dist/OcuSense/OcuSense (+ its _internal folder), packed as dist/OcuSense-linux-x64.tar.gz.
# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, get_package_paths

ROOT = Path(SPECPATH).parent

# MediaPipe loads its native library from mediapipe/tasks/c/ at runtime (libmediapipe.so on Linux).
_, mediapipe_dir = get_package_paths("mediapipe")
mediapipe_lib = (str(Path(mediapipe_dir) / "tasks" / "c" / "libmediapipe.so"), "mediapipe/tasks/c")

datas = [(str(ROOT / "models" / "face_landmarker.task"), "models"),
         (str(ROOT / "ocusense" / "assets"), "ocusense/assets")]
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
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="OcuSense", console=False)
coll = COLLECT(exe, a.binaries, a.datas, name="OcuSense")
