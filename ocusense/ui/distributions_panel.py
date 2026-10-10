"""The "Blink distributions" panel: one histogram at a time, chosen with a selector.

Shared by Statistics › Current session (live) and Statistics › All time (imported
recordings). It only displays: every number comes from core.distributions. It
never shows demo data and never invents values: with too little data it says so.
"""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from ocusense.config import MIN_VALID_SECONDS_FOR_RATE
from ocusense.core.distributions import (
    CLOSURE_BINS, INTERVAL_BINS, OPENNESS_BINS, RATE_BINS, WINDOW_SECONDS, Distributions, histogram, quartiles,
)
from ocusense.exports import export_analysis

from . import theme
from .widgets.common import label
from .widgets.histogram import Histogram
from .widgets.segmented import Segmented

SMALL_SAMPLE = 10  # fewer events than this: the histogram is shown, with a small-sample note
MIN_WINDOWS = 3  # fewer eligible windows than this: no rate histogram, a message instead

METRICS = (("closure", "Closure duration"), ("interval", "Time between blinks"),
           ("rate", "Blink rate per minute"), ("openness", "Personal eye openness"))
EYES = (("left", "Left eye"), ("right", "Right eye"), ("both", "Both eyes"))

EXPLAIN = {
    "closure": "Time between the detector’s closing and reopening thresholds — not the full blink movement. "
               "Measured from frame time stamps, so each value is only as precise as the time between frames "
               "(about ±33 ms at 30 frames per second).",
    "interval": "Time from the start of one completed blink to the start of the next, counted only within "
                "uninterrupted tracking — never across a gap, pause or recalibration.",
    "rate": f"Completed blinks per minute of valid tracking, in separate {WINDOW_SECONDS:.0f}-second windows. "
            f"A window counts only if it is finished and has at least {MIN_VALID_SECONDS_FOR_RATE:.0f} s of valid "
            "tracking.",
    "openness": "Relative to your calibrated eye positions. Not a fatigue score or literal percentage of "
                "anatomical eye opening. Bars show the share of valid observed time, weighted by time between "
                "frames, so a varying frame rate doesn’t distort them.",
}


def _iqr_text(values: list[float], unit: str, decimals: int) -> str:
    q = quartiles(values)
    if q is None:
        return ""
    fmt = f"{{:.{decimals}f}}"
    sep = "" if unit == "%" else " "
    return (f"median {fmt.format(q[1])}{sep}{unit} · interquartile range "
            f"{fmt.format(q[0])}–{fmt.format(q[2])}{sep}{unit}")


class DistributionsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.metric, self.eye = "closure", "left"
        self.data: Distributions | None = None
        self.thresholds: tuple[float, float] | None = None  # (close_below, reopen_above) as fractions
        self.context: dict = {}
        self.title = ""
        self.empty_text = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.metric_switch = Segmented(METRICS, self.metric, "Distribution")
        self.metric_switch.changed.connect(self._set_metric)
        layout.addWidget(self.metric_switch, 0, Qt.AlignmentFlag.AlignLeft)
        self.eye_switch = Segmented(EYES, self.eye, "Eye")
        self.eye_switch.changed.connect(self._set_eye)
        layout.addWidget(self.eye_switch, 0, Qt.AlignmentFlag.AlignLeft)
        self.summary = label("", font=theme.ui_font(15, QFont.Weight.DemiBold), wrap=True)
        layout.addWidget(self.summary)
        self.note = label("", "secondary", theme.ui_font(13), wrap=True)
        layout.addWidget(self.note)
        self.chart = Histogram()
        layout.addWidget(self.chart)
        self.explain = label("", "secondary", theme.ui_font(13), wrap=True)
        layout.addWidget(self.explain)
        actions = QHBoxLayout()
        self.export_button = QPushButton("Export results…")
        self.export_button.setProperty("kind", "quiet")
        self.export_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_button.clicked.connect(self._export)
        actions.addWidget(self.export_button)
        self.export_status = label("", "secondary", theme.ui_font(13), wrap=True)
        actions.addWidget(self.export_status, 1)
        layout.addLayout(actions)
        self.show_data(None, "")

    # ----------------------------------------------------------- input
    def show_data(self, data: Distributions | None, empty_text: str, thresholds=None, context=None,
                  title: str = "") -> None:
        """data: None shows empty_text. thresholds: (close_below, reopen_above) fractions from the calibration."""
        self.data, self.empty_text = data, empty_text
        self.thresholds = thresholds
        self.context = context or {}
        self.title = title
        self.render()

    def _set_metric(self, key: str) -> None:
        self.metric = key
        self.render()

    def _set_eye(self, key: str) -> None:
        self.eye = key
        self.render()

    # ----------------------------------------------------------- output
    def render(self) -> None:
        self.metric_switch.set_current(self.metric)
        self.eye_switch.set_current(self.eye)
        self.eye_switch.setVisible(self.metric == "openness")
        self.explain.setText(EXPLAIN[self.metric])
        d = self.data
        self.export_button.setEnabled(d is not None and d.valid_seconds > 0)
        if d is None:
            self.summary.setText("")
            self.note.setText("")
            self.chart.clear(self.empty_text)
            return
        getattr(self, f"_render_{self.metric}")(d)

    def _render_closure(self, d: Distributions) -> None:
        values = d.closure_ms()
        self._events(values, CLOSURE_BINS, "completed events", "events", 0,
                     f"{d.interrupted} interrupted event{'s' if d.interrupted != 1 else ''} excluded "
                     "(tracking lost, a gap or a pause before reopening). Closures of 1000 ms or longer are "
                     "kept in the last bar.")

    def _render_interval(self, d: Distributions) -> None:
        values = d.interval_seconds()
        self._events(values, INTERVAL_BINS, "intervals", "intervals", 2,
                     f"From {len(d.events)} completed blinks in {d.segments} uninterrupted "
                     f"tracking segment{'s' if d.segments != 1 else ''}. Intervals of 30 s or longer are "
                     "kept in the last bar.")

    def _events(self, values, binning, noun, short, decimals, note) -> None:
        unit = binning.unit
        if not values:
            self.summary.setText(f"No {noun} yet.")
            self.note.setText(note)
            self.chart.clear(f"No {noun} to show yet. They appear as completed blinks are detected.")
            return
        small = (f" Small sample (n = {len(values)}): the shape isn’t reliable yet."
                 if len(values) < SMALL_SAMPLE else "")
        self.summary.setText(f"{len(values)} {noun} · {_iqr_text(values, unit, decimals)}")
        self.note.setText(note + small)
        counts = histogram(values, binning)
        self.chart.set_data(counts, binning, f"number of {short}",
                            value_text=lambda c: f"{c:.0f} {short if c != 1 else short.rstrip('s')}")

    def _render_rate(self, d: Distributions) -> None:
        rates = d.eligible_rates()
        excluded = d.excluded_windows()
        in_progress = sum(1 for w in d.windows if not w.complete)
        status = (f"{len(rates)} eligible window{'s' if len(rates) != 1 else ''} · {excluded} excluded "
                  f"(under {MIN_VALID_SECONDS_FOR_RATE:.0f} s of valid tracking)"
                  + (" · 1 in progress" if in_progress else ""))
        self.note.setText(status)
        if len(rates) < MIN_WINDOWS:
            self.summary.setText("Not enough eligible minutes yet.")
            self.chart.clear(f"A blink-rate histogram needs at least {MIN_WINDOWS} eligible one-minute windows "
                             f"({len(rates)} so far). Each window needs {MIN_VALID_SECONDS_FOR_RATE:.0f} s of valid "
                             "tracking.")
            return
        self.summary.setText(f"{len(rates)} windows · {_iqr_text(rates, 'blinks/min', 1)}")
        self.chart.set_data(histogram(rates, RATE_BINS), RATE_BINS, "number of windows",
                            value_text=lambda c: f"{c:.0f} window{'s' if c != 1 else ''}")

    def _render_openness(self, d: Distributions) -> None:
        o = d.openness
        if not o.total:
            self.summary.setText("No valid observation yet.")
            self.note.setText("")
            self.chart.clear("Personal eye openness appears after a few seconds of valid tracking.")
            return
        shares = o.shares(self.eye)
        eye = dict(EYES)[self.eye].lower()
        below, above = shares[0], shares[-1]
        self.summary.setText(f"{eye.capitalize()} · {o.total:.0f} s of valid observed time")
        both = " Both eyes = mean of the two unclipped values, shown only when both eyes were valid." \
            if self.eye == "both" else ""
        markers = []
        if self.thresholds:
            close, reopen = self.thresholds
            markers = [(close * 100, f"closes {close:.0%}"), (reopen * 100, f"reopens {reopen:.0%}")]
            both += (" Dashed lines: the recorded detection thresholds; the detector applies them to the mean of "
                     "both eyes (each clipped to 0–100 %).")
        self.note.setText(f"Below 0 %: {below:.1f} % of the time · 100 % or above: {above:.1f} % of the time "
                          f"(range seen {o.lowest[self.eye]:.0f} % to {o.highest[self.eye]:.0f} %)." + both)
        self.chart.set_data(shares, OPENNESS_BINS, "% of valid observed time",
                            value_text=lambda c: f"{c:.1f} % of valid observed time", markers=markers)

    # ----------------------------------------------------------- export
    def _export(self) -> None:
        if self.data is None:
            return
        folder = QFileDialog.getExistingDirectory(self, "Choose a folder for the exported results")
        if not folder:
            return
        self.export_to(Path(folder))

    def export_to(self, folder: Path) -> Path | None:
        try:
            target = export_analysis(folder, self.title, self.data, self.context)
            self.chart.grab().save(str(target / "histogram.png"))
        except OSError as error:
            self.export_status.setText(f"Couldn’t export: {error.strerror or error}")
            return None
        self.export_status.setText(f"Exported to {target}")
        return target
