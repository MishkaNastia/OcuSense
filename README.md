# OcuSense

Live webcam blink counter using OpenCV, Google MediaPipe Face Landmarker
(to locate eyelid points) and the Eye Aspect Ratio (EAR) with personal
calibration. All video is processed locally in memory: nothing is recorded
or uploaded.

## Setup (once)

```
cd ~/Projects/OcuSense
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python download_model.py
```

## Run the desktop app (PySide6)

```
source .venv/bin/activate
python -m ocusense
```

Press **Start**. The first session begins with a 30-second calibration; after
that you see the timer, Pause / Stop / Recalibrate and the live eye-openness
graph. Pause turns the camera off; Stop ends the session (calibration is kept).
**Statistics** (header tab) shows today / this week / this month: study time,
sessions, tracking coverage, a timeline with blink rate, median closure duration
or time classified as closed, and recent sessions. For now sessions are kept in
memory only and forgotten when the app quits. To preview the page with clearly
labelled demo sessions: `python -m ocusense --demo-history`.
⌘. also stops. Tab moves between buttons.

## Build OcuSense.app (macOS)

```
.venv/bin/pip install -r requirements-build.txt
./packaging/build_mac.sh
```

The app appears in `dist/OcuSense.app` (about 380 MB). It is signed only for
your own Mac (ad-hoc). Sharing it with others needs an Apple Developer ID and
notarisation. The first time it opens the camera, macOS asks for permission
for OcuSense itself.

## Run the OpenCV prototype

```
source .venv/bin/activate
python -m prototype
```

In the video window:
- **SPACE** (or **C**): start / redo the ~30-second personal calibration
  (eyes open → eyes gently closed → a few natural blinks)
- **M**: show / hide the face mesh (grey), outlines (blue) and the 12 EAR points (red)
- **Q**: quit

Blinks are only counted after a successful calibration.

## How it works

1. MediaPipe finds 6 points around each eye; we compute each eye's EAR
   (eye height ÷ width) in pixel coordinates (`ocusense/core/eye_metrics.py`).
2. Calibration stores *your* open and closed EAR for each eye (median of
   many frames) and rejects calibrations that are unclear or unstable
   (`ocusense/core/calibration.py`).
3. Each eye's EAR becomes **personal eye openness**: 1 = as open as in
   calibration, 0 = as closed. The two eyes are averaged.
4. A blink is counted once per open → closed (below 0.35) → open
   (above 0.65) sequence (`ocusense/core/blink_counter.py`). Measurement pauses when the
   face is lost, too small or turned away.
5. The OpenCV prototype also shows each eye separately: its openness, EAR,
   calibration references and its own blink count. Per-eye counts also
   include one-eyed winks; the main "Blinks" count needs both eyes.
6. A live graph at the bottom shows the last 10 seconds of personal eye
   openness and a mark for each counted blink (`ocusense/core/history.py`;
   drawn by `ocusense/ui/widgets/openness_graph.py`). It is kept in memory only.

Personal eye openness is relative to your own calibration only. It is not
a fatigue or health measure, and accuracy has not been established for
everyone - see [EVALUATION_CHECKLIST.md](EVALUATION_CHECKLIST.md).

## Project structure

```
ocusense/
  config.py            documented defaults (thresholds, limits, camera, file paths)
  core/                pure calculations — no PySide6, camera or MediaPipe
    eye_metrics.py     EAR from eyelid points, tracking-quality checks
    calibration.py     personal open/closed references, validation, personal openness
    blink_counter.py   the blink rule (open → closed → open)
    history.py         last 10 s of openness for the live graph
    session.py         per-session recording: blink rate, closure times, gaps
    models.py          shared data structures (SessionSummary, MinuteBin)
    stats.py           Statistics maths: periods, weighted averages, display units
  monitoring/          camera + MediaPipe
    pipeline.py        one camera frame → structured results (EyeMonitor)
    camera_worker.py   background thread; sends results to the interface
  storage.py           where session summaries are kept (memory now, file later)
  demo_data.py         labelled demo sessions for --demo-history
  ui/                  PySide6 interface — displays results, relays actions
    app.py             start-up, error dialogs, --self-test
    main_window.py     header, navigation, session life cycle
    study_page.py      study screen
    calibration_view.py guided calibration screen
    statistics_page.py "Your patterns"
    theme.py           colours, fonts, style sheet
    widgets/           drawing-only pieces (graph, chart, artwork, status)
prototype/             original OpenCV window (python -m prototype)
packaging/             Mac build script, PyInstaller recipe, icon generator
tests/                 one test file per area, plus structure guards
models/                MediaPipe face model (python download_model.py)
```

**Where future work goes**

- **New measurement or formula** (e.g. a new eye metric): `ocusense/core/` —
  one function, with tests. Per-session versions go in `core/session.py`;
  period summaries in `core/stats.py`. Store internal values in seconds and
  convert only for display (`stats.to_display`).
- **New default or threshold**: `ocusense/config.py`, with a comment and unit.
  A person's own calibration data is *not* config.
- **Feedback rules** (break reminders, pattern check-ins): a new pure module in
  `ocusense/core/` that takes session numbers and returns a decision; the
  interface only shows it.
- **Saving history**: replace `SessionStore` in `ocusense/storage.py`.
- **Interface changes**: the page in `ocusense/ui/`; reusable drawing in
  `ui/widgets/`; colours and fonts in `ui/theme.py`. Interface code never
  recalculates EAR or blinks — `tests/test_structure.py` checks this.
- **Files used at runtime** (models, fonts, images): load them with
  `config.resource_path(...)` so they work in development and in OcuSense.app,
  and add them to `packaging/OcuSense.spec`.

## Tests

```
python -m unittest
```

Runs every test in `tests/` (no camera needed; the window is tested offscreen).
