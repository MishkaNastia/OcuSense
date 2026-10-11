r"""Build the portable Windows version of OcuSense (x64). Run it ON WINDOWS:

    py -3.14 -m venv .venv
    .venv\Scripts\python -m pip install -r requirements.txt -r requirements-build.txt
    .venv\Scripts\python packaging\build_windows.py

Result:
    dist\OcuSense\OcuSense.exe        the app (keep it next to its _internal folder)
    dist\OcuSense-windows-x64.zip     the same folder zipped, to hand to testers

The build is unsigned, so Windows SmartScreen may warn the first time it opens
(see docs/windows.md). User data lives in %LOCALAPPDATA%\OcuSense, never in the app
folder, so replacing the folder with a newer build keeps everything.
"""

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"


def main() -> int:
    if sys.platform != "win32":
        print("build_windows.py builds the Windows version and must run on Windows "
              "(for the Mac app use ./packaging/build_mac.sh).")
        return 1
    if platform.machine().lower() not in ("amd64", "x86_64") or sys.maxsize <= 2**32:
        print(f"Use 64-bit Python on x64 Windows (found {platform.machine()}, "
              f"{'64' if sys.maxsize > 2**32 else '32'}-bit Python).")
        return 1
    python = sys.executable
    subprocess.run([python, str(ROOT / "packaging" / "make_icon.py"), "--ico"], check=True)
    subprocess.run([python, "-m", "PyInstaller", "--noconfirm", "--clean",
                    str(ROOT / "packaging" / "OcuSense-windows.spec")], check=True, cwd=ROOT)

    exe = DIST / "OcuSense" / "OcuSense.exe"
    # Quick check without a camera: the model loads and a frame can be analysed. A windowed
    # app has no console, so the result goes to a file as well as the exit code.
    log = DIST / "self-test.txt"
    log.unlink(missing_ok=True)
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", OCUSENSE_SELF_TEST_LOG=str(log),
               OCUSENSE_DATA_DIR=str(DIST / "self-test-data"))  # never touch the builder's real data
    done = subprocess.run([str(exe), "--self-test"], env=env, timeout=300)
    print(log.read_text(encoding="utf-8") if log.exists() else "(no self-test log written)")
    if done.returncode != 0:
        print(f"Self-test failed (exit code {done.returncode}).")
        return 1
    shutil.rmtree(DIST / "self-test-data", ignore_errors=True)

    archive = shutil.make_archive(str(DIST / "OcuSense-windows-x64"), "zip", root_dir=DIST, base_dir="OcuSense")
    print(f"Built: {exe}\nZipped: {archive}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
