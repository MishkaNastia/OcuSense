"""Draw the OcuSense app icon (logo B on paper) and save packaging/OcuSense.icns.

Run from the project folder:  python packaging/make_icon.py
With --ico (Windows builds) it saves packaging/OcuSense.ico instead (no macOS tools needed).
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPainterPath, QPen  # noqa: E402

from ocusense.ui import theme  # noqa: E402
from ocusense.ui.widgets.artwork import paint_logo  # noqa: E402

HERE = Path(__file__).resolve().parent


def draw(size):
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    # macOS icon grid: the tile is about 80% of the canvas, with rounded corners.
    margin = size * 0.1
    tile = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)
    shape = QPainterPath()
    shape.addRoundedRect(tile, tile.width() * 0.225, tile.width() * 0.225)
    p.fillPath(shape, QColor(theme.PAPER))
    p.setPen(QPen(QColor(theme.INK), max(1.0, size / 256)))
    p.drawPath(shape)
    logo = tile.width() * 0.74
    p.translate(tile.center().x() - logo / 2, tile.center().y() - logo / 2)
    paint_logo(p, logo)
    p.end()
    return image


def save_ico(path: Path, sizes=(16, 24, 32, 48, 64, 128, 256)) -> None:
    """A Windows .ico with PNG-compressed images inside (supported since Windows Vista)."""
    import struct

    from PySide6.QtCore import QBuffer, QByteArray, QIODevice

    images = []
    for size in sizes:
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        draw(size).save(buffer, "PNG")
        images.append((size, bytes(data)))
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for size, png in images:
        side = 0 if size >= 256 else size  # 0 means 256 in the ICO format
        entries += struct.pack("<BBBBHHII", side, side, 0, 0, 1, 32, len(png), offset)
        blobs += png
        offset += len(png)
    path.write_bytes(header + entries + blobs)


def main():
    QGuiApplication([])
    if "--ico" in sys.argv:
        save_ico(HERE / "OcuSense.ico")
        print("Saved", HERE / "OcuSense.ico")
        return
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "OcuSense.iconset"
        iconset.mkdir()
        for points in (16, 32, 128, 256, 512):
            draw(points).save(str(iconset / f"icon_{points}x{points}.png"))
            draw(points * 2).save(str(iconset / f"icon_{points}x{points}@2x.png"))
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(HERE / "OcuSense.icns")], check=True)
        shutil.copy(iconset / "icon_512x512@2x.png", HERE / "OcuSense-icon-1024.png")
    print("Saved", HERE / "OcuSense.icns")


if __name__ == "__main__":
    main()
