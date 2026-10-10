#!/bin/zsh
# Build OcuSense.app into dist/. Run from anywhere:  ./packaging/build_mac.sh
set -e
cd "$(dirname "$0")/.."

.venv/bin/python packaging/make_icon.py
.venv/bin/python -m PyInstaller --noconfirm --clean packaging/OcuSense.spec

# Quick check without a camera: the model loads and a frame can be analysed.
QT_QPA_PLATFORM=offscreen dist/OcuSense.app/Contents/MacOS/OcuSense --self-test

echo "Built: $(pwd)/dist/OcuSense.app"
