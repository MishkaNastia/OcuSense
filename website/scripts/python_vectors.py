"""Generate shared test vectors from the desktop app's Python implementation.

The website's TypeScript port must reproduce these results exactly
(see src/lib/measurement/__tests__/parity.test.ts).

Run from the repository root with the desktop app's environment:
    .venv/bin/python website/scripts/python_vectors.py
"""

import json
import random
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from ocusense.core.blink_counter import BlinkCounter  # noqa: E402
from ocusense.core.calibration import (  # noqa: E402
    CalibrationError, GuidedCalibration, build_eye_reference, robust_reference,
)
from ocusense.core.eye_metrics import EYE_LANDMARKS, eye_aspect_ratio, measure_eyes  # noqa: E402
from ocusense.core.measurements import MeasurementTracker, RollingWindow, combined_openness_percent  # noqa: E402
from ocusense.core.models import FrameObservation  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "src" / "lib" / "measurement" / "__tests__" / "python-vectors.json"
rng = random.Random(2026)


def r6(x):
    return None if x is None else round(x, 9)


def fake_landmarks(eyes):
    points = [SimpleNamespace(x=0.5, y=0.5) for _ in range(478)]
    for name, (cx, cy, w, h) in eyes.items():
        p1, p2, p3, p4, p5, p6 = EYE_LANDMARKS[name]
        for index, (x, y) in {
            p1: (cx - w / 2, cy), p4: (cx + w / 2, cy),
            p2: (cx - w / 6, cy - h / 2), p3: (cx + w / 6, cy - h / 2),
            p6: (cx - w / 6, cy + h / 2), p5: (cx + w / 6, cy + h / 2),
        }.items():
            points[index] = SimpleNamespace(x=x, y=y)
    return points


vectors = {}

# 1. EAR
ear_cases = []
for _ in range(20):
    pts = [(round(rng.uniform(0, 200), 4), round(rng.uniform(0, 200), 4)) for _ in range(6)]
    ear_cases.append({"points": pts, "ear": r6(eye_aspect_ratio(pts))})
vectors["ear"] = ear_cases

# 2. measure_eyes (pixel coordinates, reliability)
measure_cases = []
for eyes, size in [
    ({"left": (0.4, 0.5, 0.1, 1 / 30), "right": (0.6, 0.5, 0.1, 1 / 30)}, (640, 480)),
    ({"left": (0.4, 0.5, 0.1, 0.03), "right": (0.6, 0.5, 0.04, 0.012)}, (640, 480)),
    ({"left": (0.48, 0.5, 0.01, 0.003), "right": (0.52, 0.5, 0.01, 0.003)}, (640, 480)),
    ({"left": (0.0, 0.5, 0.1, 0.03), "right": (0.2, 0.5, 0.1, 0.03)}, (640, 480)),
    ({"left": (0.42, 0.45, 0.07, 0.02), "right": (0.58, 0.46, 0.065, 0.021)}, (1280, 720)),
]:
    lm = fake_landmarks(eyes)
    m = measure_eyes(lm, *size)
    used = sorted({i for idx in EYE_LANDMARKS.values() for i in idx})
    measure_cases.append({
        "landmarks": {str(i): [lm[i].x, lm[i].y] for i in used},
        "width": size[0], "height": size[1],
        "ears": {k: r6(v) for k, v in m.ears.items()}, "reliable": m.reliable, "reason": m.reason,
    })
vectors["measure_eyes"] = measure_cases

# 3. robust reference
vectors["robust_reference"] = []
for n in (5, 6, 15, 40):
    samples = [round(rng.gauss(0.28, 0.01), 6) for _ in range(n)] + [0.05]
    med, spread = robust_reference(samples)
    vectors["robust_reference"].append({"samples": samples, "median": r6(med), "spread": r6(spread)})

# 4. eye references (accepted and rejected)
ref_cases = []
for open_mu, closed_mu, n, noise in [(0.30, 0.10, 40, 0.004), (0.30, 0.27, 40, 0.004), (0.30, 0.10, 5, 0.004),
                                     (0.30, 0.10, 40, 0.06), (0.22, 0.08, 30, 0.003)]:
    o = [round(rng.gauss(open_mu, noise), 6) for _ in range(n)]
    c = [round(rng.gauss(closed_mu, noise), 6) for _ in range(n)]
    try:
        ref = build_eye_reference("left", o, c)
        ref_cases.append({"open": o, "closed": c, "ok": True, "openEar": r6(ref.open_ear), "closedEar": r6(ref.closed_ear),
                          "raw": [[e, r6(ref.raw_openness(e))] for e in (0.05, 0.15, 0.25, 0.40)]})
    except CalibrationError as error:
        ref_cases.append({"open": o, "closed": c, "ok": False, "error": str(error)})
vectors["eye_reference"] = ref_cases

# 5. detector decisions on a noisy sequence
seq = []
for i in range(3000):
    if rng.random() < 0.02:
        seq.append(None)
    else:
        phase = (i / 30) % 3.3
        base = 0.05 if phase < 0.2 else (0.5 if 1.5 < phase < 1.7 else 0.92)
        seq.append(round(min(1.0, max(0.0, base + rng.gauss(0, 0.05))), 4))
counter = BlinkCounter()
decisions = []
for v in seq:
    b = counter.update(v)
    decisions.append([b, counter.state])
vectors["detector"] = {"input": seq, "decisions": decisions, "count": counter.count}

# 6. guided calibration
def simulate(open_ear, closed_ear, blink_ears, lose=lambda t: False):
    cal = GuidedCalibration()
    cal.start(0.0)
    frames, now = [], 0.0
    while cal.status == GuidedCalibration.RUNNING and now < 120:
        step = cal.step
        t = now - cal._step_start - step.get_ready_seconds
        ear = open_ear if (step.name == "open" or t < 0) else closed_ear if step.name == "closed" else blink_ears(t)
        ears = None if lose(now) else {"left": round(ear + rng.gauss(0, 0.002), 5), "right": round(ear * 0.9 + rng.gauss(0, 0.002), 5)}
        frames.append([now, ears])
        cal.update(now, ears)
        now = round(now + 1 / 30, 6)  # the exact times stored in the vectors
    result = {"status": cal.status, "error": cal.error}
    if cal.result:
        result.update(left=[r6(cal.result.left.open_ear), r6(cal.result.left.closed_ear)],
                      right=[r6(cal.result.right.open_ear), r6(cal.result.right.closed_ear)])
    return {"frames": frames, "result": result}


def five_blinks(t):
    return 0.09 if (t % 1.0) < 0.15 else 0.30


vectors["calibration"] = [
    simulate(0.30, 0.10, five_blinks),
    simulate(0.30, 0.29, five_blinks),
    simulate(0.30, 0.10, lambda t: 0.30),
    simulate(0.30, 0.10, five_blinks, lose=lambda now: 4.0 <= now < 4.5),
]

# 7. measurements: observations from the real detector, then rolling snapshots
def observations():
    counter, out, t = BlinkCounter(), [], 0.0
    while t < 95:
        rel = t
        if 20 <= rel < 24 or (50 <= rel < 50.6 and rng.random() < 0.9):
            value = None
        elif 30 <= rel < 34:
            value = 0.03  # prolonged closure
        elif (rel % 3.1) < 0.2:
            value = 0.04
        else:
            value = round(0.9 + rng.gauss(0, 0.03), 4)
        before = counter.state
        blinked = counter.update(value)
        after = counter.state
        left = None if value is None else round(value + 0.05, 4)
        right = None if value is None else round(value - 0.05, 4)
        out.append(FrameObservation(t=t, valid=value is not None, left_raw=left, right_raw=right,
                                    detector_closed=after == BlinkCounter.CLOSED,
                                    closing_started=before == BlinkCounter.OPEN and after == BlinkCounter.CLOSED,
                                    blink_completed=blinked))
        # irregular frame timing, including a 1.2 s stall
        t = round(t + (1.2 if 70 <= t < 70.04 else 1 / 30 + rng.uniform(-0.004, 0.004)), 5)
    return out


obs = observations()
tracker, window, snaps = MeasurementTracker(), RollingWindow(0.0), []
checkpoints = {10.0, 25.0, 40.0, 61.0, 75.0, 94.0}
for o in obs:
    window.add(tracker.add(o))
    for cp in sorted(checkpoints):
        if o.t >= cp:
            s = window.snapshot(o.t)
            snaps.append({"after_t": o.t, **{k: r6(v) if isinstance(v, float) else v for k, v in s.__dict__.items()}})
            checkpoints.discard(cp)
            break
vectors["measurements"] = {
    "observations": [[o.t, o.valid, o.left_raw, o.right_raw, o.detector_closed, o.closing_started, o.blink_completed] for o in obs],
    "snapshots": snaps,
}
vectors["combined_percent"] = [[a, b, r6(combined_openness_percent(a, b))]
                               for a, b in [(0.5, 0.5), (1.3, 0.6), (-0.2, 0.4), (None, 0.5), (0.8, None)]]

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(vectors, separators=(",", ":")))
print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)")
