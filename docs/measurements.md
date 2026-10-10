# OcuSense measurements and graphs

This document explains **what OcuSense measures, how, and over which time spans**, and
what every graph in the Mac app shows. It describes the code as it is (measurement
version `ear-personal-v2`). All values are descriptive: OcuSense does **not** diagnose
tiredness, dry eye or any other condition, and gives no health scores.

Contents

1. [The pipeline at a glance](#1-the-pipeline-at-a-glance)
2. [All settings in one table](#2-all-settings-in-one-table)
3. [From camera frame to eye measurement](#3-from-camera-frame-to-eye-measurement)
4. [Calibration](#4-calibration)
5. [Personal eye openness](#5-personal-eye-openness)
6. [The blink detector](#6-the-blink-detector)
7. [Valid observation, gaps and coverage](#7-valid-observation-gaps-and-coverage)
8. [The measurements](#8-the-measurements)
9. [Time windows: rolling vs. fixed](#9-time-windows-rolling-vs-fixed)
10. [Graphs and numbers, page by page](#10-graphs-and-numbers-page-by-page)
11. [Blink distributions (histograms)](#11-blink-distributions-histograms)
12. [Saved recordings](#12-saved-recordings)
13. [Precision and limitations](#13-precision-and-limitations)
14. [Where it lives in the code](#14-where-it-lives-in-the-code)

---

## 1. The pipeline at a glance

Every camera frame goes through the same steps:

```
camera frame (~30 per second)
  │  mirrored, analysed in memory, then thrown away (never saved)
  ▼
MediaPipe Face Landmarker → 478 points on the face
  │  6 points per eye
  ▼
Eye Aspect Ratio (EAR), left and right            ← saved to the recording files
  │  quality checks: is this frame reliable?
  ▼
personal eye openness per eye (0 % = your closed, 100 % = your open)   ← uses YOUR calibration
  │  mean of both eyes
  ▼
blink detector (closes below 35 %, reopens above 65 %)
  │
  ▼
measurements: blink count, blink rate, closure duration, time classified as closed,
tracking coverage — shown live, per session, per minute, and as distributions
```

Two clocks are used: a steady **monotonic clock** for all durations inside the app, and
the **wall clock** (date and time of day) only to label sessions and in saved files.

---

## 2. All settings in one table

These are the same for everyone (they live in `ocusense/config.py`). Your personal
calibration values are measured, not set.

| Setting | Value | What it does |
| --- | --- | --- |
| `CLOSE_BELOW` | 0.35 (35 %) | eyes count as **closed** when personal openness falls below this |
| `REOPEN_ABOVE` | 0.65 (65 %) | …and as **open again** only above this (completes a blink) |
| `MIN_SAMPLES` | 15 frames | reliable frames needed per eye in the open and closed calibration steps |
| `MIN_RELATIVE_SEPARATION` | 0.25 | closed EAR must be at least 25 % below open EAR |
| `MAX_SPREAD_FRACTION` | 0.25 | allowed wobble within a calibration step, relative to the open–closed gap |
| `MIN_CALIBRATION_BLINKS` | 3 | blinks that must be detected in the last calibration step |
| `MIN_EYE_WIDTH_PX` | 15 px | smaller eyes in the image = face too far away → frame unreliable |
| `MIN_EYE_WIDTH_RATIO` | 0.6 | one eye much narrower than the other = head turned → frame unreliable |
| `GRAPH_SECONDS` | 10 s | length of the live eye-openness graph |
| `MAX_FRAME_GAP` | 0.5 s | two valid frames further apart than this are a **gap** (not observed time) |
| `UNTRACKED_MIN` | 2 s | missing tracking this long is drawn as a gap on the All time timeline |
| `MIN_TRACKED_PER_MINUTE` | 20 s | valid observation needed for a per-minute value on the All time chart |
| `MIN_SESSION_SECONDS` | 10 s | shorter sessions are not kept in Statistics |
| `ROLLING_WINDOW_SECONDS` | 60 s | length of the "Last 60 seconds" rolling window |
| `MIN_VALID_SECONDS_FOR_RATE` | 30 s | valid observation needed before a rate or closed time is shown (rolling window and 60 s distribution windows) |
| `PROCESSING_RATE_WINDOW` | 5 s | period used to measure the actual frames per second |
| `RECORDING_CHUNK_SECONDS` | 600 s | a new recording file every 10 minutes |
| `MEASUREMENT_VERSION` | `ear-personal-v2` | changes whenever a definition changes |

The 0.5 s gap, the 30 s minimum and the 20 s per-minute minimum are **engineering
choices** for this prototype, not clinical standards.

---

## 3. From camera frame to eye measurement

**Camera.** The built-in camera (camera 0) at whatever resolution and frame rate macOS
provides — usually about **30 frames per second**, less in dim light. The app measures the
real rate (see [8.6](#86-processing-rate-and-precision)). Each frame is **mirrored** (so the
preview behaves like a mirror and "left" means your left eye), analysed, and discarded.

**Face landmarks.** Google MediaPipe Face Landmarker (video mode, one face) finds 478
points on the face. OcuSense uses six per eye:

| Eye | MediaPipe points (p1 … p6) |
| --- | --- |
| left | 33, 160, 158, 133, 153, 144 |
| right | 362, 385, 387, 263, 373, 380 |

p1 and p4 are the eye corners; p2/p6 and p3/p5 are pairs on the upper and lower lid.

**Eye Aspect Ratio (EAR)** — how tall the eye is compared to how wide, from pixel
positions (so the image's width/height ratio doesn't distort it):

```
        p2   p3
    p1          p4          EAR = ( |p2 − p6| + |p3 − p5| ) / ( 2 × |p1 − p4| )
        p6   p5
```

An open eye has a larger EAR than a closed one. Typical values are around 0.25–0.35 open
and below 0.1 closed, but they differ between people and setups — which is why OcuSense
never compares EAR with a fixed number and calibrates instead.

**Reliable frame?** A frame is used for measurement only if:
- a face was found,
- all twelve eye points are inside the picture,
- both eyes are at least **15 px** wide (otherwise "face too small – move closer"),
- the narrower eye is at least **60 %** as wide as the wider one (otherwise "head turned").

Unreliable frames are **not** counted as open or closed: they are missing observation.

---

## 4. Calibration

Calibration measures **your** open and closed eyes. It runs at the start of the first
session (and whenever you press Recalibrate) and takes **23.5 seconds**:

| Step | Instruction | Get ready | Measuring | Frames used |
| --- | --- | --- | --- | --- |
| 1. Open | eyes comfortably open, look at the screen | 3 s | 3 s | 0.5–3.0 s into measuring |
| 2. Closed | close gently, count slowly to 5 (a sound says when to open) | 4 s | 4.5 s | 1.0–3.5 s into measuring |
| 3. Blinks | blink naturally about 5 times | 3 s | 6 s | all 6 s |

The "frames used" windows skip the moments when you are still opening or closing your
eyes. Only reliable frames are used.

**References.** For each eye, the **median** EAR of the open frames becomes the *open
reference* and the median of the closed frames the *closed reference*. The median ignores
a few odd frames, such as an accidental blink during the open step.

**Acceptance checks** — calibration fails with an explanation unless, for each eye:
1. at least **15** reliable frames were collected in both the open and the closed step;
2. the closed reference is at least **25 %** below the open reference;
3. the variation within each step is small: the robust spread (1.4826 × median absolute
   deviation, comparable to a standard deviation) is at most **25 %** of the open–closed gap;
4. in step 3, using the new references, the normal blink detector finds at least **3 blinks**.

Each calibration is stored with: the four reference EARs, the two detector thresholds, the
time it was made and the measurement version (see [12](#12-saved-recordings)).

---

## 5. Personal eye openness

For each eye separately:

```
personal openness = (EAR − closed reference) / (open reference − closed reference)
```

- **1.0 (100 %)** = as open as during calibration, **0.0 (0 %)** = as closed as during calibration.
- **Unclipped** values can go below 0 % (squeezed shut) or above 100 % (opened wider than in
  calibration). These are kept in saved files and in the openness distribution.
- **Clipped** to 0–100 %: what the blink detector and the on-screen value use, so one eye
  squeezed extra hard can't dominate.
- **Both eyes** = the mean of the two clipped values. Because a real blink closes both
  eyes, the mean only falls below 35 % when both close: a one-eyed wink stays near 50 % and
  is not counted.

It is **not** a fatigue percentage and **not** a literal measure of how far the eyelids are
open. Lighting, camera angle, glasses and head position change it — recalibrate when they
change.

---

## 6. The blink detector

A three-state detector with **two thresholds** (hysteresis), fed with the both-eyes
openness of every frame:

```
UNKNOWN ──(openness > 65 %)──► OPEN ──(openness < 35 %)──► CLOSED ──(openness > 65 %)──► OPEN
                                                                         = one blink counted
```

- It starts in **UNKNOWN** and only starts watching after it has seen the eyes clearly
  open, so starting with closed eyes never counts as a blink.
- Two thresholds instead of one stop small wobbles around a single line from being counted
  twice.
- An unreliable frame, lost tracking or a pause sends it back to **UNKNOWN**: a
  half-finished blink is forgotten, never counted.
- A blink is counted at the frame where the eyes **reopen above 65 %**.

---

## 7. Valid observation, gaps and coverage

- **Valid frame**: reliable, both eyes measured, and a calibration in use.
- **Valid observation interval**: the time between two consecutive valid frames, if they are
  at most **0.5 s** apart. Longer gaps, invalid frames and pauses are **missing observation**.
- Missing observation is **never** counted as zero blinks or as closed eyes. All rates and
  percentages divide by **valid observation time**, not by clock time.
- **Study time** = the time a session was running, pauses excluded.
- **Tracking coverage** = valid observation time ÷ study time.

---

## 8. The measurements

### 8.1 Blink count
Completed blinks (closed → reopened, see [6](#6-the-blink-detector)) in the session.

### 8.2 Blink rate (blinks per minute)
```
blink rate = completed blinks ÷ (valid observation seconds ÷ 60)
```

### 8.3 Closure duration (one per blink)
From the frame where the detector went **open → closed** (below 35 %) to the frame where it
went **closed → open** (above 65 %) — the same frame that counts the blink. This is the
**time between the two thresholds, not the whole blink movement** (the lid starts moving
before 35 % and finishes after 65 %). A closure is **discarded** (no duration) if tracking
was lost, a gap occurred or monitoring paused before it reopened. Shown as the **median**
in milliseconds, so a few long closures don't dominate.

### 8.4 Time classified as closed (%)
```
closed % = valid observation time in the detector's CLOSED state ÷ valid observation time × 100
```
An interval counts as closed when the detector was closed at the interval's start frame.
A long closure counts even if it never reopens into a blink.

### 8.5 Live personal eye openness
The latest frame's both-eyes openness (mean of the two clipped values), shown as "—" when
the frame isn't valid — never as 0 %.

### 8.6 Processing rate and precision
The app counts the frames processed in the last **5 s** to get the real frames per second.
All durations are measured between frame time stamps, so they are only as precise as the
time between frames: about **±33 ms at 30 fps**. The Study page states the current value
under "Last 60 seconds".

---

## 9. Time windows: rolling vs. fixed

OcuSense uses two different kinds of one-minute window on purpose.

| | Rolling "Last 60 seconds" (Study page) | Fixed 60 s windows (Blink distributions) | Per-minute bins (All time chart) |
| --- | --- | --- | --- |
| What | always the **last 60 s up to now**; moves forward with every frame | **separate, non-overlapping** minutes: 0–60 s, 60–120 s, … from the session or recording start | separate minutes from the session start |
| Purpose | a current, smooth live value | one independent value per minute, so they can be counted in a histogram | the Today line chart |
| Minimum data | 30 s valid observation in the window | 30 s valid observation in the window; a window still in progress is not used | 20 s valid observation in the minute |
| Before that | "Collecting data" | window excluded (counted as excluded) | no point on the line |

Why both? Consecutive rolling values overlap by up to 59 seconds, so they are not
independent observations; putting every rolling value into a histogram would count the same
blinks many times. The fixed windows give exactly one rate per minute.

**Rolling window details.** It keeps only the last 60 s of valid intervals, blinks and
closures (older ones are dropped, so memory stays small). An interval that crosses the
60 s edge counts **partly** (only the part inside the window). Pauses inside the window
reduce the running time, and are reported in the window's coverage.

**Other time spans**: the live graph shows the last **10 s**; tracking gaps of **2 s** or more
are drawn on the All time timeline; sessions shorter than **10 s** are not kept; recording
files rotate every **10 minutes**.

---

## 10. Graphs and numbers, page by page

### Study
| Element | What it shows |
| --- | --- |
| Timer | study time of this session, pauses excluded |
| "N blinks this session" | blink count (8.1) |
| **Personal eye openness** (big number) | live both-eyes openness of the latest frame (8.5) |
| **Live graph** | both-eyes openness (clipped) over the **last 10 s**; dashed lines at the 35 % and 65 % detector thresholds; a red dot at the lowest point of each counted blink. The line breaks where tracking was lost or frames were more than 0.5 s apart. Dimmed while paused. |
| **Last 60 seconds** | rolling window (section 9): blink rate, median closure duration, time classified as closed, plus valid observation, monitored time and tracking coverage. Rate and closed time show "Collecting data" until 30 s of valid observation. |
| Precision note | the measured frames per second and the resulting timing precision (8.6) |
| Show details (or Settings › Measurement details) | raw EAR of both eyes, unclipped openness, whether the frame is valid and closed, processing rate, number of blinks and timed closures in the window, and the calibration in use |

### Statistics › Current session
| Element | What it shows |
| --- | --- |
| Study time, tracking coverage, blinks counted | for the whole session so far (section 7, 8.1) |
| Eye measurements · whole session so far | blink rate, median closure duration and time classified as closed over **all** valid observation of the session (not just the last 60 s) |
| Personal eye openness graph | the same 10 s live graph as on the Study page |
| Blink distributions | five histograms, updated every 2 s — see [11](#11-blink-distributions-histograms) |

### Statistics › All time
| Element | What it shows |
| --- | --- |
| Total study time, completed sessions | across all sessions kept since OcuSense opened (kept in memory only; gone after quitting) |
| Recorded breaks | "—": breaks aren't recorded by the Mac app yet |
| By date (Today / This week / This month) | filters the chart and session list |
| **Timeline** | one row per day; black bars = study time, dashed outlines = tracking gaps of 2 s or more |
| **Per-minute line** (Today) | the chosen measure per minute (per-minute bins, section 9); minutes with less than 20 s valid observation have no point; separate sessions are never joined by a line |
| Day values (week, month) | for several sessions together: blink rate and closed time are **weighted by tracked time** (total blinks ÷ total tracked minutes; total closed time ÷ total tracked time), not a plain average of session values; closure duration is the median of all closures |
| Sessions | each session's study time, pauses, blink rate, median closure, closed time and coverage |
| Blink distributions from recordings | analysis of saved recordings — see [11](#11-blink-distributions-histograms) |

Demo sessions (`--demo-history`) are labelled "Demo data" and are never mixed into the
recording analysis.

### Statistics › Understanding your patterns
Plain-language explanations only. Personal observations need both history and your own
check-ins; the Mac app doesn't record check-ins yet, so it shows "Your patterns will appear
as you complete sessions and check-ins" and draws no conclusions.

---

## 11. Blink distributions (histograms)

Shown on **Current session** (live, refreshed every 2 s) and, for imported recordings, on
**All time**. Five histograms, one at a time, chosen with the tabs. Live and imported data use
**exactly the same code and definitions**.

A **valid segment** is a stretch of valid frames without a gap longer than 0.5 s. An
invalid frame, a longer gap, a pause, a recalibration or the end of the data ends it.

### 11.1 Closure duration (default)
- **Each value**: one completed closure event (8.3), in milliseconds.
- **Axes**: closure duration (ms) × number of events.
- **Shown**: number of events, median, interquartile range (25th–75th percentile).
- **Excluded**: "interrupted" events — closures cut off by lost tracking, a gap or a pause,
  and blinks whose closure couldn't be timed. Their number is shown.
- **Bins**: 50 ms wide from 0 to 1000 ms, plus one **"1000 ms or more"** bar so long
  closures stay visible.

### 11.2 Time between blinks
- **Each value**: the time from the **start of one completed closure to the start of the
  next** (onset to onset), in seconds.
- Only pairs **inside the same valid segment** — never across a gap, pause or recalibration.
- **Axes**: interval (s) × number of intervals. **Shown**: count, median, interquartile range.
- **Bins**: 1 s wide from 0 to 30 s, plus "30 s or more".

### 11.3 Blink rate per minute
- **Each value**: one **fixed, non-overlapping 60 s window** (section 9):
  `completed blinks ÷ valid minutes in that window`.
- A window counts only if it is **finished** and has **at least 30 s** of valid observation.
  Eligible and excluded windows are both reported.
- Fewer than **3** eligible windows → a message instead of a histogram.
- **Axes**: blinks per minute × number of windows. **Bins**: 2 per minute, 0–40, plus "40 or more".
- This is the **main blink-frequency measure**: one independent value per minute, comparable
  between sessions.

### 11.4 Frequency per blink
- **Each value**: `60 ÷ time between blinks` (section 11.2) — the blink frequency implied by
  one interval, in blinks per minute. Example: 3 s between two blinks = 20 per minute.
- One value per pair of consecutive blinks, with **exactly the same exclusions** as the time
  between blinks (same valid segment; never across a gap, pause or recalibration).
- Appears after a short recording (it needs no full minutes), but it is **much noisier** than
  the per-minute rate: one long pause gives one very low value, a quick double blink a very
  high one. Use it for a first impression; use 11.3 to compare sessions.
- **Axes**: blinks per minute × number of values. **Shown**: count, median, interquartile range.
- **Bins**: 2 per minute from 0 to 60, plus **"60 or more"** (blinks 1 s apart or closer), so
  very short intervals stay visible.

### 11.5 Personal eye openness
- Left eye, right eye, or both (mean of the two **unclipped** values; only when both are valid).
- **Time-weighted**: every valid interval adds its **duration** to the bin of the openness at
  its start frame. The bars are a **percentage of valid observed time**, not of frames, so a
  changing frame rate doesn't distort the shape.
- **Bins**: 5 % wide from 0 to 100 %, plus **"below 0 %"** and **"100 % or more"** bars; the
  exact share of time outside 0–100 % and the lowest and highest values seen are shown.
- Dashed lines: the recorded detection thresholds (the detector applies them to the mean of
  both eyes, each clipped).

### 11.6 Common rules
- **Fixed bins**: the edges never change between refreshes or sessions, so histograms can be
  compared directly. Widths are never finer than the frame timing allows.
- **Tooltips**: hover a bar for its range and its count or share of time.
- **Small samples**: with fewer than 10 events the histogram is shown with a note that the
  shape isn't reliable yet.
- **Imported recordings** use the calibration and thresholds **saved with each recording**,
  never hard-coded values, and recompute openness from the raw EAR.
- **Inspect detection** (All time, imported recordings): a selectable 10/30/60 s stretch of the
  recording with left and right openness, what the detector used, the thresholds, timed
  closures (pale bands), counted blinks (red dots) and tracking gaps (hatched). Use it to
  check the detection before trusting the histograms.
- **Export results…** writes, to a new folder you choose: `blink_events.csv` (one row per
  event), `windows.csv` (each 60 s window and why it was or wasn't eligible), `summary.csv`
  (counts, medians, quartiles, exclusions), `analysis_settings.json` (definitions, bins,
  thresholds, calibration, source files, exclusions) and `histogram.png`.

---

## 12. Saved recordings

While the camera is on, OcuSense saves one row per frame to
`~/Library/Application Support/OcuSense/recordings/` — a new file every 10 minutes and
whenever you pause, stop, quit or recalibrate (Settings › Data & privacy can switch it off).

**`ear_YYYY-MM-DD_HH-MM-SS.csv`**

| Column | Meaning |
| --- | --- |
| `unix_time` | wall-clock time in seconds, millisecond precision |
| `left_ear`, `right_ear` | raw EAR (empty when no face was found) |
| `reliable` | 1 if the frame passed the quality checks (section 3), 0 if not |
| `left_openness`, `right_openness` | personal openness from the calibration in use, 0–1, **unclipped**; empty when not calibrated or not reliable |

**`ear_YYYY-MM-DD_HH-MM-SS.calibration.json`** (one per CSV): the four reference EARs,
`close_below`, `reopen_above`, `calibrated_at`, `measurement_version` and the openness
formula — or `"calibration": null` for the frames recorded during calibration itself.
Every CSV belongs to exactly one calibration.

**Analysing saved recordings** (Statistics › All time › Import recording…): files are read
only, never changed. Files without calibration (`null`) are excluded with that reason.
Consecutive files are joined only when they share exactly the same calibration **and** the
next file starts within 0.5 s of the previous one's last frame (the app rotated files while
the camera kept running); everything else stays separate. The recording is replayed through
the app's own calibration code and detector. One unavoidable difference from live use: a
time gap longer than 0.5 s inside a file is treated like a pause.

No camera images and no face landmarks are ever saved.

---

## 13. Precision and limitations

- **Frame timing**: durations are accurate to about one frame interval (±33 ms at 30 fps;
  coarser in dim light, when cameras slow down).
- **Threshold-defined closures**: closure duration measures the time between 35 % and 65 %,
  not the full lid movement; changing the thresholds changes the values.
- **Calibration matters**: if your eyes look less open while studying than during
  calibration (for example looking down at the screen after looking at the camera), the
  "open" level can sit close to the 65 % reopening threshold. Then a partial reopening may
  not end a closure, which makes closures look longer. Recalibrate in your normal study
  position and check with Inspect detection.
- **Webcam limits**: lighting, glasses, camera angle and head movement affect EAR.
- **Prototype rules**: the 0.5 s gap, 30 s and 20 s minimums and 3-window minimum are
  engineering choices, not clinical standards.
- **Descriptive only**: no fatigue states, no "healthy" ranges, no health scores. Compare
  your values with your own earlier sessions rather than with other people.
- **Session history** in Statistics is kept in memory only; the raw recordings are the
  permanent record.

---

## 14. Where it lives in the code

| Topic | File |
| --- | --- |
| All settings | `ocusense/config.py` |
| EAR and reliability checks | `ocusense/core/eye_metrics.py` |
| Calibration | `ocusense/core/calibration.py` |
| Blink detector | `ocusense/core/blink_counter.py` |
| Valid intervals, closures, rolling window | `ocusense/core/measurements.py` |
| Session totals and per-minute bins | `ocusense/core/session.py`, `ocusense/core/models.py` |
| Period values (day, week, month) | `ocusense/core/stats.py` |
| Blink distributions | `ocusense/core/distributions.py` |
| Replaying saved recordings | `ocusense/core/replay.py`, `ocusense/recording_files.py` |
| Saving recordings | `ocusense/recording.py` |
| Exports | `ocusense/exports.py` |
| Frame processing per camera frame | `ocusense/monitoring/pipeline.py` |
