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
13. [Distance reminder](#13-distance-reminder)
14. [Posture](#14-posture)
15. [Precision and limitations](#15-precision-and-limitations)
16. [Where it lives in the code](#16-where-it-lives-in-the-code)

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
| `IRIS_DIAMETER_MM` | 11.7 mm | assumed iris width, the ruler for the posture distance |
| `FOCAL_LENGTH_PER_FRAME_WIDTH` | 1.0 | webcam focal length ÷ frame width (≈ 53° view); tune if the cm are off |
| `POSTURE_CALIBRATION_SECONDS` | 60 s | the posture baseline: the first minute of each study session (or after Recalibrate posture or a screen tilt) |
| `POSTURE_MIN_SAMPLES` | 300 frames | frames with everything measured needed in that minute |
| `POSTURE_MAX_PITCH_SPREAD` | 5° | head angle spread above this = no single posture: baseline rejected |
| `POSTURE_SUSTAIN_SECONDS` | 20 s | a posture limit must be exceeded this long in a row to count… |
| `POSTURE_GRACE_SECONDS` | 3 s | …where back within it (or no face) for up to this long doesn't restart the count |
| `POSTURE_PITCH_DROP_DEGREES` | 12° | head dropped: chin this much lower than at calibration |
| `POSTURE_ROLL_DEGREES` | 10° | head tilted this much either way |
| `POSTURE_MIN_DISTANCE_CM` | 50 cm | closer than this counts as too close… |
| `POSTURE_CLOSER_FRACTION` | 0.20 | …as does being 20 % closer than at calibration |
| `POSTURE_CENTRE_DROP` | 0.05 | slumped: face centre 5 % of the frame height lower… |
| `POSTURE_SLUMP_GROWTH` | 0.05 | …and the face at least 5 % bigger (lower alone with the lid sensor) |
| `POSTURE_REMINDER_GAP_SECONDS` | 600 s | the "stop slouching" message: one per poor stretch, at least 10 minutes apart |
| `LID_RECALIBRATE_DEGREES` | 5° | screen tilted this much from the baseline… |
| `LID_SETTLE_SECONDS` | 2 s | …and left there this long: "You tilted your screen, recalibrating now" |
| `LID_READ_INTERVAL` | 0.5 s | time between screen angle readings |
| `PROXIMITY_WARN_RATIO` | 1.6 | distance reminder when the face looks 1.6× as big as at calibration… |
| `PROXIMITY_SUSTAIN_SECONDS` | 3 s | …for this long |
| `PROXIMITY_CLEAR_RATIO` | 1.3 | below this the person counts as moved back |
| `PROXIMITY_COOLDOWN_SECONDS` | 300 s | default time before another distance reminder (adjustable: 5 s, 10 s, 15 s, 30 s, 1, 2, 3, 5 or 10 min) |
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

Calibration measures **your** open and closed eyes. It runs **once** — the first time
someone presses Start on a Mac — and whenever they press **Recalibrate**. It takes
**23.5 seconds**:

| Step | Instruction | Get ready | Measuring | Frames used |
| --- | --- | --- | --- | --- |
| 1. Open | sit about an arm's length from the screen, eyes comfortably open, look at the screen | 3 s | 3 s | 0.5–3.0 s into measuring |
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

During the open step OcuSense also stores the **reference face size** (median distance between
the eye centres ÷ image width) for the distance reminder (section 13).

Each calibration is stored with: the four reference EARs, the two detector thresholds, the
reference face size, the time it was made and the measurement version (see [12](#12-saved-recordings)).

**Saved and reused.** A successful calibration is saved on the Mac, in the user account's
`~/Library/Application Support/OcuSense/calibration.json` (one person per Mac account), and
loaded every time OcuSense opens, so Start goes straight to monitoring. The file holds only
numbers: the four reference EARs, the reference face size, the calibration time and the
measurement version (the detector thresholds come from the current settings).
- **Recalibrate** replaces it — but only when the new calibration succeeds. A cancelled or
  failed recalibration keeps the saved one.
- A damaged file, values that fail the calibration's own checks, or a file made with another
  measurement version are ignored: OcuSense says so and calibrates again.
- Recalibrate when lighting, glasses, seat or screen position change: a calibration made in a
  different setup can make eyes look less open than they are (section 14).

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
Blink frequency can also be written **per second**: `blinks per second = blinks per minute ÷ 60`.
Both say the same thing; per minute gives friendlier numbers:

| Per minute | Per second | One blink every |
| --- | --- | --- |
| 6 | 0.1 | 10 s |
| 12 | 0.2 | 5 s |
| 15 | 0.25 | 4 s |
| 20 | 0.333 | 3 s |
| 30 | 0.5 | 2 s |
| 60 | 1 | 1 s |

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
| Posture message | "Stop slouching, hunchbacks are not particularly sexy you know" under the buttons (with the time) when posture turns poor — see [14](#14-posture) |
| Screen tilted | "You tilted your screen, recalibrating now" under the buttons (with the time) after a clear screen tilt — see [14](#14-posture) |
| Break reminder | a note under the buttons (with the time) when a break reminder was given, until dismissed — see [11.7](#117-compared-with-your-reference) |
| Show details (or Settings › Measurement details) | raw EAR of both eyes, unclipped openness, whether the frame is valid and closed, processing rate, number of blinks and timed closures in the window, and the calibration in use |

### Statistics › Current session
| Element | What it shows |
| --- | --- |
| Study time, tracking coverage, blinks counted | for the whole session so far (section 7, 8.1) |
| Eye measurements · whole session so far | blink rate, median closure duration and time classified as closed over **all** valid observation of the session (not just the last 60 s) |
| Personal eye openness graph | the same 10 s live graph as on the Study page |
| Posture | when ticked in Settings: good / poor (with the limits exceeded), the current changes from your posture baseline (including a corrected screen tilt), the 1-minute baseline's progress, and a **Recalibrate posture** button — see [14](#14-posture) |
| Blink distributions | five histograms, updated every 2 s — see [11](#11-blink-distributions-histograms) |
| Compared with your reference | the saved reference (or, without one, this session's first 10 minutes), the latest 5-minute window's test result and a count of windows so far — see [11.7](#117-compared-with-your-reference) |

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
- **Per second** (switch under the tabs): the same windows ÷ 60, in blinks per second.
  **Bins**: 0.05 per second (= 3 per minute), 0–0.7, plus "0.7 or more" (42 per minute).
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
- **Per second** (switch under the tabs): `1 ÷ time between blinks`, in blinks per second —
  for example 3 s between blinks = 0.333 per second. **Bins**: 0.05 per second (= 3 per minute),
  0–1, plus **"1 or more"** (blinks 1 s apart or closer).

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
  compared directly — compare per-minute charts with per-minute charts and per-second charts
  with per-second charts, since the two units use different bins. Widths are never finer than
  the frame timing allows.

  | Histogram | Bin width | Range | Extra bars |
  | --- | --- | --- | --- |
  | Closure duration | 50 ms | 0–1000 ms | ≥ 1000 ms |
  | Time between blinks | 1 s | 0–30 s | ≥ 30 s |
  | Blink rate per minute | 2 /min (0.05 /s) | 0–40 /min (0–0.7 /s) | ≥ 40 /min (≥ 0.7 /s) |
  | Frequency per blink | 2 /min (0.05 /s) | 0–60 /min (0–1 /s) | ≥ 60 /min (≥ 1 /s) |
  | Personal eye openness | 5 % | 0–100 % | < 0 %, ≥ 100 % |
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
  event), `windows.csv` (each 60 s window, its rate per minute and per second, and why it was or wasn't eligible), `summary.csv`
  (counts, medians, quartiles, exclusions; both frequency measures in per minute and per second), `analysis_settings.json` (definitions, bins,
  thresholds, calibration, source files, exclusions) and `histogram.png`.

### 11.7 Compared with your reference
Statistics › Current session asks whether the **time between blinks** (11.2) is still
distributed like in your **reference**: the first 10 minutes of one session, saved once.
- **Reference**: the intervals whose two onsets both fall in the first **600 s** of a session.
  If no reference is saved, the next session's first 10 minutes become it, as long as they hold
  at least **50** intervals (otherwise the session after that tries again). It is kept when you
  recalibrate. **Settings › Data & privacy › Make a new reference…** discards it, and the next
  session's first 10 minutes become the new one. `analysis/set_reference.py` makes one from a
  saved recording instead. It is saved as `reference.json` beside the recordings folder
  (section 12).
- **Fit**: log-normal by maximum likelihood on y = ln(interval): mu = mean(y),
  sigma² = mean((y − mu)²) (ddof = 0). Intervals ≤ 0 are excluded and counted.
- **Windows**: **300 s** long, starting at the session start and every **30 s** after. An
  interval belongs to a window when both its onsets are inside. Pause time counts as session
  time, so a window during a pause usually has too few intervals.
- **Test**: two-sample likelihood ratio. H0: one (mu, sigma) for the reference and the window
  together. H1: one each. LR = 2·[ℓ(reference) + ℓ(window) − ℓ(pooled)], with ℓ the normal
  log-likelihood of the logs (the log-normal's 1/x term cancels). p = exp(−LR/2), the
  chi-square survival function with 2 degrees of freedom. A window is **below the line** when
  p < **0.01**.
- **Confirmed different**: only when **3 windows in a row** are below the line (6 minutes of
  data, since the windows overlap). A single window below the line is shown as "not confirmed
  yet". A window that can't be tested breaks the run, and the count starts again.
- **Not tested**: fewer than **15** intervals in the window ("not enough data"); a baseline
  with fewer than 2 intervals or no spread ("baseline unusable").
- **When**: with a saved reference, each window is tested **5 s** after it ends (an interval is
  only recorded when its second blink reopens). The first result comes at about **5 min**, then
  one every 30 s. In the session that **creates** the reference, nothing can be tested before
  its first 10 minutes are complete. At **10 min**, every window that has already ended is
  compared with them at once (these overlap them and are marked so, as a sanity check), and then
  one every 30 s.
- **Break reminder**: when **3 windows in a row** are below the line **and** their median
  interval is longer than the reference's (window mu > reference mu: blinking less often), the
  app shows a Mac notification and a note on the Study page: "Hey, you should take a break, else
  your eyes will become drier than the Sahara desert." At most **one per slow stretch** (a
  stretch ends after **5 min** without such a window) and at least **20 min** apart. Faster
  blinking never triggers one. Settings › Reminders › Break reminders switches it off (for as
  long as OcuSense is open). The trigger is a statistical comparison of blink timing; the app
  doesn't measure dryness.
- **Same as offline**: `analysis/sliding_window_lrt.ipynb` runs the same code
  (`sliding_windows`) on saved recordings against the saved reference, so the live and offline
  results match.
- **Limitations**: windows overlap (90 % shared data) and about 100 are tested per hour with
  no correction for multiple testing, so single windows below the line happen by chance. That is
  why only 3 in a row count. With 3 in a row a difference is confirmed at the earliest 1 minute
  after the first window below the line.
  With 15–100 intervals per window, the fits and p-values are approximate. Tracking gaps cut
  intervals, and long ones are lost most often. "Different" means "not distributed like those
  10 minutes": a different activity (long reading, talking) counts just as drift does, so
  comparisons mean most during the same kind of activity as the reference. A reference kept
  across recalibrations may have been detected with other thresholds. Like everything here it
  describes timing only: it is not a fatigue assessment.

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

**`reference.json`** (beside the `recordings` folder): your reference for blink timing
(11.7). It holds the reference's intervals as (onset, onset) pairs in seconds since that session
started, the fit (n, mu, sigma), when and from what it was made, and the calibration in use.
Numbers only.

No camera images and no face landmarks are ever saved.

---

## 13. Distance reminder

A gentle reminder when someone has moved much closer to the screen than during calibration:

> **Trying to lick the screen?**
> Go easy on your eyes and move back a little.

**Method.** The camera can't measure centimetres, but a face looks bigger the closer it is
(apparent size ∝ 1 ÷ distance). For every reliable frame:

```
face size  = distance between the two eye centres (midpoint of each eye's corners) ÷ image width
closeness  = face size now ÷ reference face size (median during calibration step 1, at about an arm's length)
```

| Closeness | Roughly | If calibrated at 60 cm |
| --- | --- | --- |
| 1.0 | where you calibrated | 60 cm |
| 1.3 | 77 % of that distance | ~46 cm |
| 1.6 | 62 % of that distance | ~37 cm |
| 2.0 | half the distance | 30 cm |

The eye-centre distance is used rather than eye width because it doesn't change when you
blink or squint. Dividing by the image width makes it independent of camera resolution.

**Rules.**
1. Closeness at or above **1.6** for **3 seconds** without interruption → a reminder (a quick
   lean forward doesn't count; an unreliable frame restarts the 3 s).
2. The reminder stays until closeness falls below **1.3** (two levels, like the blink detector,
   so it doesn't flicker), or until you press **Got it**.
3. **Remind again after** (Settings › Reminders, default **5 minutes**, from **5 s to 10 min**):
   if you are still too close when that time has passed, you are reminded again — and never
   more often than that, even if you move back and forth.
4. Pausing, stopping or recalibrating clears it. The **On** switch in Settings › Reminders turns
   it off. Both choices are remembered between launches
   (`~/Library/Application Support/OcuSense/preferences.json`).

**Where it appears.** Always as a card at the top of the OcuSense window, in the OcuSense
alert style (paper card, ink border, a Miró mark: an eye pressed against the screen with a
vermilion tongue). When OcuSense is in the background, also as a **macOS notification** in
Notification Centre, with the same title and text. It is sent with the app's shared
`ocusense/notifications.py` (macOS's built-in `osascript`, like the break reminders), so it
works both in OcuSense.app and when running `python -m ocusense`; macOS shows it under
"Script Editor" and draws it in its own style. If macOS asks whether Script Editor may send
notifications, allow it once. No sound is played.

**Limits.** It is relative to your calibration, not centimetres: calibrating while already
very close makes it less useful. Leaning or turning the head changes the apparent size a
little; the thresholds leave room for that. It never affects blink detection — EAR is a ratio
and barely changes with distance.

## 14. Posture

Statistics › Current session shows whether you are sitting the way you did when your posture
baseline was recorded. It uses the same Face Landmarker as the eyes (no extra model) and, on
MacBooks that report it, the screen's angle. Nothing posture-related is saved.

**On and off.** Posture monitoring is **off** until you tick **Settings › Monitoring › Posture
monitoring** (remembered between launches in `preferences.json`). While it is off nothing
posture-related runs: no measurements, no baseline, no screen-angle readings, no messages.
Ticking it during a session starts the 1-minute baseline straight away; with the camera off,
it starts when monitoring does. Unticking forgets the baseline.

**What is measured** on every frame with a face:

| Value | How | Unit |
| --- | --- | --- |
| Head angle | MediaPipe's facial transformation matrix (4×4), read as R = Rz(roll)·Ry(yaw)·Rx(pitch) | degrees |
| • pitch | nodding; **+ = chin down** | ° |
| • roll | tilting towards a shoulder | ° |
| • yaw | turning sideways (shown, not judged) | ° |
| Distance | `focal length (px) × 11.7 mm ÷ iris width (px)`; iris width = mean horizontal width of both irises (landmarks 469–471, 474–476); focal length = 1.0 × frame width (≈ 53° field of view) | cm (approximate) |
| Face centre | middle of the face's landmarks, top to bottom: 0 = top of the picture, 1 = bottom | fraction of frame height |
| Face size | width of the face's landmarks ÷ frame width | fraction |
| Screen angle | MacBook lid angle sensor (see below), read twice a second | degrees |

The iris is a useful ruler because its visible width is about 11.7 mm in almost every adult.
The focal length is **not measured** for your camera: if the centimetres look off, tune
`FOCAL_LENGTH_PER_FRAME_WIDTH` (0.87 for a 60° camera). The limits compare with your own
baseline, so a constant error in centimetres mostly cancels out, except for the fixed 50 cm limit.

**The posture baseline.** At the start of **every study session**, the **first minute** of work
is recorded: sit the way you want to, at a good distance, and keep working normally (reading is
fine; that's what it should describe). The **median** pitch, roll, distance, face centre, face
size and screen angle become the baseline; posture isn't judged during that minute. Resuming
after a pause keeps it (unless the pause interrupted it, then it starts again).
**Recalibrate posture** records it again (for example after moving your chair or desk) without
touching the eye calibration. It is rejected, and the previous baseline kept, when:
- fewer than **300** frames had everything measured (face mostly out of view), or
- the head angle kept changing: its spread (interquartile range ÷ 1.349) was more than **5°**.
  The interquartile range is used rather than the median deviation because it also notices two
  alternating postures.

It is recorded fresh for each session, rather than once like the 10-minute blink reference
(section 11.7), because posture is measured relative to the camera: a different desk, chair or
screen angle changes it, while blink timing doesn't.

**Limits.** Posture is marked **poor** when one of these has been exceeded for **20 seconds
in a row** (see below for what counts as "in a row"):

| Name | Rule (compared with the baseline) |
| --- | --- |
| head dropped | pitch more than **12°** lower (chin down) |
| head tilted | roll more than **10°** either way |
| too close | closer than **50 cm**, or more than **20 %** closer than in the baseline |
| slumped | face centre more than **5 %** of the frame height lower **and** the face at least **5 %** bigger; with the lid angle sensor, **5 % lower** is enough |

Without the sensor "slumped" needs both, because sliding down in a chair almost always brings
the head forward too, while a face that is only lower could be a tilted screen. With the sensor
the screen tilt is corrected, so lower alone counts.

**Message.** When posture turns poor, a Mac notification (title "Posture") says **"Stop
slouching, hunchbacks are not particularly sexy you know"**, and the same note appears under the
Study page buttons. At most one per poor stretch (it ends when posture is good again; a lost
face doesn't end it) and at least **10 minutes** apart (`POSTURE_REMINDER_GAP_SECONDS`).

Each limit has its own timer. Its count starts again only after being back within the limit for
more than **3 seconds**: the camera's measurements wobble a little from frame to frame, and
near a limit single frames would otherwise keep restarting it. Sitting up for longer than that,
glancing down at your phone or stretching for a few seconds never adds up to 20 s. Frames
without a face (or without a head angle) aren't judged; after more than 3 s without a face all
timers start again, like lost tracking in the blink counter. Pausing resets them too. While a
limit is exceeded but not yet for 20 s, the page shows it with its time so far ("Good · head
dropped for 12 s").

**Screen tilt (MacBooks with a lid angle sensor).** The built-in camera sits in the screen, so
tilting the screen moves your face up or down in the picture (about 2 % of the picture height
per degree) and changes the measured head angle by the same number of degrees. Recent MacBook
Pros have a hinge sensor that macOS exposes as an Apple HID device (vendor 0x05AC, product
0x8104, sensor page 0x20, usage 0x8A); OcuSense reads it directly through IOKit with
synchronous calls only (`ocusense/lid_sensor.py`; no extra package). Apple doesn't document it, so it is optional: on Macs without it,
with an external camera, or if it can't be read, posture uses the camera alone.
- **Small tilts are corrected**: with δ = screen angle now − at the baseline (+ = opened
  further, camera looking more upwards), pitch is taken as `pitch − δ` and the face centre as
  `centre − 1.0 × (width ÷ height) × tan δ`.
- **A clear tilt records a new baseline**: when the screen has moved **5°** or more from the
  baseline's angle and then stayed within ±1° for **2 seconds** (so adjusting it gives one
  message, at the end), a Mac notification says **"You tilted your screen, recalibrating now"**
  (also shown under the Study page buttons), and the 1-minute baseline starts again.

**Not the distance reminder.** The distance reminder (section 13) compares apparent face size
with the eye calibration and reacts after 3 s; the posture "too close" limit uses the
estimated centimetres and the 20 s rule. They can disagree a little.

**Limits of the method.** The head angle and iris points come from a single 2D camera, so
expect a few degrees and several centimetres of noise. Glasses can hide the iris edges. Moving
the laptop higher, to another desk or another chair isn't seen by the lid sensor: press
Recalibrate posture. Posture and screen angles are shown live only and never written to disk.
They describe position, not health.

## 15. Precision and limitations

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

## 16. Where it lives in the code

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
| Comparison with the reference, break reminders | `ocusense/core/baseline_drift.py`, `ocusense/reference.py`, `ocusense/notifications.py` |
| Replaying saved recordings | `ocusense/core/replay.py`, `ocusense/recording_files.py` |
| Saving recordings | `ocusense/recording.py` |
| Exports | `ocusense/exports.py` |
| Distance reminder rules | `ocusense/core/proximity.py` (face size in `core/eye_metrics.py`) |
| Reminder card and macOS notifications | `ocusense/ui/widgets/alert_banner.py`, `ocusense/ui/notifications.py` |
| Posture: head angle, distance, slump, baseline, limits, screen tilt | `ocusense/core/posture.py` (values in `core/models.py`), `ocusense/lid_sensor.py`; on/off in `ocusense/preferences.py` |
| Frame processing per camera frame | `ocusense/monitoring/pipeline.py` |
