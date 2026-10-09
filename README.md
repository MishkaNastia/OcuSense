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

## Run

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
   (eye height ÷ width) in pixel coordinates (`eye_metrics.py`).
2. Calibration stores *your* open and closed EAR for each eye (median of
   many frames) and rejects calibrations that are unclear or unstable
   (`calibration.py`).
3. Each eye's EAR becomes **personal eye openness**: 1 = as open as in
   calibration, 0 = as closed. The two eyes are averaged.
4. A blink is counted once per open → closed (below 0.35) → open
   (above 0.65) sequence (`blink_counter.py`). Measurement pauses when the
   face is lost, too small or turned away.
5. The screen also shows each eye separately: its openness, EAR,
   calibration references and its own blink count. Per-eye counts also
   include one-eyed winks; the main "Blinks" count needs both eyes.

Personal eye openness is relative to your own calibration only. It is not
a fatigue or health measure, and accuracy has not been established for
everyone - see [EVALUATION_CHECKLIST.md](EVALUATION_CHECKLIST.md).

## Tests

```
python -m unittest
```
