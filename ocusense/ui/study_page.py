"""The study screen: timer, controls, live personal eye openness, last-60-seconds measurements.

Display only. Button presses are exposed as buttons for MainWindow to connect;
every number shown here comes from ocusense.core (no calculations here beyond
formatting). Unavailable values are shown as "—" or "Collecting data", never 0.
"""

from PySide6.QtCore import QPointF, QSize, Qt
from PySide6.QtGui import QBrush, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from ocusense.config import MIN_VALID_SECONDS_FOR_RATE
from ocusense.core.measurements import combined_openness_percent, openness_percent
from ocusense.core.models import CalibrationInfo, FrameObservation, RollingSnapshot
from ocusense.core.stats import format_duration, format_metric

from . import theme
from .widgets.artwork import Composition
from .widgets.common import button, label, rule, vline
from .widgets.openness_graph import OpennessGraph

PREVIEW_INSET = QSize(4, 4)  # keeps the preview image inside its 2 px border
COLLECTING = "Collecting data"
UNAVAILABLE = "—"


def scaled_preview(pixmap: QPixmap, target: QLabel) -> QPixmap:
    return pixmap.scaled(target.size() - PREVIEW_INSET, Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)


def _percent(value: float | None) -> str:
    return UNAVAILABLE if value is None else f"{value:.0f}%"


class StudyPage(QScrollArea):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content.setObjectName("Root")
        self.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(56, 36, 56, 28)
        layout.setSpacing(24)

        # --- session, controls, artwork
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
        session.addSpacing(12)
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

        # --- live personal eye openness
        layout.addWidget(rule())
        heading = QHBoxLayout()
        heading.addWidget(label("Personal eye openness", font=theme.ui_font(24, QFont.Weight.DemiBold)))
        heading.addSpacing(16)
        live_tag = label("LIVE", "eyebrow", theme.ui_font(12, QFont.Weight.Bold))
        heading.addWidget(live_tag, 0, Qt.AlignmentFlag.AlignBottom)
        heading.addStretch(1)
        self.graph_caption = label("", "secondary", theme.ui_font(14))
        heading.addWidget(self.graph_caption)
        layout.addLayout(heading)
        readout = QHBoxLayout()
        readout.setSpacing(18)
        self.openness_value = label(UNAVAILABLE, font=theme.number_font(44))
        self.openness_value.setMinimumWidth(130)
        self.openness_value.setAccessibleName("Personal eye openness, both eyes")
        readout.addWidget(self.openness_value, 0, Qt.AlignmentFlag.AlignVCenter)
        readout.addWidget(label("Relative to your calibrated open and closed positions. "
                                "Not a fatigue score and not a literal anatomical percentage.",
                                "secondary", theme.ui_font(14), wrap=True), 1, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(readout)
        self.graph = OpennessGraph()
        layout.addWidget(self.graph)
        layout.addWidget(self._legend())

        # --- last 60 seconds
        layout.addWidget(rule())
        window_heading = QHBoxLayout()
        window_heading.addWidget(label("Last 60 seconds", font=theme.ui_font(20, QFont.Weight.DemiBold)))
        window_heading.addStretch(1)
        self.window_caption = label("", "secondary", theme.ui_font(14))
        window_heading.addWidget(self.window_caption)
        layout.addLayout(window_heading)
        stats_row = QHBoxLayout()
        stats_row.setSpacing(0)
        self.stat_values = {}
        cells = (("rate", "Blink rate", "completed blinks per minute of valid observation"),
                 ("closure", "Median closure duration", "time between the detector’s closing and reopening "
                                                        "thresholds — not the whole blink movement"),
                 ("closed", "Time classified as closed", "share of valid observation in the detector’s closed state"))
        for i, (key, title, explain) in enumerate(cells):
            if i:
                stats_row.addWidget(vline())
            cell = QVBoxLayout()
            cell.setContentsMargins(0 if i == 0 else 22, 4, 22, 4)
            cell.setSpacing(4)
            cell.addWidget(label(title, font=theme.ui_font(14, QFont.Weight.Bold)))
            value = label(COLLECTING, font=theme.number_font(28))
            value.setAccessibleName(title)
            self.stat_values[key] = value
            cell.addWidget(value)
            cell.addWidget(label(explain, "secondary", theme.ui_font(12), wrap=True))
            holder = QWidget()
            holder.setLayout(cell)
            stats_row.addWidget(holder, 1)
        layout.addLayout(stats_row)
        self.precision_note = label("", "secondary", theme.ui_font(12), wrap=True)
        layout.addWidget(self.precision_note)

        details_row = QHBoxLayout()
        self.details_button = button("Show details", "quiet")
        self.details_button.setCheckable(True)
        self.details_button.toggled.connect(self._toggle_details)
        details_row.addWidget(self.details_button)
        details_row.addStretch(1)
        layout.addLayout(details_row)
        self.details = label("", font=theme.number_font(13), wrap=True)
        self.details.setTextFormat(Qt.TextFormat.RichText)
        self.details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.details.setVisible(False)
        layout.addWidget(self.details)
        layout.addStretch(1)

        # --- camera preview
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
        privacy.addWidget(label("Processed on this Mac. Images are never saved or uploaded.", "secondary", theme.ui_font(13)))
        footer.addLayout(privacy)
        footer.addStretch(1)
        layout.addLayout(footer)
        self.set_blinks(0)
        self.clear_measurements()

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

    def set_live_openness(self, obs: FrameObservation | None) -> None:
        """Both-eyes value only when both eyes are valid; otherwise "—" (never 0 %)."""
        value = combined_openness_percent(obs.left_raw, obs.right_raw) if obs and obs.valid else None
        self.openness_value.setText(_percent(value))

    def set_rolling(self, snap: RollingSnapshot | None) -> None:
        if snap is None:
            self.clear_measurements()
            return
        collecting = COLLECTING
        self.stat_values["rate"].setText(format_metric("rate", snap.blink_rate) if snap.enough_data else collecting)
        self.stat_values["closure"].setText(format_metric("closure", snap.median_closure))
        self.stat_values["closed"].setText(format_metric("closed", snap.closed_percent) if snap.enough_data else collecting)
        coverage = _percent(snap.coverage * 100) if snap.coverage is not None else UNAVAILABLE
        self.window_caption.setText(f"Valid observation {format_duration(snap.valid_seconds)} of "
                                    f"{format_duration(snap.running_seconds)} monitored · tracking coverage {coverage}")
        if snap.processing_rate:
            frame_ms = 1000 / snap.processing_rate
            self.precision_note.setText(
                f"Durations are timed between camera frames ({snap.processing_rate:.0f} per second), so they are "
                f"accurate to about ±{frame_ms:.0f} ms. Blink rate and closed time appear after "
                f"{MIN_VALID_SECONDS_FOR_RATE:.0f} s of valid observation (an MVP engineering choice).")

    def clear_measurements(self) -> None:
        self.openness_value.setText(UNAVAILABLE)
        for key, value in self.stat_values.items():
            value.setText(UNAVAILABLE if key == "closure" else COLLECTING)
        self.window_caption.setText("")
        self.precision_note.setText("")
        self.details.setText("")

    def set_details(self, obs: FrameObservation | None, snap: RollingSnapshot | None,
                    calibration: CalibrationInfo | None) -> None:
        """Developer view: raw values, data quality and the calibration in use."""
        def ear(value):
            return UNAVAILABLE if value is None else f"{value:.3f}"

        def raw(value):
            return UNAVAILABLE if value is None else f"{value * 100:.0f}% (shown {_percent(openness_percent(value))})"

        rows = []
        if obs:
            rows.append(f"EAR left {ear(obs.left_ear)} · right {ear(obs.right_ear)}")
            rows.append(f"Unclamped openness left {raw(obs.left_raw)} · right {raw(obs.right_raw)}")
            rows.append(f"Frame valid: {'yes' if obs.valid else 'no'} · detector closed: {'yes' if obs.detector_closed else 'no'}")
        if snap:
            rate = f"{snap.processing_rate:.1f} frames/s" if snap.processing_rate else UNAVAILABLE
            rows.append(f"Processing rate {rate} · valid observation {snap.valid_seconds:.1f} s · "
                        f"monitored {snap.running_seconds:.1f} s · coverage {_percent(snap.coverage * 100) if snap.coverage is not None else UNAVAILABLE}")
            rows.append(f"Window: {snap.blinks} blinks · {snap.closure_count} timed closures · "
                        f"closed {snap.closed_seconds:.2f} s")
        if calibration:
            rows.append(f"Calibration {calibration.calibrated_at:%H:%M:%S} · left open {calibration.left_open_ear:.3f} / "
                        f"closed {calibration.left_closed_ear:.3f} · right open {calibration.right_open_ear:.3f} / "
                        f"closed {calibration.right_closed_ear:.3f}")
            rows.append(f"Thresholds close &lt; {calibration.close_below:.0%} · reopen &gt; {calibration.reopen_above:.0%} · "
                        f"{calibration.measurement_version}")
        self.details.setText("<br>".join(rows))

    def _toggle_details(self, on: bool) -> None:
        self.details.setVisible(on)
        self.details_button.setText("Hide details" if on else "Show details")

    def set_preview(self, pixmap: QPixmap) -> None:
        self.preview.setPixmap(scaled_preview(pixmap, self.preview))

    def clear_preview(self) -> None:
        self.preview.clear()

    def _legend(self) -> QWidget:
        legend = QWidget()
        row = QHBoxLayout(legend)
        row.setContentsMargins(OpennessGraph.LEFT, 0, 0, 0)
        row.setSpacing(24)
        for kind, text in (("line", "Both eyes (last 10 s)"), ("dash", "Detector thresholds"), ("dot", "Blink counted")):
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
