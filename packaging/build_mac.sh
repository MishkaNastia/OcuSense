#!/bin/zsh
# Build OcuSense.app and replace the copy on your Desktop.
# Run from anywhere:  ./packaging/build_mac.sh
# Add --no-install to only build into dist/ without touching the Desktop.
set -e
cd "$(dirname "$0")/.."

.venv/bin/python packaging/make_icon.py
.venv/bin/python -m PyInstaller --noconfirm --clean packaging/OcuSense.spec

# Quick check without a camera: the model loads and a frame can be analysed.
# A throwaway data folder, so the check never creates or changes your real OcuSense files.
SELF_TEST_DATA="$(mktemp -d)"
OCUSENSE_DATA_DIR="$SELF_TEST_DATA" QT_QPA_PLATFORM=offscreen dist/OcuSense.app/Contents/MacOS/OcuSense --self-test
rm -rf "$SELF_TEST_DATA"

echo "Built: $(pwd)/dist/OcuSense.app"

if [[ "$1" == "--no-install" ]]; then
  exit 0
fi

DESKTOP_APP="$HOME/Desktop/OcuSense.app"
if pgrep -f "OcuSense.app/Contents/MacOS/OcuSense" > /dev/null; then
  echo "OcuSense is open — quit it (⌘Q) and run this script again to replace $DESKTOP_APP."
  exit 1
fi
rm -rf "$DESKTOP_APP"
ditto dist/OcuSense.app "$DESKTOP_APP"
codesign --verify --deep "$DESKTOP_APP"
echo "Replaced: $DESKTOP_APP"
