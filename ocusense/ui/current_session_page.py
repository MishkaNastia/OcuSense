"""Statistics › Current session: the running (or paused) session, from the live recorder.

Every number comes from SessionRecorder.summary() (the same data the All time page
uses once the session ends). Unavailable values read "not yet", never 0. The comparison
with the saved reference comes from core/baseline_drift.LiveDrift.
"""

import math

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from ocusense.core.baseline_drift import NOT_ENOUGH_DATA, TESTED, LiveDrift
from ocusense.config import LID_RECALIBRATE_DEGREES, POSTURE_CALIBRATION_SECONDS, POSTURE_SUSTAIN_SECONDS
from ocusense.core.models import SessionSummary
from ocusense.core.posture import PostureCalibration
from ocusense.reference import MIN_REFERENCE_INTERVALS
from ocusense.core.stats import METRICS, format_duration, format_metric

from . import theme
from .distributions_panel import DistributionsPanel
from .widgets.artwork import Composition
from .widgets.common import label, rule, vline
from .widgets.openness_graph import OpennessGraph
from .widgets.page import Page, paragraph
from .widgets.status_indicator import StatusIndicator

UNAVAILABLE = "not yet"


def _value(key: str, value) -> str:
    return UNAVAILABLE if value is None else format_metric(key, value)


def value_row(cells) -> tuple[QWidget, dict]:
    """A row of (key, title, explanation) cells with large values; returns the row and the value labels."""
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    values = {}
    for i, (key, title, explain) in enumerate(cells):
        if i:
            layout.addWidget(vline())
        cell = QWidget()
        col = QVBoxLayout(cell)
        col.setContentsMargins(0 if i == 0 else 22, 14, 22, 14)
        col.setSpacing(4)
        col.addWidget(label(title, font=theme.ui_font(14, QFont.Weight.Bold)))
        value = label(UNAVAILABLE, font=theme.number_font(30))
        value.setAccessibleName(title)
        values[key] = value
        col.addWidget(value)
        if explain:
            col.addWidget(label(explain, "secondary", theme.ui_font(12), wrap=True))
        col.addStretch(1)
        layout.addWidget(cell, 1)
    return row, values


class CurrentSessionPage(Page):
    go_to_study = Signal()
    calibrate_posture = Signal()

    def __init__(self, parent=None):
        super().__init__("Statistics", "Current session",
                         "The session you are running now, measured relative to your own calibration.", parent)

        # Empty state: no session
        self.empty = QWidget()
        empty = QHBoxLayout(self.empty)
        empty.setContentsMargins(0, 8, 0, 8)
        empty.setSpacing(36)
        empty.addWidget(Composition(), 0, Qt.AlignmentFlag.AlignTop)
        text = QVBoxLayout()
        text.addWidget(label("No session running right now.", font=theme.ui_font(26, QFont.Weight.Bold), wrap=True))
        text.addWidget(paragraph("Start one on the Study page and its numbers show up here live. Like a "
                                 "scoreboard, but for your eyes.", 16, secondary=True))
        go = QPushButton("Go to Study")
        go.setProperty("kind", "primary")
        go.clicked.connect(self.go_to_study.emit)
        text.addWidget(go, 0, Qt.AlignmentFlag.AlignLeft)
        text.addStretch(1)
        empty.addLayout(text, 1)
        self.body.addWidget(self.empty)

        # Session content
        self.content = QWidget()
        body = QVBoxLayout(self.content)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(12)
        body.addWidget(rule())
        row, self.time_values = value_row((
            ("duration", "Study time", "running time, pauses excluded"),
            ("coverage", "Tracking coverage", "share of study time with both eyes measured"),
            ("blinks", "Blinks counted", "completed blinks this session"),
        ))
        body.addWidget(row)
        body.addWidget(rule(1, "hairline"))

        self.section("Eye measurements · whole session so far", body)
        row, self.metric_values = value_row(tuple(
            (key, METRICS[key]["name"], METRICS[key]["explain"]) for key in ("rate", "closure", "closed")))
        body.addWidget(row)
        body.addWidget(label("Averaged over all tracked time in this session. The Study page shows the last 60 seconds.",
                             "secondary", theme.ui_font(13), wrap=True))

        self.section("Personal eye openness", body)
        self.graph_caption = label("", "secondary", theme.ui_font(14))
        body.addWidget(self.graph_caption)
        self.graph = OpennessGraph()
        body.addWidget(self.graph)
        body.addWidget(label("Compared with your own open and closed eyes. Not a tiredness score.",
                             "secondary", theme.ui_font(13), wrap=True))

        self.section("Posture", body)
        posture_row = QHBoxLayout()
        posture_row.setSpacing(16)
        self.posture_indicator = StatusIndicator()
        self.posture_indicator.set("paused", "Posture monitoring is off")
        posture_row.addWidget(self.posture_indicator, 1)
        self.posture_button = QPushButton("Recalibrate posture")
        self.posture_button.setProperty("kind", "secondary")
        self.posture_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.posture_button.clicked.connect(self.calibrate_posture.emit)
        posture_row.addWidget(self.posture_button, 0, Qt.AlignmentFlag.AlignTop)
        body.addLayout(posture_row)
        minutes = POSTURE_CALIBRATION_SECONDS / 60
        self.posture_off_text = "Turn it on in Settings › Monitoring › Posture monitoring."
        self.posture_on_text = (f"After each eye calibration, the first {minutes:.0f} minutes of work become your "
                                    "posture baseline: sit the way you want to, at a good distance from the screen. "
                                "Moved your chair or desk? Press Recalibrate posture.")
        self.posture_detail = label(self.posture_off_text, "secondary", theme.ui_font(14), wrap=True)
        body.addWidget(self.posture_detail)
        self.set_posture_enabled(False)
        body.addWidget(label("Head angle, distance (estimated from your iris, so approximate) and how low your face "
                             "sits in the picture. A limit must be exceeded for "
                             f"{POSTURE_SUSTAIN_SECONDS:.0f} seconds in a row to count, so "
                             "glancing away doesn't. On MacBooks that report the screen angle, small screen tilts "
                             f"are corrected and a tilt of {LID_RECALIBRATE_DEGREES:.0f}° or more records a new "
                             "baseline. Shown live only and never saved. Not a health assessment.",
                             "secondary", theme.ui_font(13), wrap=True))

        self.section("Blink distributions", body)
        body.addWidget(label("How your blinks vary in this session. It describes, it doesn’t judge, and it’s not a "
                             "tiredness test. Updates every few seconds.", "secondary", theme.ui_font(14), wrap=True))
        self.distributions = DistributionsPanel()
        body.addWidget(self.distributions)

        self.section("Compared with your reference", body)
        body.addWidget(label("Are the gaps between your blinks still like in your reference (the first 10 "
                             "minutes of one session, saved in Settings › Data & privacy)? Every 30 seconds "
                             "the last 5 minutes are compared with it (likelihood-ratio test on log-normal fits); 3 windows in a "
                             "row below p = 0.01 count as different. "
                             "A statistical comparison of timing, not a fatigue assessment.",
                             "secondary", theme.ui_font(14), wrap=True))
        self.drift_baseline = paragraph("")
        self.drift_latest = paragraph("")
        self.drift_counts = label("", "secondary", theme.ui_font(13), wrap=True)
        for widget in (self.drift_baseline, self.drift_latest, self.drift_counts):
            body.addWidget(widget)

        self.body.addWidget(self.content)
        self.finish()
        self.show_session(None)

    def show_session(self, summary: SessionSummary | None, paused: bool = False) -> None:
        has = summary is not None
        self.empty.setVisible(not has)
        self.content.setVisible(has)
        self.set_tag(("Paused" if paused else "In progress") if has else "")
        if not has:
            self.graph.clear()
            return
        self.time_values["duration"].setText(format_duration(summary.study_seconds))
        coverage = summary.coverage
        self.time_values["coverage"].setText(UNAVAILABLE if coverage is None else f"{coverage * 100:.0f}%")
        self.time_values["blinks"].setText(str(summary.blinks))
        for key, value in self.metric_values.items():
            value.setText(_value(key, summary.metric(key)))

    def show_drift(self, drift: LiveDrift, interval_pairs, now: float, reference=None, error: str = "") -> None:
        """reference: the saved ocusense.reference.Reference (None if there is none yet)."""
        if drift.fixed:
            self.drift_baseline.setText(f"Reference: session of {reference.label()} · {reference.n} intervals · "
                                        f"median {reference.median:.1f} s between blinks."
                                        if reference else "Compared with the reference saved when this session began.")
        elif drift.baseline is None:
            seconds, n = drift.collecting(interval_pairs, now)
            first = "" if reference or error else "No reference yet: this session's first 10 minutes will become it. "
            self.drift_baseline.setText(f"{first}Collecting: {format_duration(seconds)} of "
                                        f"{format_duration(drift.baseline_seconds)} · {n} intervals so far.")
            self.drift_latest.setText("The first comparison appears 10 minutes into the session.")
            self.drift_counts.setText("")
            return
        else:
            fit = drift.baseline_fit
            if fit is None or fit.sigma == 0:
                n = fit.n if fit else len(drift.baseline)
                self.drift_baseline.setText(f"Too few intervals to compare with: {n} in the first 10 minutes "
                                            "(tracking may have been poor). The next session tries again.")
                self.drift_latest.setText("")
                self.drift_counts.setText("")
                return
            if reference is not None and reference.n == fit.n and abs(reference.mu - fit.mu) < 1e-9:
                saved = "saved as your reference"
            elif error:
                saved = f"not saved ({error})"
            elif reference is not None:
                saved = "not saved: a reference already exists"
            else:
                saved = f"not saved as your reference: at least {MIN_REFERENCE_INTERVALS} intervals are needed"
            self.drift_baseline.setText(f"This session's first 10 min: {fit.n} intervals · median "
                                        f"{math.exp(fit.mu):.1f} s between blinks, {saved}.")
        results = drift.results
        if not results:
            self.drift_latest.setText("The first comparison appears 5 minutes into the session." if drift.fixed
                                      else "Waiting for the first window.")
            self.drift_counts.setText("")
            return
        w = results[-1]
        minutes = f"{(w.start - drift.start) / 60:.1f} to {(w.end - drift.start) / 60:.1f} min"
        if w.status == NOT_ENOUGH_DATA:
            text = (f"Latest window ({minutes}): not enough data yet, {w.n} intervals and at least "
                    f"{drift.min_intervals} needed.")
        elif w.status != TESTED:
            text = f"Latest window ({minutes}): not tested ({w.status})."
        else:
            compared = "the reference" if drift.fixed else "the first 10 minutes"
            if w.confirmed:
                verdict = f"different from {compared}: {w.run} windows in a row below p = {drift.alpha:g}"
            elif w.different:
                verdict = (f"below p = {drift.alpha:g}, not confirmed yet ({w.run} of {drift.confirm_windows} "
                           "in a row needed)")
            else:
                verdict = f"similar to {compared}"
            text = (f"Latest window ({minutes}): {w.n} intervals · median {math.exp(w.fit.mu):.1f} s · "
                    f"p = {w.p:.2g}, so {verdict}.")
        if w.overlaps_baseline:
            text += " This window overlaps the first 10 minutes it is compared with."
        self.drift_latest.setText(text)
        tested = sum(r.status == TESTED for r in results)
        below = sum(r.different for r in results)
        confirmed = sum(r.confirmed for r in results)
        skipped = sum(r.status == NOT_ENOUGH_DATA for r in results)
        self.drift_counts.setText(f"{len(results)} windows so far: {tested} tested, {below} below p = "
                                  f"{drift.alpha:g}, {confirmed} confirmed ({drift.confirm_windows} in a row), "
                                  f"{skipped} with not enough data. A single window below the line happens by "
                                  f"chance now and then, so only {drift.confirm_windows} in a row count as "
                                  "different.")

    def set_posture_enabled(self, enabled: bool) -> None:
        """Ticked or not in Settings: the section explains itself when off."""
        self.posture_button.setEnabled(enabled)
        if not enabled:
            self.posture_indicator.set("paused", "Posture monitoring is off")
            self.posture_detail.setText(self.posture_off_text)
        elif self.posture_indicator.text.text() == "Posture monitoring is off":
            self.posture_indicator.set("ready", "Waiting for a posture baseline")
            self.posture_detail.setText(self.posture_on_text)

    def show_posture(self, update) -> None:
        """update: the window's MonitorUpdate. Only shows what core/posture.py worked out."""
        if not update.posture_enabled:
            return
        if update.posture_cal_status == PostureCalibration.RUNNING:
            minutes, seconds = divmod(int(round(update.posture_cal_seconds_left)), 60)
            self.posture_indicator.set("calibrating", f"Recording your posture: {minutes}:{seconds:02d} left")
            self.posture_detail.setText("Keep working, sitting the way you want to, at a good distance from the "
                                        "screen. Posture isn't judged until this is done.")
            return
        if update.posture_cal_status == PostureCalibration.FAILED and update.posture_status is None:
            self.posture_indicator.set("paused", "Posture calibration failed")
            self.posture_detail.setText(update.posture_cal_error)
            return
        status = update.posture_status
        if status is None:
            return  # not calibrated yet: keep the instructions
        if not status.tracked:
            self.posture_indicator.set("paused", "Face not tracked")
            self.posture_detail.setText("Posture is checked again when your face is back in the picture.")
            return
        if status.poor:
            self.posture_indicator.set("warning", "Poor posture: " + ", ".join(status.problems))
        elif status.outside:
            self.posture_indicator.set("monitoring", f"Good · {', '.join(status.outside)} for "
                                                     f"{status.longest_outside:.0f} s")
        else:
            self.posture_indicator.set("monitoring", "Good posture")
        parts = [f"head {abs(status.pitch_change):.0f}° {'lower' if status.pitch_change > 0 else 'higher'}"]
        if status.roll_change is not None:
            parts.append(f"tilted {abs(status.roll_change):.0f}°")
        if status.distance_cm is not None:
            parts.append(f"about {status.distance_cm:.0f} cm away (calibrated {status.baseline_distance_cm:.0f} cm)")
        parts.append(f"face {abs(status.centre_drop) * 100:.0f} % of the picture "
                     f"{'lower' if status.centre_drop > 0 else 'higher'}")
        if status.lid_change:
            parts.append(f"screen tilted {abs(status.lid_change):.0f}° {'back' if status.lid_change > 0 else 'forward'}"
                         " (corrected)")
        self.posture_detail.setText("Compared with your posture baseline: " + " · ".join(parts) + ".")

    def show_distributions(self, data, thresholds, context: dict) -> None:
        self.distributions.show_data(data, "Distributions appear once tracking has started.", thresholds, context,
                                     "Current session")

    def set_graph(self, samples, now, dimmed: bool = False, caption: str = "") -> None:
        self.graph.set_data(samples, now, dimmed=dimmed)
        self.graph_caption.setText(caption)
