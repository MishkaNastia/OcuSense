"""The live graph of personal eye openness (both eyes, 0–100 %), drawn with QPainter.

Exact data only: a straight line between real samples, gaps where
measurement was paused, a dot at the lowest point of each counted blink.
"""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ocusense.config import CLOSE_BELOW, GRAPH_SECONDS, MAX_FRAME_GAP, REOPEN_ABOVE

from .. import theme



class OpennessGraph(QWidget):
    LEFT, RIGHT, TOP, BOTTOM = 60, 112, 10, 26

    def __init__(self, parent=None):
        super().__init__(parent)
        self.samples = []
        self.now = 0.0
        self.dimmed = False
        self.message = ""
        self.setMinimumHeight(220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAccessibleName("Personal eye openness graph")
        self.setAccessibleDescription(
            f"Last {GRAPH_SECONDS:.0f} seconds. Blink counted below {CLOSE_BELOW} and above {REOPEN_ABOVE}."
        )

    def set_data(self, samples, now, dimmed=False, message=""):
        self.samples = samples
        self.now = now
        self.dimmed = dimmed
        self.message = message
        self.update()

    def clear(self, message=""):
        self.set_data([], 0.0, False, message)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        plot = QRectF(self.LEFT, self.TOP, self.width() - self.LEFT - self.RIGHT,
                      self.height() - self.TOP - self.BOTTOM)

        def x_of(t):
            return plot.left() + plot.width() * (1 - (self.now - t) / GRAPH_SECONDS)

        def y_of(value):
            return plot.bottom() - plot.height() * value

        small = theme.number_font(12)
        p.setFont(small)
        p.setPen(theme.color(theme.GRAPHITE))
        p.drawText(QRectF(0, plot.top() - 2, self.LEFT - 10, 16), Qt.AlignmentFlag.AlignRight, "100%")
        p.drawText(QRectF(0, plot.bottom() - 14, self.LEFT - 10, 16), Qt.AlignmentFlag.AlignRight, "0%")
        for seconds_ago, text in ((GRAPH_SECONDS, f"−{GRAPH_SECONDS:.0f} s"), (GRAPH_SECONDS / 2, f"−{GRAPH_SECONDS / 2:.0f} s"), (0, "now")):
            x = plot.left() + plot.width() * (1 - seconds_ago / GRAPH_SECONDS)
            align = Qt.AlignmentFlag.AlignLeft if seconds_ago == GRAPH_SECONDS else (
                Qt.AlignmentFlag.AlignRight if seconds_ago == 0 else Qt.AlignmentFlag.AlignHCenter)
            box = QRectF(x - 40, plot.bottom() + 6, 80, 16)
            if seconds_ago == GRAPH_SECONDS:
                box = QRectF(x, plot.bottom() + 6, 80, 16)
            elif seconds_ago == 0:
                box = QRectF(x - 80, plot.bottom() + 6, 80, 16)
            p.drawText(box, align, text)

        # Thresholds (dashed, labelled outside the plot so they never cover data)
        dash = QPen(theme.color(theme.GRAPHITE), 1.25, Qt.PenStyle.DashLine)
        p.setPen(dash)
        for value, label in ((REOPEN_ABOVE, f"reopens · {REOPEN_ABOVE:.0%}"), (CLOSE_BELOW, f"closes · {CLOSE_BELOW:.0%}")):
            y = y_of(value)
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.save()
            p.setFont(theme.ui_font(12))
            p.setPen(theme.color(theme.GRAPHITE))
            p.drawText(QRectF(plot.right() + 10, y - 8, self.RIGHT - 12, 16), Qt.AlignmentFlag.AlignLeft, label)
            p.restore()

        # Axes
        p.setPen(QPen(theme.color(theme.INK), 1.5))
        p.drawLine(plot.bottomLeft(), plot.topLeft())
        p.drawLine(plot.bottomLeft(), plot.bottomRight())

        if self.message:
            p.setFont(theme.ui_font(15))
            p.setPen(theme.color(theme.GRAPHITE))
            p.drawText(plot, Qt.AlignmentFlag.AlignCenter, self.message)

        if not self.samples:
            return
        if self.dimmed:
            p.setOpacity(0.35)
        p.setClipRect(plot.adjusted(0, -8, 0, 8))

        line = QPainterPath()
        pen_down = False
        last_t = None
        dip = None  # lowest point since the last blink
        blink_points = []
        for t, openness, blinked in self.samples:
            if openness is None or (last_t is not None and t - last_t > MAX_FRAME_GAP):
                pen_down = False
            if openness is not None:
                point = QPointF(x_of(t), y_of(openness[2]))
                if pen_down:
                    line.lineTo(point)
                else:
                    line.moveTo(point)
                pen_down = True
                if dip is None or openness[2] < dip[1]:
                    dip = (point, openness[2])
            else:
                dip = None
            if blinked and dip is not None:
                blink_points.append(dip[0])
                dip = None
            last_t = t

        p.setPen(QPen(theme.color(theme.COBALT), 2.25))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(line)

        p.setPen(QPen(theme.color(theme.INK), 1.25))
        p.setBrush(QBrush(theme.color(theme.VERMILION)))
        for point in blink_points:
            p.drawEllipse(point, 5.5, 5.5)
