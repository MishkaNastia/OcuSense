"""A ~4-minute pitch video of OcuSense: every feature, slowly, without voiceover or captions.

    .venv/bin/python -m examples.make_pitch_video          # → ~/Desktop/OcuSense-pitch.mp4 (+ a silent copy)
    .venv/bin/python -m examples.make_pitch_video --keyframes

Made for talking over during a pitch: short chapter cards, then each feature on screen long
enough to explain it, with a pointer that clicks through the real app. Built from the same
pieces as examples/make_trailer.py (the real window offscreen, its own temporary data folder,
a drawn face instead of the camera, made-up demo friends, the app's labelled demo statistics).
Writes two files: one with soft synthesised background music and one silent.

The website chapter needs the website running (cd website && npm run dev) and Google Chrome:
its pages are captured headless from --website (default http://localhost:3000) with a
throwaway Chrome profile. Without them the chapter is left out.
"""

import argparse
import json
import math
import shutil
import tempfile
import urllib.request
import random
import subprocess
import sys
import time
from pathlib import Path

from examples import make_trailer as T  # isolates every data file and sets the video clock on import

import numpy as np  # noqa: E402
from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QPushButton  # noqa: E402

FPS, W, H, CLOCK, WORK = T.FPS, T.W, T.H, T.CLOCK, T.WORK
INK, PAPER, GRAPHITE = T.INK, T.PAPER, T.GRAPHITE
COBALT, VERMILION, GOLDEN, GREEN = T.COBALT, T.VERMILION, T.GOLDEN, T.GREEN


# ------------------------------------------------------------------ the film, without captions
class Pitch(T.Trailer):
    def app_frame(self, window, caption, t, overlay=None):
        """The app as large as the frame allows (no caption bar), on paper with the drifting confetti."""
        shot = window.grab().toImage()
        img, p = self.canvas(self.time())
        target_h = 1000
        target_w = int(shot.width() * target_h / shot.height())
        x, y = (W - target_w) / 2, 40
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 40))
        p.drawRoundedRect(QRectF(x + 10, y + 14, target_w, target_h), 22, 22)
        p.setBrush(INK)
        p.drawRoundedRect(QRectF(x - 12, y - 12, target_w + 24, target_h + 24), 26, 26)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(x, y, target_w, target_h), 14, 14)
        p.setClipPath(clip)
        p.drawImage(QRectF(x, y, target_w, target_h), shot)
        if overlay is not None:
            overlay(p, QRectF(x, y, target_w, target_h), shot.width())
        p.end()
        return img

    def chapter(self, number, title, subtitle, accent):
        self.card(2.5, f"{number} · {title}", subtitle, eye=False, accent=accent)


class Pointer:
    """A mouse pointer that glides to widgets and clicks them, drawn on top of the app."""

    def __init__(self, window):
        self.window = window
        self.pos = None
        self.clicked_at = -9.0
        self.t = 0.0
        self.plan = []  # [(time, widget, action)] — action None = click the widget

    def reset(self, plan):
        self.plan = sorted(plan, key=lambda item: item[0])
        self.clicked_at = -9.0

    def step(self, t):
        self.t = t
        upcoming = [item for item in self.plan if item[0] >= t - 0.5 / FPS]
        target = upcoming[0][1] if upcoming else (self.plan[-1][1] if self.plan else None)
        if target is not None and target.isVisible():
            c = target.mapTo(self.window, target.rect().center())
            if self.pos is None:
                self.pos = (c.x() + 240.0, c.y() + 140.0)
            x, y = self.pos
            self.pos = (x + (c.x() - x) * 0.14, y + (c.y() - y) * 0.14)
        for at, widget, action in self.plan:
            if abs(t - at) < 0.5 / FPS:
                (action or widget.click)()
                self.clicked_at = t

    def draw(self, p, rect, shot_width):
        if self.pos is None:
            return
        k = rect.width() / shot_width
        x, y = rect.left() + self.pos[0] * k, rect.top() + self.pos[1] * k
        since = self.t - self.clicked_at
        if 0 <= since < 0.5:
            p.setPen(QPen(VERMILION, 4))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(x, y), 14 + since * 70, 14 + since * 70)
        arrow = QPainterPath(QPointF(x, y))
        for dx, dy in ((0, 34), (9, 26), (16, 41), (23, 38), (16, 23), (27, 23)):
            arrow.lineTo(x + dx, y + dy)
        arrow.closeSubpath()
        p.setPen(QPen(QColor("#FFFFFF"), 3))
        p.setBrush(INK)
        p.drawPath(arrow)


def tidy_paths(widget):
    """Show the usual data folder in labels instead of the video's temporary one."""
    real = "~/Library/Application Support/OcuSense"
    for label in widget.findChildren(QLabel):
        text = label.text()
        if str(WORK) in text:
            label.setText(text.replace(str(WORK), real))


CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
WEB_PAGES = (("home", "/", "OcuSense"), ("how", "/how-it-works", "How it works"),
             ("demo", "/demo/sample", "Demo · sample session"), ("download", "/download", "Download"),
             ("signup", "/signup", "Create an account"))


def capture_website(base: str) -> dict:
    """name → (QImage of the whole page, tab title); empty without a running site or Chrome."""
    from PySide6.QtGui import QImage
    try:
        urllib.request.urlopen(base, timeout=5).close()
    except OSError:
        print(f"Website not reachable at {base}: its chapter is left out.")
        return {}
    if not Path(CHROME).exists():
        print("Google Chrome not found: the website chapter is left out.")
        return {}
    folder = Path(tempfile.mkdtemp(prefix="ocusense-web-"))
    pages = {}
    for name, path, title in WEB_PAGES:
        shot = folder / f"{name}.png"
        chrome = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                                   f"--user-data-dir={folder / ('profile-' + name)}", "--window-size=1440,7000",
                                   "--virtual-time-budget=6000", f"--screenshot={shot}", base.rstrip("/") + path],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(60):  # the dev server keeps a connection open, so Chrome may not exit by itself
            if shot.exists() and shot.stat().st_size > 0:
                time.sleep(2)
                break
            time.sleep(1)
        chrome.kill()
        chrome.wait()
        if not shot.exists():
            continue
        img = QImage(str(shot)).convertToFormat(QImage.Format.Format_RGB888)
        w, h = img.width(), img.height()
        arr = np.frombuffer(img.constBits(), dtype=np.uint8).reshape(h, img.bytesPerLine())[:, :w * 3]
        core = arr.reshape(h, w, 3)[:, 120:w - 40].astype(int)  # the left edge holds the dev-server badge
        rows = np.where(np.abs(core - core[h - 300, 200]).sum(axis=2).max(axis=1) > 30)[0]
        rows = rows[rows < h - 200]
        bottom = min(h, int(rows.max()) + 60) if len(rows) else h
        pages[name] = (img.copy(0, 0, w, bottom), title)
    shutil.rmtree(folder, ignore_errors=True)
    return pages


def browser_scene(film, page, title, path, seconds, hold=1.2):
    """A browser window showing `page`, scrolling slowly from the top to the bottom."""
    n = film.length(seconds, "")
    bar = 64
    for i in range(n):
        t = i / FPS
        img, p = film.canvas(film.time())
        bw, bh = 1600, 1000
        x, y = (W - bw) / 2, 40
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 40))
        p.drawRoundedRect(QRectF(x + 10, y + 14, bw, bh), 22, 22)
        p.setBrush(QColor("#E9E6DF"))
        p.drawRoundedRect(QRectF(x, y, bw, bh), 18, 18)
        for k, colour in enumerate(("#FF5F57", "#FEBC2E", "#28C840")):
            p.setBrush(QColor(colour))
            p.drawEllipse(QPointF(x + 30 + k * 26, y + bar / 2), 8, 8)
        p.setBrush(QColor("#FFFFFF"))
        p.drawRoundedRect(QRectF(x + 520, y + 14, 560, bar - 28), 18, 18)
        p.setFont(T.font(20, QFont.Weight.Medium))
        p.setPen(GRAPHITE)
        p.drawText(QRectF(x + 520, y + 14, 560, bar - 28), Qt.AlignmentFlag.AlignCenter, f"OcuSense  ·  {path}")
        view = QRectF(x, y + bar, bw, bh - bar)
        k = bw / page.width()
        visible = view.height() / k  # page pixels that fit
        travel = max(0.0, page.height() - visible)
        top = travel * T.ease((t - hold) / max(0.1, seconds - hold - 1.0))
        clip = QPainterPath()
        clip.addRoundedRect(view, 0, 0)
        p.setClipPath(clip)
        p.drawImage(view, page, QRectF(0, top, page.width(), visible))
        p.setClipping(False)
        p.end()
        film.emit(film.fade(img, i, n), path if i == n // 2 else "")


def buttons(segmented):
    return segmented.findChildren(QPushButton)


def smooth_scroll(area, start, end, t, t0, t1):
    bar = area.verticalScrollBar()
    bar.setValue(int(start + (end - start) * T.ease((t - t0) / max(0.01, t1 - t0))))


def seed_time_log():
    """A believable week of study in the Time log."""
    from datetime import datetime, timedelta
    from ocusense.core.timelog import TimeLog
    log = TimeLog()
    subjects = [log.add_subject("Biology 210", "subject", "green"), log.add_subject("Machine Learning", "subject",
                "cobalt"), log.add_subject("Linear Algebra", "subject", "golden"),
                log.add_subject("OcuSense", "project", "vermilion")]
    rng = random.Random(4)
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    for day in range(6, -1, -1):
        start = today - timedelta(days=day) + timedelta(hours=9, minutes=rng.randint(0, 40))
        for _ in range(rng.randint(2, 4)):
            subject = rng.choice(subjects)
            length = timedelta(minutes=rng.choice((25, 40, 50, 75, 90)))
            if start + length > datetime.now():
                break
            log.add_entry(subject.id, start.timestamp(), (start + length).timestamp(),
                          rng.choice(("Lecture notes", "Exercise sheet", "Reading", "Coding", "Exam prep")))
            start += length + timedelta(minutes=rng.randint(10, 60))
    (WORK / "timelog.json").write_text(json.dumps(log.to_dict()))


# ------------------------------------------------------------------ main
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=Path.home() / "Desktop" / "OcuSense-pitch.mp4")
    parser.add_argument("--keyframes", action="store_true")
    parser.add_argument("--website", default="http://localhost:3000", help="the running OcuSense website")
    args = parser.parse_args(argv)

    app = QApplication.instance() or QApplication([])
    from ocusense.core.blink_counter import BlinkCounter
    from ocusense.core.calibration import GuidedCalibration
    from ocusense.core.history import ScoreHistory
    from ocusense.core.models import FrameObservation, PostureStatus
    from ocusense.core.morse import MORSE
    from ocusense.core import runner as R
    from ocusense.monitoring.camera_worker import MonitorUpdate
    from ocusense.monitoring.pipeline import CALIBRATION_DONE, CLOSED_STEP_FINISHED
    from ocusense.ui import main_window as mw
    from ocusense.ui import theme, window_chrome

    website = capture_website(args.website)
    app.setApplicationName("OcuSense")
    app.setStyle("Fusion")
    app.setStyleSheet(theme.STYLE_SHEET)
    window_chrome.install(app)
    QApplication.beep = staticmethod(lambda: None)  # the calibration "open your eyes" beep
    T.seed_garden()
    seed_time_log()
    service = T.make_account_service()
    mw.AccountService = lambda: service
    window = mw.MainWindow(demo_history=True)
    window.notify = lambda message, title: None
    window.resize(1440, 900)
    window.show()
    app.processEvents()
    for i, score in enumerate((640, 1105, 480, 920, 300)):
        window.games_page.scores.book.record("eye_runner", score, now=time.time() - 86400 * i)
    for i, score in enumerate((420, 310, 255)):
        window.games_page.scores.book.record("blink_code_challenge", score, now=time.time() - 86400 * (i + 1))

    keyframes = None
    if args.keyframes:
        keyframes = args.out.with_suffix("")
        keyframes.mkdir(parents=True, exist_ok=True)
    film = Pitch(WORK / "pitch.mp4", keyframes)
    pointer = Pointer(window)

    # ---------------- opening
    film.card(4.0, "OcuSense", "your eyes' study buddy")

    # ================= 1. study
    film.chapter(1, "Study with a buddy", "Calibrate once, then it watches your blinks while you work", COBALT)
    thread = T.FakeThread()
    window._start_camera = lambda: (setattr(window, "thread", thread), True)[1]
    window.monitor.calibration = None
    window.show_page("study")
    window.start()  # no calibration yet → the guided calibration
    steps = [(0, 4.0), (1, 4.0), (2, 3.0)]  # (step, seconds) as GuidedCalibration walks them

    def calibrate(i, t):
        elapsed, step, left = t, 0, 0.0
        for index, length in steps:
            if elapsed < length:
                step, left = index, length - elapsed
                break
            elapsed -= length
        else:
            step, left = 2, 0.0
        value = 0.04 if step == 1 and left < 3.2 else (T.blink_curve(t, every=0.9) if step == 2 else 0.95)
        events = [CLOSED_STEP_FINISHED] if step == 2 and abs(elapsed) < 1 / FPS else []
        window._on_update(MonitorUpdate(
            now=time.monotonic(), face_found=True, reliable=True, reason="", openness=None, blinked=False,
            events=events, blinks=0, calibrated=False, cal_status=GuidedCalibration.RUNNING, cal_step=step,
            cal_measuring=left < 3.0, cal_seconds_left=max(0.0, left), cal_error="", samples=[],
            preview=T.cartoon_face(value, t), source=thread))

    film.scene(11.0, window, "", calibrate, label="calibration")
    window.monitor.calibration = object()
    window._on_update(MonitorUpdate(now=time.monotonic(), face_found=True, reliable=True, reason="", openness=None,
                                    blinked=False, events=[CALIBRATION_DONE], blinks=0, calibrated=True,
                                    cal_status="done", cal_step=None, cal_measuring=False, cal_seconds_left=0,
                                    cal_error="", samples=[], preview=T.cartoon_face(0.95, 0), source=thread))

    counter, history = BlinkCounter(), ScoreHistory()
    blinks, current = [0], {"value": 0.95, "t": 0.0}
    env = {"zoom": 1.0, "slump": 0.0, "dark": 0.0, "posture": None}
    still = T.cartoon_face(0.95, 0.0)

    def feed(t, show_face=True):
        now = time.monotonic()
        value = T.blink_curve(t, every=3.1 if t < 0 else 2.6)
        current.update(value=value, t=t)
        before = counter.state
        blinked = counter.update(value)
        blinks[0] += blinked
        history.add(now, (value, value, value), blinked)
        obs = FrameObservation(t=now, valid=True, left_raw=value, right_raw=value, left_ear=0.3 * value,
                               right_ear=0.3 * value, detector_closed=counter.state == BlinkCounter.CLOSED,
                               closing_started=before == BlinkCounter.OPEN and counter.state == BlinkCounter.CLOSED,
                               blink_completed=blinked)
        posture = env["posture"]
        window._on_update(MonitorUpdate(
            now=now, face_found=True, reliable=True, reason="", openness=(value,) * 3, blinked=blinked, events=[],
            blinks=blinks[0], calibrated=True, cal_status="done", cal_step=None, cal_measuring=False,
            cal_seconds_left=0, cal_error="", samples=list(history.samples) if t > -12 else [],
            preview=T.cartoon_face(value, t, env["zoom"], env["slump"], env["dark"]) if show_face else still,
            source=thread, observation=obs, closeness=env["zoom"], brightness=130 - 110 * env["dark"],
            posture_enabled=posture is not None, posture_status=posture))

    def preroll(seconds, start_t):
        for k in range(int(seconds * FPS)):
            feed(start_t + k / FPS, show_face=False)
            CLOCK.advance()
            if k % 30 == 0:
                window._tick()

    def bubble(p, rect, shot_width):
        r = 120
        cx, cy = rect.right() - r - 30, rect.bottom() - r - 30
        clip = QPainterPath()
        clip.addEllipse(QPointF(cx, cy), r, r)
        p.save()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 50))
        p.drawEllipse(QPointF(cx + 6, cy + 8), r, r)
        p.setClipPath(clip)
        p.drawImage(QRectF(cx - r * 1.33, cy - r, r * 2.67, r * 2),
                    T.cartoon_face(current["value"], current["t"], env["zoom"], env["slump"], env["dark"]))
        p.setClipping(False)
        p.setPen(QPen(INK, 6))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), r, r)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(VERMILION)
        p.drawEllipse(QPointF(cx - r * 0.72, cy - r * 0.72), 11, 11)
        p.restore()

    def with_pointer_and_bubble(p, rect, shot_width):
        bubble(p, rect, shot_width)
        pointer.draw(p, rect, shot_width)

    preroll(24 * 60, -24 * 60)  # 24 minutes into a study session
    study = window.study
    study_max = [0]

    def study_tour(i, t):
        feed(t)
        study_max[0] = study_max[0] or study.verticalScrollBar().maximum()
        if t < 5:
            smooth_scroll(study, 0, 0, t, 0, 1)
        elif t < 8:
            smooth_scroll(study, 0, study_max[0], t, 5, 8)  # down to the last-60-seconds numbers
        else:
            smooth_scroll(study, study_max[0], 0, t, 11, 13.5)

    film.scene(14.0, window, "", study_tour, overlay=bubble, label="study")

    window.show_page("current")
    current_page = window.current_page
    panel = current_page.distributions
    metric_buttons = buttons(panel.metric_switch)
    pointer.pos = None
    pointer.reset([(2.5 + 1.6 * k, b, None) for k, b in enumerate(metric_buttons[:5])])
    target = [0]

    def current_tour(i, t):
        feed(t + 100)
        if i == 0:
            target[0] = panel.mapTo(current_page.widget(), panel.rect().topLeft()).y() - 60
        smooth_scroll(current_page, 0, target[0], t, 0.3, 2.2)
        pointer.step(t)

    film.scene(12.0, window, "", current_tour, overlay=pointer.draw, label="current-session")
    window.show_page("study")
    study.verticalScrollBar().setValue(0)

    # ================= 2. your body
    film.chapter(2, "Your body counts too", "Distance, posture, light and rest: gentle nudges, all optional",
                 GREEN)
    offset = [1000.0]

    def acted(direct):
        def step(i, t):
            direct(t)
            study.verticalScrollBar().setValue(0)
            feed(offset[0] + t)
        return step

    film.scene(8.0, window, "", acted(lambda t: env.update(zoom=1.0 + 0.9 * T.ease((t - 0.5) / 0.8))),
               overlay=bubble, label="distance")
    env.update(zoom=1.0)
    preroll(1.5, 2000)
    poor, upright = PostureStatus(tracked=True, poor=True, problems=("head dropped",)), PostureStatus(tracked=True)
    film.scene(8.0, window, "", acted(lambda t: env.update(slump=T.ease((t - 0.3) / 1.0),
                                                            posture=poor if t > 1.2 else upright)),
               overlay=bubble, label="posture")
    env.update(slump=0.0, posture=upright)
    preroll(1.0, 3000)
    env["posture"] = None
    study.message_label.setText("")
    window.settings_page.lighting.setChecked(True)
    env["dark"] = 1.0
    preroll(57, 4000)
    film.scene(8.0, window, "", acted(lambda t: env.update(dark=1.0)), overlay=bubble, label="lighting")
    env["dark"] = 0.0
    preroll(1.5, 5000)
    window.lighting_card.setVisible(False)
    window.settings_page.eye_rest.setChecked(True)  # 20-20-20: after 20 monitored minutes
    preroll(20 * 60 + 2, 6000)
    film.scene(8.0, window, "", acted(lambda t: None), overlay=bubble, label="eye-rest")
    window.eye_rest_card.setVisible(False)

    window.show_page("settings")
    settings = window.settings_page
    app.processEvents()
    settings.verticalScrollBar().setValue(0)
    y_of = lambda w: w.mapTo(settings.widget(), w.rect().topLeft()).y()  # noqa: E731
    reminders_y = max(0, y_of(settings.reminders) - 200)
    theme_y = max(0, y_of(settings.lighting) + 40)
    pointer.pos = None
    pointer.reset([(2.0, settings.posture, None), (5.6, settings.eye_rest, None), (6.6, settings.eye_rest, None),
                   (7.8, settings.distance, None), (8.8, settings.distance, None)])

    def settings_tour(i, t):
        tidy_paths(settings)
        if t < 4:
            smooth_scroll(settings, 0, 0, t, 0, 1)
        elif t < 5:
            smooth_scroll(settings, 0, reminders_y, t, 4, 5)
        elif t > 10:
            smooth_scroll(settings, reminders_y, theme_y, t, 10, 12)
        pointer.step(t)

    film.scene(15.0, window, "", settings_tour, overlay=pointer.draw, label="settings")
    settings.posture.setChecked(False)

    # ================= 3. focus
    film.chapter(3, "Focus", "A Pomodoro timer and a time log for every subject", GOLDEN)
    window.show_page("pomodoro")
    pomodoro = window.pomodoro_page
    presets = buttons(pomodoro.presets)
    pointer.pos = None
    pointer.reset([(1.6, presets[1], None), (3.4, presets[2], None), (5.0, presets[0], None),
                   (6.6, pomodoro.main_button, None)])
    film.scene(10.0, window, "", lambda i, t: pointer.step(t), overlay=pointer.draw, label="pomodoro")

    window.show_page("time_log")
    log_page = window.time_log_page
    switches = log_page.findChildren(type(pomodoro.presets))
    periods = next((sw for sw in switches if any("week" in b.text().lower() for b in buttons(sw))), None)
    period_buttons = buttons(periods) if periods else []
    log_max = [0]
    pointer.pos = None
    pointer.reset([(6.5 + 1.0 * k, b, None) for k, b in enumerate(period_buttons[:4])])

    def time_log_tour(i, t):
        log_max[0] = log_max[0] or log_page.verticalScrollBar().maximum()
        if t < 6:
            smooth_scroll(log_page, 0, log_max[0], t, 1.5, 5.5)
        pointer.step(t)

    film.scene(10.0, window, "", time_log_tour, overlay=pointer.draw, label="time-log")

    # ================= 4. breaks
    film.chapter(4, "Breaks that are actually fun", "Three games you play with your eyes, and leaderboards",
                 VERMILION)
    window.stop()  # the study session ends here (its recap comes at the end)
    summary_card = window.summary_card
    if summary_card is not None:
        summary_card.hide()
    window.show_page("games")
    page = window.games_page
    page.verticalScrollBar().setValue(0)
    film.scene(4.0, window, "", label="games-hub")

    page.open_eye_runner()
    runner = page.eye_runner
    runner.frames.stop()
    game = runner.game
    game.rng = random.Random(11)
    game.jump()
    game.score = 240
    game.highscore = 1105
    crash_at = 13.5

    def play_runner(i, t):
        p = game.player
        ahead = [o for o in game.obstacles if o.rect.right > p.x - 10 and o.kind in ("ground", "low")]
        runner.canvas.eyes_closed = False
        if ahead and t < crash_at - 0.6:
            o = min(ahead, key=lambda o: o.rect.x)
            gap = o.rect.x - (p.x + 34)
            if 0 < gap < game.speed * 0.2 and p.on_ground:
                game.jump()
                runner.canvas.eyes_closed = True
            elif o.kind == "low" and not p.on_ground and p.vy > 0 and 0 < gap < 60:
                game.jump()
        if t >= crash_at - 0.6 and game.state == "play" and not any(o.rect.x < 400 for o in game.obstacles):
            game.obstacles.append(R.Obstacle(p.x + 120, "ground", game.sizes.obstacles[0], game.rng))
        runner.canvas.eyes = "eyes closed" if runner.canvas.eyes_closed else "eyes open"
        if game.state == "over":
            game.over_timer += 1 / FPS
        game.update(1 / FPS, False)
        runner.canvas.update()

    film.scene(16.0, window, "", play_runner, label="eyegame")

    page.show_hub()
    page.open_blink_code()
    code = page.blink_code
    code.set_input("keys")
    code.set_mode("learn")

    def learn(i, t):
        if i % 20 == 10:
            letter = code.learn.target
            code._letter(letter, MORSE[letter])

    film.scene(8.0, window, "", learn, label="blinkcode-learn")
    code.set_mode("challenge")
    code.start_challenge()

    def challenge(i, t):
        if i % 12 == 6 and code.challenge.started_at is not None:
            letter = code.challenge.expected
            code._letter(letter, MORSE[letter])

    film.scene(9.0, window, "", challenge, label="blinkcode-challenge")
    page.show_hub()
    page.open_blink_garden()
    garden = page.blink_garden
    film.scene(8.0, window, "", label="garden")
    garden.open_shop()
    shop = garden.shop_dialog
    app.processEvents()

    def shop_overlay(p, rect, shot_width):
        if shop is None:
            return
        card = shop.grab().toImage()
        k = rect.width() / shot_width
        cw, ch = card.width() * k, card.height() * k
        p.fillRect(rect, QColor(0, 0, 0, 70))
        p.drawImage(QRectF(rect.center().x() - cw / 2, rect.center().y() - ch / 2, cw, ch), card)

    film.scene(5.0, window, "", overlay=shop_overlay, label="garden-shop")
    if shop is not None:
        shop.reject()
    page.show_hub()

    board = page.leaderboard
    board.set_game("eye_runner")
    board.set_scope("mac")
    game_buttons, scope_buttons = buttons(board.game_switch), buttons(board.scope_switch)
    pointer.pos = None
    pointer.reset([(2.0, scope_buttons[1], None), (4.5, scope_buttons[2], None), (7.0, game_buttons[0], None),
                   (8.5, scope_buttons[1], None)])
    film.scene(10.0, window, "", lambda i, t: pointer.step(t), overlay=pointer.draw, label="leaderboards")
    window.show_page("account")
    window.account_page.verticalScrollBar().setValue(10 ** 6)
    friends_panel = window.account_page.friends
    accept = [b for b in friends_panel.findChildren(QPushButton) if b.text() == "Accept"]
    pointer.pos = None
    pointer.reset([(3.0, accept[0], None)] if accept else [])
    film.scene(6.0, window, "", lambda i, t: pointer.step(t), overlay=pointer.draw, label="friends")

    # ================= 5. make it yours
    film.chapter(5, "Make it yours", "Spend garden coins on paintings and pick a theme", COBALT)
    window.show_page("library")
    library = window.library_page
    lib_max = [0]

    def gallery_tour(i, t):
        lib_max[0] = lib_max[0] or library.verticalScrollBar().maximum()
        smooth_scroll(library, 0, min(lib_max[0], 900), t, 3, 8)

    film.scene(10.0, window, "", gallery_tour, label="gallery")
    window.show_page("settings")
    theme_switch = next((s for s in settings.findChildren(type(pomodoro.presets)) if "Keith" in
                         " ".join(b.text() for b in buttons(s))), None)
    settings.verticalScrollBar().setValue(theme_y)
    app.processEvents()
    haring_button = next((b for b in buttons(theme_switch) if "Keith" in b.text()), None) if theme_switch else None
    pointer.pos = None
    pointer.reset([(1.5, haring_button, None)] if haring_button else [(1.5, settings, lambda: window.apply_theme("haring"))])

    def haring_tour(i, t):
        tidy_paths(settings)
        pointer.step(t)
        if abs(t - 3.5) < 0.5 / FPS:
            window.show_page("games")
            page.verticalScrollBar().setValue(0)
        if abs(t - 6.0) < 0.5 / FPS:
            window.show_page("pomodoro")
        if abs(t - 8.3) < 0.5 / FPS:
            window.show_page("library")
            library.verticalScrollBar().setValue(0)

    film.scene(10.0, window, "", haring_tour, overlay=pointer.draw, label="haring")
    window.apply_theme("miro")

    # ================= 6. progress
    film.chapter(6, "See your progress", "Every session adds to your statistics, with a recap at the end", GREEN)
    window.show_page("all_time")
    stats = window.stats_page
    stats_max = [0]
    stat_buttons = buttons(stats.metric_switch) if hasattr(stats, "metric_switch") else []
    pointer.pos = None
    pointer.reset([(2.0 + 1.5 * k, b, None) for k, b in enumerate(stat_buttons[1:3] + stat_buttons[:1])])

    def stats_tour(i, t):
        stats_max[0] = stats_max[0] or stats.verticalScrollBar().maximum()
        if t > 7:
            smooth_scroll(stats, 0, stats_max[0], t, 7, 11.5)
        pointer.step(t)

    film.scene(12.0, window, "", stats_tour, overlay=pointer.draw, label="statistics")
    stats.verticalScrollBar().setValue(0)
    if summary_card is not None:
        summary_card.show()
        app.processEvents()

        def card_overlay(p, rect, shot_width):
            card = summary_card.grab().toImage()
            k = rect.width() / shot_width
            cw, ch = card.width() * k, card.height() * k
            p.fillRect(rect, QColor(0, 0, 0, 70))
            p.drawImage(QRectF(rect.center().x() - cw / 2, rect.center().y() - ch / 2, cw, ch), card)

        film.scene(7.0, window, "", overlay=card_overlay, label="summary")
        summary_card.close()

    # ================= 7. the website
    if website:
        film.chapter(7, "The website", "Learn how it works, try it in the browser, download the app", VERMILION)
        for name, seconds in (("home", 8.0), ("how", 5.0), ("demo", 5.0), ("download", 4.5), ("signup", 4.0)):
            if name in website:
                page, title = website[name]
                path = dict((n, pth) for n, pth, _ in WEB_PAGES)[name]
                browser_scene(film, page, title, path if path != "/" else "home", seconds)

    # ---------------- closing
    film.card(3.0, "Blink more. Stress less.", "OcuSense · made by students, for tired student eyes")
    film.call_to_action(9.0)
    seconds = film.frames / FPS
    film.close()
    window.close()

    # soft background music (a pitch is talked over) and a silent copy
    music = T.make_music(seconds) * 0.35
    track = WORK / "music.wav"
    with T.wave.open(str(track), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(44100)
        f.writeframes((music * 32767).astype(np.int16).tobytes())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    silent = args.out.with_name(args.out.stem + "-silent.mp4")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(film.video_path), "-i", str(track), "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", str(args.out)], check=True)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(film.video_path), "-c:v", "copy",
                    "-movflags", "+faststart", str(silent)], check=True)
    T.shutil.rmtree(WORK, ignore_errors=True)
    print(f"{args.out}  ·  {seconds / 60:.0f} min {seconds % 60:.0f} s, {W}×{H}\n{silent}  ·  the same, no sound")
    return 0


if __name__ == "__main__":
    sys.exit(main())
