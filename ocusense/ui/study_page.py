"""The study screen: timer, blink count, controls, live graph and camera preview.

Display only. Button presses are exposed as buttons for MainWindow to connect;
every number shown here comes from the monitoring pipeline.
"""

from PySide6.QtCore import QPointF, QSize, Qt
from PySide6.QtGui import QBrush, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from . import theme
from .widgets.artwork import Composition
from .widgets.common import button, label, rule
from .widgets.openness_graph import OpennessGraph

PREVIEW_INSET = QSize(4, 4)  # keeps the preview image inside its 2 px border


def scaled_preview(pixmap: QPixmap, target: QLabel) -> QPixmap:
    return pixmap.scaled(target.size() - PREVIEW_INSET, Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)


class StudyPage(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(56, 40, 56, 28)
        layout.setSpacing(28)

        top = QHBoxLayout()
        session = QVBoxLayout()
        session.setSpacing(8)
        session.addWidget(label("STUDY SESSION", "eyebrow", theme.ui_font(13, QFont.Weight.Bold)))
        self.timer_label = label("00:00:00", font=theme.number_font(76))
        self.timer_label.setContentsMargins(0, 10, 0, 4)  # room for the tall digits
        self.timer_label.setAccessibleName("Session time")
        session.addWidget(self.timer_label)
        self.blink_label = label("", font=theme.ui_font(18))
        session.addWidget(self.blink_label)
        session.addSpacing(14)

        controls = QHBoxLayout()
        controls.setSpacing(10)
        self.start_button = button("Start", "primary")
        self.pause_button = button("Pause", "secondary")
        self.resume_button = button("Resume", "primary")
        self.stop_button = button("Stop", "quiet")
        self.recalibrate_button = button("Recalibrate", "quiet")
        self.stop_button.setToolTip("Stop and end this session (⌘.)")
        self.pause_button.setToolTip("Pause — the camera turns off until you resume")
        self.buttons = {"start": self.start_button, "pause": self.pause_button, "resume": self.resume_button,
                        "stop": self.stop_button, "recalibrate": self.recalibrate_button}
        for widget in self.buttons.values():
            controls.addWidget(widget)
        controls.addStretch(1)
        session.addLayout(controls)
        self.message_label = label("", "secondary", theme.ui_font(14), wrap=True)
        session.addWidget(self.message_label)
        top.addLayout(session, 1)
        top.addWidget(Composition(), 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(top)

        layout.addWidget(rule())
        heading = QHBoxLayout()
        heading.addWidget(label("Personal eye openness", font=theme.ui_font(24, QFont.Weight.DemiBold)))
        heading.addStretch(1)
        self.graph_caption = label("", "secondary", theme.ui_font(14))
        heading.addWidget(self.graph_caption)
        layout.addLayout(heading)
        self.graph = OpennessGraph()
        layout.addWidget(self.graph)
        layout.addWidget(self._legend())
        layout.addStretch(1)

        footer = QHBoxLayout()
        footer.setSpacing(14)
        self.preview = QLabel()
        self.preview.setFixedSize(128, 96)
        self.preview.setStyleSheet(f"border: 2px solid {theme.INK}; border-radius: 8px; background: {theme.PAPER_DEEP};")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setAccessibleName("Camera preview")
        footer.addWidget(self.preview)
        privacy = QVBoxLayout()
        privacy.addWidget(label("Camera preview", font=theme.ui_font(14, QFont.Weight.Bold)))
        privacy.addWidget(label("Processed on this Mac. Nothing is recorded or uploaded.", "secondary", theme.ui_font(13)))
        footer.addLayout(privacy)
        footer.addStretch(1)
        layout.addLayout(footer)
        self.set_blinks(0)

    # -------------------------------------------------------------- display
    def show_buttons(self, names: set[str], start_text: str = "Start") -> None:
        for name, widget in self.buttons.items():
            widget.setVisible(name in names)
        self.start_button.setText(start_text)

    def set_time(self, seconds: float) -> None:
        s = int(seconds)
        self.timer_label.setText(f"{s // 3600:02d}:{s // 60 % 60:02d}:{s % 60:02d}")

    def set_blinks(self, count: int) -> None:
        self.blink_label.setText(f"{count} blink{'s' if count != 1 else ''} this session")

    def set_preview(self, pixmap: QPixmap) -> None:
        self.preview.setPixmap(scaled_preview(pixmap, self.preview))

    def clear_preview(self) -> None:
        self.preview.clear()

    def _legend(self) -> QWidget:
        legend = QWidget()
        row = QHBoxLayout(legend)
        row.setContentsMargins(OpennessGraph.LEFT, 0, 0, 0)
        row.setSpacing(24)
        for kind, text in (("line", "Both eyes"), ("dash", "Thresholds"), ("dot", "Blink counted")):
            item = QHBoxLayout()
            item.setSpacing(8)
            swatch = QLabel()
            swatch.setPixmap(_legend_swatch(kind))
            item.addWidget(swatch)
            item.addWidget(label(text, font=theme.ui_font(14)))
            row.addLayout(item)
        row.addStretch(1)
        return legend


def _legend_swatch(kind: str) -> QPixmap:
    pixmap = QPixmap(28, 14)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    if kind == "line":
        p.setPen(QPen(theme.color(theme.COBALT), 2.5))
        p.drawLine(1, 7, 27, 7)
    elif kind == "dash":
        p.setPen(QPen(theme.color(theme.GRAPHITE), 1.5, Qt.PenStyle.DashLine))
        p.drawLine(1, 7, 27, 7)
    else:
        p.setPen(QPen(theme.color(theme.INK), 1.2))
        p.setBrush(QBrush(theme.color(theme.VERMILION)))
        p.drawEllipse(QPointF(14, 7), 5, 5)
    p.end()
    return pixmap
