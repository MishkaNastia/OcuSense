"""Build the portable Linux version of OcuSense (x86_64, beta). Run it ON LINUX:

    python3 -m venv .venv
    .venv/bin/python -m pip install -r requirements.txt -r requirements-build.txt
    .venv/bin/python packaging/build_linux.py

Result:
    dist/OcuSense/OcuSense             the app (keep it next to its _internal folder)
    dist/OcuSense-linux-x64.tar.gz     the same folder packed, to hand to testers

User data lives in ~/.local/share/OcuSense, never in the app folder.
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
    if not sys.platform.startswith("linux"):
        print("build_linux.py builds the Linux version and must run on Linux.")
        return 1
    if platform.machine().lower() not in ("x86_64", "amd64"):
        print(f"Use an x86_64 Linux (found {platform.machine()}).")
        return 1
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                    str(ROOT / "packaging" / "OcuSense-linux.spec")], check=True, cwd=ROOT)
    app = DIST / "OcuSense" / "OcuSense"
    log = DIST / "self-test.txt"
    log.unlink(missing_ok=True)
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", OCUSENSE_SELF_TEST_LOG=str(log),
               OCUSENSE_DATA_DIR=str(DIST / "self-test-data"))  # never touch the builder's real data
    done = subprocess.run([str(app), "--self-test"], env=env, timeout=300)
    print(log.read_text(encoding="utf-8") if log.exists() else "(no self-test log written)")
    if done.returncode != 0:
        print(f"Self-test failed (exit code {done.returncode}).")
        return 1
    shutil.rmtree(DIST / "self-test-data", ignore_errors=True)
    archive = shutil.make_archive(str(DIST / "OcuSense-linux-x64"), "gztar", root_dir=DIST, base_dir="OcuSense")
    print(f"Built: {app}\nPacked: {archive}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
