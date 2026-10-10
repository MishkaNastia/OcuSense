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
.venv/bin/pip install pyinstaller
./packaging/build_mac.sh
```

The app appears in `dist/OcuSense.app` (about 380 MB). It is signed only for
your own Mac (ad-hoc). Sharing it with others needs an Apple Developer ID and
notarisation. The first time it opens the camera, macOS asks for permission
for OcuSense itself.

## Run the OpenCV prototype

```
source .venv/bin/activate
python main.py
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
5. The screen also shows each eye separately: its openness, EAR,
   calibration references and its own blink count. Per-eye counts also
   include one-eyed winks; the main "Blinks" count needs both eyes.
6. A live graph at the bottom shows the last 10 seconds of personal eye
   openness (left, right, both), the two thresholds, and a green tick for
   each counted blink (`ocusense/core/history.py`, drawn by `score_graph.py`). It is kept in memory only.

Personal eye openness is relative to your own calibration only. It is not
a fatigue or health measure, and accuracy has not been established for
everyone - see [EVALUATION_CHECKLIST.md](EVALUATION_CHECKLIST.md).

## Project layout

- `ocusense/core/`: monitoring logic with no user interface (EAR,
  calibration, blink counting, openness history, and `monitor.py`, which
  runs one measuring step per camera frame).
- `main.py` + `score_graph.py`: the OpenCV prototype window.
- `ocusense/app/`: the PySide6 desktop app (window, camera thread, graph, artwork).

## Tests

```
python -m unittest
```
