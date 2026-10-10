# OcuSense

Live webcam blink counter using OpenCV, Google MediaPipe Face Landmarker
(to locate eyelid points) and the Eye Aspect Ratio (EAR) with personal
calibration. All video is processed locally in memory: camera images are never
saved or uploaded. The only thing written to disk is the raw EAR recording (see
below).

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
The sidebar on the left switches pages without interrupting monitoring:

- **Study** — timer, controls, calibration and the live graph.
- **Statistics** (expands) — **Current session** (the running session's time,
  coverage and measurements), **All time** (totals, a date filter, a timeline
  with blink rate, median closure duration or time classified as closed, and
  each session's summary) and **Understanding your patterns** (what each
  measurement means; no personal findings until check-ins exist).
- **Settings** — recalibration, measurement details, and data & privacy
  (including clearing the session history).
- **Log in** — accounts aren't available in the app yet; it says so.

**Raw EAR recording.** While the camera is on, the app saves the left and right
Eye Aspect Ratio of every frame to CSV files in
`~/Library/Application Support/OcuSense/recordings/` — a new file every 10
minutes and whenever you pause, stop, quit or recalibrate. Columns:

- `unix_time` — seconds, millisecond precision
- `left_ear`, `right_ear` — raw EAR (empty when no face was found)
- `reliable` — 0 when the head was turned or the face too small; filter these out
- `left_openness`, `right_openness` — personal openness from the calibration in
  use, `(EAR − closed EAR) / (open EAR − closed EAR)`, not clipped; empty while
  not calibrated

Each `ear_….csv` has an `ear_….calibration.json` next to it with the calibration
those openness values used (open and closed EAR per eye, thresholds, time), so
every file can be re-analysed from the raw EAR. One calibration per file: a
recalibration starts a new one. Numbers only, no images. Settings › Data &
privacy can switch it off and open the folder. About 1 MB per 10 minutes at 30
frames per second.

**Blink distributions.** Statistics › Current session shows live histograms
(closure duration by default; also time between blinks, blink rate per minute
and personal eye openness). Statistics › All time › *Import recording…* analyses
saved `ear_….csv` files with their own `.calibration.json` (read-only), with an
*Inspect detection* timeline to check the detector and *Export results…* for
derived CSV/JSON/PNG files. Definitions, bins and exclusions are documented in
`ocusense/core/distributions.py`; descriptive only, not a fatigue assessment.

Statistics sessions are kept in memory only and forgotten when the app quits. To
preview Statistics with clearly labelled demo sessions:
`python -m ocusense --demo-history`.
⌘. also stops. Tab reaches the sidebar; ↑/↓ move between its items and →/←
open or close Statistics.

## Build OcuSense.app (macOS)

```
.venv/bin/pip install -r requirements-build.txt
./packaging/build_mac.sh
```

The script builds `dist/OcuSense.app` (about 380 MB), checks it, and replaces
`~/Desktop/OcuSense.app` (quit OcuSense first; use `--no-install` to skip that). It is signed only for
your own Mac (ad-hoc). Sharing it with others needs an Apple Developer ID and
notarisation. The first time it opens the camera, macOS asks for permission
for OcuSense itself.

## Website

The public website (information pages, a sample-session demo and a browser camera demo)
is in [`website/`](website/README.md). It is separate from the desktop app:

```bash
cd website && npm install && npm run dev   # open http://localhost:3000, Ctrl+C to stop
```

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

## Measurements (live study screen)

All durations use monotonic timestamps of camera frames (never frame counts)
and are only as precise as the frame interval (about ±33 ms at 30 frames/s).
Definitions live in `ocusense/core/measurements.py`; defaults in `ocusense/config.py`.

- **Personal eye openness (0–100 %, live)** — per eye:
  `100 × (EAR − closed reference) / (open reference − closed reference)`,
  using that eye's validated calibration. Shown clamped to 0–100 %; the
  unclamped value is kept for diagnostics. The both-eyes value is the mean of
  the two separately normalised eyes and is shown only when both are valid
  ("—" otherwise, never 0 %). Relative to your calibration: not a fatigue
  score or an anatomical percentage.
- **Valid observation** — time between consecutive valid frames at most
  `MAX_FRAME_GAP` (0.5 s) apart. Face lost, measurement paused, long frame
  gaps and pauses are excluded. Tracking coverage = valid ÷ monitored time.
- **Bilateral blink event** (unchanged detector) — both-eyes openness (mean
  of the two clipped eyes) falls below 35 % → *closing*; it later rises above
  65 % → *reopening* = one counted blink. Winks keep the mean around 50 % and
  are not counted. Losing tracking or pausing forgets a half-finished blink.
- **Blink rate (last 60 s)** — completed bilateral blinks ÷ valid observation
  seconds × 60. Shown after 30 s of valid observation ("Collecting data" before).
- **Median closure duration (last 60 s)** — median time from the closing to
  the reopening transition of completed events that finished in the window.
  This is the threshold-defined closed interval, not the whole blink movement.
  Events interrupted by tracking loss, a frame gap or a pause are discarded.
- **Time classified as closed (last 60 s)** — valid time spent in the
  detector's closed state ÷ valid observation × 100, including ongoing and
  long closures. Intervals crossing the window edge count only partly.
  Not PERCLOS: calibrated EAR thresholds don't measure anatomical closure.

**Engineering choices (not clinical standards):** the 30 s minimum before
showing rate/closed time, the 0.5 s frame-gap limit, the 60 s window, and the
35 %/65 % detector thresholds. `MEASUREMENT_VERSION` in `config.py` is stored
with each session so later analysis can tell settings apart.

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
    distributions.py   blink distributions: events, intervals, 60 s windows, histograms
    replay.py          replays a saved recording through the real calibration and detector
  monitoring/          camera + MediaPipe
    pipeline.py        one camera frame → structured results (EyeMonitor)
    camera_worker.py   background thread; sends results to the interface
  storage.py           where session summaries are kept (memory now, file later)
  recording.py         writes the raw EAR recording (CSV + calibration JSON)
  recording_files.py   reads and groups recordings for analysis (read-only)
  exports.py           writes derived analysis results to a chosen folder
  demo_data.py         labelled demo sessions for --demo-history
  ui/                  PySide6 interface — displays results, relays actions
    app.py             start-up, error dialogs, --self-test
    main_window.py     session life cycle; connects the sidebar and pages
    sidebar.py         vertical navigation and the monitoring status
    study_page.py      study screen
    calibration_view.py guided calibration screen
    current_session_page.py  Statistics › Current session
    all_time_page.py   Statistics › All time
    patterns_page.py   Statistics › Understanding your patterns
    distributions_panel.py  the "Blink distributions" histograms (live and imported)
    recordings_section.py   All time: import, choose and inspect recordings (background loading)
    settings_page.py   Settings
    account_page.py    Log in (not available yet)
    theme.py           colours, fonts, style sheet
    widgets/           drawing-only pieces (graph, chart, artwork, status, icons, page)
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
