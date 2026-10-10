"""Statistics › All time › "Blink distributions from recordings".

Recordings are not linked to the session history (that lives in memory only),
so nothing is guessed: the person imports ear_*.csv files with "Import
recording…". Reading and analysing runs on a background thread; widgets are only
updated here, on the interface thread, when the result arrives. Original files
are only read, never changed.
"""

from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QComboBox, QFileDialog, QHBoxLayout, QPushButton, QSlider, QVBoxLayout, QWidget

from ocusense.recording import default_directory
from ocusense.recording_files import ImportResult, import_recordings

from . import theme
from .distributions_panel import DistributionsPanel
from .widgets.common import label, rule
from .widgets.detection_timeline import DetectionTimeline
from .widgets.segmented import Segmented

SPANS = (("10", "10 s"), ("30", "30 s"), ("60", "60 s"))


class ImportWorker(QThread):
    """Reads and analyses the chosen files away from the interface thread."""
    done = Signal(object)  # ImportResult
    failed = Signal(str)

    def __init__(self, paths, parent=None):
        super().__init__(parent)
        self.paths = list(paths)

    def run(self) -> None:
        try:
            self.done.emit(import_recordings(self.paths))
        except Exception as error:  # an unexpected problem must not take the app down
            self.failed.emit(f"{type(error).__name__}: {error}")


def _button(text: str, kind: str) -> QPushButton:
    widget = QPushButton(text)
    widget.setProperty("kind", kind)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    return widget


class RecordingsSection(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.recordings = []  # imported Recording objects
        self.excluded: list[tuple[str, str]] = []
        self.worker: ImportWorker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(label("Blink distributions from recordings", font=theme.ui_font(28, QFont.Weight.Bold)))
        layout.addWidget(rule())
        layout.addWidget(label(
            "Import EAR recordings saved by OcuSense (ear_….csv with its .calibration.json). Each recording is "
            "analysed with its own saved calibration and thresholds; the original files are never changed. "
            "Files are joined only when they continue each other without a gap and share one calibration.",
            "secondary", theme.ui_font(14), wrap=True))

        row = QHBoxLayout()
        self.import_button = _button("Import recording…", "secondary")
        self.import_button.clicked.connect(self._choose_files)
        row.addWidget(self.import_button)
        self.choice = QComboBox()
        self.choice.setAccessibleName("Imported recording")
        self.choice.setMinimumWidth(320)
        self.choice.currentIndexChanged.connect(self._show_selected)
        row.addWidget(self.choice, 1)
        layout.addLayout(row)
        self.status = label("", "secondary", theme.ui_font(13), wrap=True)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.status)
        self.calibration_label = label("", font=theme.ui_font(13, QFont.Weight.DemiBold), wrap=True)
        layout.addWidget(self.calibration_label)

        self.panel = DistributionsPanel()
        layout.addWidget(self.panel)

        # Inspect detection (collapsed by default)
        self.inspect_button = _button("Inspect detection", "quiet")
        self.inspect_button.setCheckable(True)
        self.inspect_button.toggled.connect(self._toggle_inspect)
        layout.addWidget(self.inspect_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.inspect = QWidget()
        inspect = QVBoxLayout(self.inspect)
        inspect.setContentsMargins(0, 0, 0, 0)
        inspect.addWidget(label(
            "Check the detection before reading the histograms. Cobalt: left eye · graphite: right eye · thin ink: "
            "what the detector used (mean of both, clipped) · dashed: recorded thresholds · pale bands: timed "
            "closures · red dots: counted blinks · hatched: no valid tracking.", "secondary", theme.ui_font(13),
            wrap=True))
        controls = QHBoxLayout()
        self.span_switch = Segmented(SPANS, "30", "Time shown")
        self.span_switch.changed.connect(lambda _key: self._update_range())
        controls.addWidget(self.span_switch)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setAccessibleName("Start of the time shown, in seconds")
        self.slider.valueChanged.connect(lambda _v: self._update_range())
        controls.addWidget(self.slider, 1)
        self.range_label = label("", "secondary", theme.ui_font(13))
        controls.addWidget(self.range_label)
        inspect.addLayout(controls)
        self.timeline = DetectionTimeline()
        inspect.addWidget(self.timeline)
        self.inspect.setVisible(False)
        layout.addWidget(self.inspect)
        self._show_selected()

    # ----------------------------------------------------------- import
    def _choose_files(self) -> None:
        folder = default_directory()
        paths, _ = QFileDialog.getOpenFileNames(self, "Import OcuSense recordings",
                                                str(folder if folder.exists() else Path.home()),
                                                "OcuSense recordings (ear_*.csv)")
        if paths:
            self.import_files([Path(p) for p in paths])

    def import_files(self, paths: list[Path]) -> None:
        if self.worker is not None:
            return  # one import at a time
        self.import_button.setEnabled(False)
        self.status.setText(f"Loading {len(paths)} file{'s' if len(paths) != 1 else ''}…")
        self.worker = ImportWorker(paths, self)
        self.worker.done.connect(self._imported)
        self.worker.failed.connect(self._failed)
        self.worker.finished.connect(self._worker_finished)
        self.worker.start()

    def _worker_finished(self) -> None:
        self.worker = None
        self.import_button.setEnabled(True)

    def _failed(self, message: str) -> None:
        self.status.setText(f"The import failed: {message}")

    def _imported(self, result: ImportResult) -> None:
        known = {f.csv_path for r in self.recordings for f in r.files}
        new = [r for r in result.recordings if not any(f.csv_path in known for f in r.files)]
        self.recordings.extend(new)
        self.excluded = result.excluded
        self.choice.blockSignals(True)
        self.choice.clear()
        for recording in self.recordings:
            self.choice.addItem(recording.label())
        self.choice.blockSignals(False)
        if new:
            self.choice.setCurrentIndex(self.recordings.index(new[-1]))
        parts = [f"Imported {len(new)} recording{'s' if len(new) != 1 else ''}."]
        if self.excluded:
            parts.append("Not analysed: " + " ".join(f"{name} — {reason}" for name, reason in self.excluded))
        self.status.setText(" ".join(parts))
        self._show_selected()

    # ----------------------------------------------------------- display
    def selected(self):
        i = self.choice.currentIndex()
        return self.recordings[i] if 0 <= i < len(self.recordings) else None

    def _show_selected(self, *_args) -> None:
        recording = self.selected()
        self.choice.setVisible(bool(self.recordings))
        self.inspect_button.setEnabled(recording is not None)
        if recording is None:
            self.calibration_label.setText("")
            self.panel.show_data(None, "No recording imported yet. Use “Import recording…” to choose ear_….csv "
                                       "files (Settings › Data & privacy › Show in Finder shows where they are).")
            self.timeline.set_data(None, [], (0.35, 0.65))
            return
        result = recording.replay_result
        cal = recording.calibration
        d = result.distributions
        mismatch = (f" · {result.stored_mismatches} rows where the stored openness differs from the recomputed one"
                    if result.stored_mismatches else "")
        self.calibration_label.setText(
            f"Calibration: {cal.label()} · {result.valid_frames} of {result.frames} frames valid{mismatch}")
        context = {
            "source": {"type": "imported recording", "files": [f.csv_path.name for f in recording.files],
                       "started": recording.started.isoformat(timespec="seconds")},
            "calibration": asdict(cal),
            "exclusions": {"interrupted_events": d.interrupted, "excluded_windows": d.excluded_windows(),
                           "files_not_analysed": [{"file": n, "reason": r} for n, r in self.excluded],
                           "frames": result.frames, "valid_frames": result.valid_frames,
                           "stored_openness_mismatches": result.stored_mismatches},
        }
        empty = "This recording has no valid tracking with its calibration." if not d.valid_seconds else ""
        self.panel.show_data(d if d.valid_seconds else None, empty, (cal.close_below, cal.reopen_above), context,
                             f"Recording {recording.label()}")
        self.timeline.set_data(result.timeline, d.events, (cal.close_below, cal.reopen_above))
        self._update_range()

    def _toggle_inspect(self, on: bool) -> None:
        self.inspect.setVisible(on)
        self.inspect_button.setText("Hide detection check" if on else "Inspect detection")

    def _update_range(self) -> None:
        recording = self.selected()
        span = float(self.span_switch.current())
        length = recording.seconds if recording else 0.0
        self.slider.blockSignals(True)
        self.slider.setRange(0, max(0, int(length - span)))
        self.slider.blockSignals(False)
        start = float(self.slider.value())
        self.timeline.set_range(start, span)
        self.range_label.setText(f"{start:.0f}–{start + span:.0f} s of {length:.0f} s" if recording else "")
