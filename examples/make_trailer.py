"""A ~1-minute trailer of OcuSense, made from the real app (no camera, no screen recording).

    .venv/bin/python -m examples.make_trailer                      # → ~/Desktop/OcuSense-trailer.mp4
    .venv/bin/python -m examples.make_trailer --out trailer.mp4 --keyframes   # also saves a PNG per scene

The real MainWindow runs invisibly ("offscreen") with its own temporary data folder, so
the person's calibration, recordings, scores and garden are never read or changed. A
drawn cartoon face stands in for the camera and its blinks drive the live graph, as real
frames would. Demo friends on the leaderboard are made up (a fake account service), and
Statistics uses the app's own labelled demo sessions. The music is synthesised here
(no samples), and the voiceover is macOS text-to-speech (`say`; --voice picks the voice,
e.g. "Ava (Premium)" once installed in System Settings › Accessibility › Spoken Content),
so the video has no third-party audio. Every scene lasts at least as long as its line, and
the music dips while the voice speaks. Needs ffmpeg on the PATH.
"""

import argparse
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

# Isolate EVERYTHING the app saves before it is imported.
WORK = Path(tempfile.mkdtemp(prefix="ocusense-trailer-"))
for key, name in (("OCUSENSE_RECORDINGS_DIR", "recordings"), ("OCUSENSE_PREFERENCES_FILE", "preferences.json"),
                  ("OCUSENSE_CALIBRATION_FILE", "calibration.json"), ("OCUSENSE_ACCOUNT_FILE", "account.json"),
                  ("OCUSENSE_REFERENCE_FILE", "reference.json"), ("OCUSENSE_SCORES_FILE", "scores.json"),
                  ("OCUSENSE_TIMELOG_FILE", "timelog.json"), ("OCUSENSE_GARDEN_FILE", "garden.json")):
    os.environ[key] = str(WORK / name)
os.environ.update(QT_QPA_PLATFORM="offscreen", OCUSENSE_NO_NOTIFICATIONS="1", OCUSENSE_NO_LID_SENSOR="1")

import numpy as np  # noqa: E402
from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

W, H, FPS = 1920, 1080, 30


class VideoClock:
    """time.monotonic() for the app = video time, so timers and live numbers run at film speed."""

    def __init__(self):
        self.value = time.monotonic()

    def __call__(self):
        return self.value

    def advance(self, seconds=1 / FPS):
        self.value += seconds


CLOCK = VideoClock()
time.monotonic = CLOCK  # every module that calls time.monotonic() now reads the video clock
PAPER, INK, GRAPHITE = QColor("#F6F0E1"), QColor("#1A1714"), QColor("#5A5148")
COBALT, VERMILION, GOLDEN, GREEN = QColor("#1F43B8"), QColor("#D2381F"), QColor("#F2B705"), QColor("#2E7A4D")


# ------------------------------------------------------------------ the voiceover script (one line per scene)
VOICEOVER = {
    "intro": "Meet OcuSense. Your eyes' new study buddy.",
    "problem": "Let's be honest. You stare at screens for hours, and your eyes forget to blink.",
    "study": "OcuSense counts your blinks while you study. Just numbers. Never photos.",
    "body": "And your body counts too.",
    "distance": "Leaning in way too close? It'll gently tell you to back off.",
    "posture": "Slouching like a question mark? It notices that too.",
    "lighting": "Studying in a cave? It suggests a lamp.",
    "settings": "And every reminder has its own switch. On, off. You're the boss.",
    "pomodoro": "Focus in rounds, with the built-in Pomodoro timer.",
    "break": "Break time? Play games... with your eyes.",
    "games-hub": "Pick one.",
    "eyegame": "In EyeGame, you blink to jump. And yes. Those are toilets.",
    "blinkcode": "Blink Code teaches you Morse code. With your eyelids.",
    "garden": "Grow a little garden with gentle eye exercises.",
    "leaderboard": "Then climb the leaderboard, and beat your friends.",
    "friends": "Add friends by username. That's all they ever see.",
    "gallery": "Collect paintings, and change the whole look in one click.",
    "haring": "Keith Haring mode. Because why not.",
    "stats": "See how your eyes did. No judgement. Just numbers.",
    "summary": "And every session ends with a little recap.",
    "outro": "Blink more. Stress less.",
    "download": "So, what are you waiting for? Download OcuSense for Mac. "
                "Windows and Linux are in beta, and there's more to come.",
}


def record_voiceover(voice: str, rate: int, folder: Path) -> dict:
    """label → (samples at 44.1 kHz as float32, seconds), spoken by macOS `say`."""
    clips = {}
    for label, text in VOICEOVER.items():
        aiff, wav_path = folder / f"vo-{label}.aiff", folder / f"vo-{label}.wav"
        subprocess.run(["say", "-v", voice, "-r", str(rate), "-o", str(aiff), text], check=True)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(aiff), "-ac", "1", "-ar", "44100",
                        "-sample_fmt", "s16", str(wav_path)], check=True)
        with wave.open(str(wav_path)) as f:
            data = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16).astype(np.float32) / 32768
        clips[label] = (data, len(data) / 44100)
    return clips


# ------------------------------------------------------------------ fakes: camera face and accounts
def cartoon_face(openness: float, t: float, zoom: float = 1.0, slump: float = 0.0, dark: float = 0.0) -> QImage:
    """What the camera preview shows: a friendly drawn face whose eyes follow `openness` (0–1).

    zoom > 1 = leaning in towards the screen, slump 0–1 = sagging down and sideways, dark 0–1 = lights off.
    """
    img = QImage(480, 360, QImage.Format.Format_RGB888)
    img.fill(QColor("#EDE3CC"))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    sway = math.sin(t * 0.8) * 6
    p.translate(240 + sway + slump * 40, 190 + slump * 70)
    p.rotate(slump * 18)
    p.scale(zoom, zoom)
    p.setPen(QPen(INK, 4))
    p.setBrush(QColor("#F3C9A5"))
    p.drawEllipse(QPointF(0, 0), 120, 145)  # face
    p.setBrush(INK)
    p.drawChord(QRectF(-128, -160, 256, 170), 0, 180 * 16)  # hair
    for x in (-48, 48):
        h = max(2.0, 26 * openness)
        p.setBrush(QColor("#FFFFFF"))
        p.drawEllipse(QPointF(x, -10), 26, h)
        if openness > 0.25:
            p.setBrush(COBALT)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(x, -10), 11, min(11, h))
            p.setPen(QPen(INK, 4))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawArc(QRectF(-40, 30, 80, 50), 200 * 16, 140 * 16)  # smile
    p.setBrush(VERMILION)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QPointF(-78, 40), 14, 9)
    p.drawEllipse(QPointF(78, 40), 14, 9)
    p.resetTransform()
    if dark > 0:
        p.fillRect(img.rect(), QColor(10, 10, 30, int(200 * dark)))
    p.end()
    return img


class FakeThread:
    def __init__(self):
        self.stopped = False

    def request_calibration(self): pass
    def request_posture_calibration(self): pass
    def request_posture_enabled(self, enabled): pass
    def requestInterruption(self): self.stopped = True
    def wait(self, ms): return True


def make_account_service():
    """A signed-in demo account with made-up friends and scores (nothing is sent anywhere)."""
    from ocusense.accounts import Account, AccountStore, FileTokens, SignedIn
    from ocusense.leaderboards import Friend, Row
    from ocusense.ui.account_service import AccountService

    class Client:
        def sign_in(self, email, password):
            return SignedIn(Account("u1", email, "blinkqueen"), "a1", "r1", time.time() + 3600)

        def refresh(self, token):
            return self.sign_in("you@example.com", "")

        def sign_out(self, access):
            pass

    class Boards:
        board = {
            ("eye_runner", "friends"): [Row(1, "toilet_jumper", 1240, "2026-10-11T09:00:00Z"),
                                        Row(2, "blinkqueen", 1105, "2026-10-11T10:00:00Z", True),
                                        Row(3, "sleepy_sam", 870, "2026-10-10T22:00:00Z"),
                                        Row(4, "mira_studies", 655, "2026-10-10T21:00:00Z")],
            ("eye_runner", "everyone"): [Row(1, "no_blink_no_glory", 2310, "2026-10-09T09:00:00Z"),
                                         Row(2, "toilet_jumper", 1240, "2026-10-11T09:00:00Z"),
                                         Row(3, "blinkqueen", 1105, "2026-10-11T10:00:00Z", True),
                                         Row(4, "eyelid_olympian", 990, "2026-10-08T20:00:00Z"),
                                         Row(5, "sleepy_sam", 870, "2026-10-10T22:00:00Z")],
            ("blink_code_challenge", "friends"): [Row(1, "blinkqueen", 420, "2026-10-11T10:00:00Z", True),
                                                  Row(2, "morse_mira", 385, "2026-10-10T19:00:00Z")],
        }

        def submit(self, *args): pass
        def leaderboard(self, game, scope="everyone", token=None, limit=50): return self.board.get((game, scope), [])
        def friends(self, token): return [Friend("u2", "toilet_jumper", "friend"), Friend("u3", "sleepy_sam", "friend"),
                                          Friend("u4", "mira_studies", "incoming")]
        def request_friend(self, token, name): return "requested"
        def respond_friend(self, token, user_id, accept): return "accepted"
        def remove_friend(self, token, user_id): pass

    store = AccountStore(WORK / "account.json", FileTokens(WORK / "account.token"))
    service = AccountService(Client(), store, synchronous=True, leaderboards=Boards())
    service.sign_in("you@example.com", "demo", lambda ok, value: None)
    return service


def seed_garden():
    """A garden with something growing, something ripe, decorations and two paintings on the wall."""
    import json
    from ocusense.core.garden import Garden, Plot
    from ocusense.core.library import PAINTINGS
    now = time.time()
    g = Garden(coins=400)
    g.plots = [Plot("strawberry", now - 7000, now + 200), Plot("carrot", now - 500, now - 300),
               Plot("tomato", now - 120, now + 180), Plot("lettuce", now - 2000, now + 700),
               Plot("blueberry"), Plot("pumpkin", now - 18000, now + 3600)]
    for item in ("flowers", "can", "mobile"):
        g.buy(item)
    for key in list(PAINTINGS)[:3]:
        g.buy_painting(key)
    g.place_painting(list(PAINTINGS)[0], "sidebar:0")
    g.place_painting(list(PAINTINGS)[1], "sidebar:1")
    g.coins = 186
    (WORK / "garden.json").write_text(json.dumps(g.to_dict()))


# ------------------------------------------------------------------ drawing helpers
def font(size, weight=QFont.Weight.Bold):
    f = QFont()
    f.setPixelSize(size)
    f.setWeight(weight)
    return f


def ease(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


class Confetti:
    """Slow Miró shapes drifting around the edges of every frame."""

    def __init__(self, seed=3):
        rng = random.Random(seed)
        spots = [(120, 160), (1800, 140), (90, 860), (1830, 900), (300, 1010), (1620, 1020), (980, 30), (60, 520),
                 (1860, 520)]
        kinds = ["circle", "star", "crescent", "dot", "squiggle"]
        colors = [COBALT, VERMILION, GOLDEN, INK, GREEN]
        self.items = [(x, y, rng.choice(kinds), rng.choice(colors), rng.uniform(18, 40), rng.uniform(0, 6.28))
                      for x, y in spots]

    def draw(self, p, t):
        p.save()
        for x, y, kind, color, size, phase in self.items:
            dx, dy = math.sin(t * 0.6 + phase) * 10, math.cos(t * 0.5 + phase) * 8
            cx, cy = x + dx, y + dy
            p.setPen(QPen(color, 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.setBrush(Qt.BrushStyle.NoBrush)
            if kind == "circle":
                p.setBrush(color)
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(cx, cy), size, size)
            elif kind == "dot":
                p.setBrush(color)
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(cx, cy), size / 3, size / 3)
            elif kind == "star":
                for a in range(4):
                    ang = a * math.pi / 4 + t * 0.3
                    p.drawLine(QPointF(cx - math.cos(ang) * size, cy - math.sin(ang) * size),
                               QPointF(cx + math.cos(ang) * size, cy + math.sin(ang) * size))
            elif kind == "crescent":
                path = QPainterPath()
                path.addEllipse(QPointF(cx, cy), size, size)
                cut = QPainterPath()
                cut.addEllipse(QPointF(cx + size * 0.45, cy - size * 0.2), size, size)
                p.setBrush(color)
                p.setPen(Qt.PenStyle.NoPen)
                p.drawPath(path.subtracted(cut))
            else:
                path = QPainterPath(QPointF(cx - size, cy))
                path.cubicTo(cx - size / 2, cy - size, cx + size / 2, cy + size, cx + size, cy)
                p.drawPath(path)
        p.restore()


def draw_eye(p, cx, cy, size, openness, star=True):
    """The OcuSense eye (as in the logo), blinking with `openness`."""
    p.save()
    p.translate(cx, cy)
    k = size / 64
    p.setPen(QPen(INK, 5 * k, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.setBrush(Qt.BrushStyle.NoBrush)
    upper = QPainterPath(QPointF(-26 * k, 1 * k))
    upper.cubicTo(-16 * k, -15 * k * openness - 1, 14 * k, -19 * k * openness - 1, 26 * k, -3 * k)
    lower = QPainterPath(QPointF(26 * k, -3 * k))
    lower.cubicTo(15 * k, 13 * k * max(openness, 0.15), -12 * k, 16 * k * max(openness, 0.15), -22 * k, 6 * k)
    p.drawPath(upper)
    p.drawPath(lower)
    if openness > 0.2:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(COBALT)
        r = 8.5 * k
        p.save()
        clip = QPainterPath(QPointF(-26 * k, 1 * k))
        clip.cubicTo(-16 * k, -15 * k * openness - 1, 14 * k, -19 * k * openness - 1, 26 * k, -3 * k)
        clip.cubicTo(15 * k, 13 * k * openness, -12 * k, 16 * k * openness, -26 * k, 1 * k)
        p.setClipPath(clip)
        p.drawEllipse(QPointF(1 * k, -1 * k), r, r)
        p.restore()
    if star:
        p.setPen(QPen(VERMILION, 3 * k, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(21 * k, -29 * k), QPointF(21 * k, -17 * k))
        p.drawLine(QPointF(15 * k, -23 * k), QPointF(27 * k, -23 * k))
    p.restore()


def blink_curve(t, every=2.3, length=0.4, offset=0.4):
    """Eye openness over time: open, with a quick blink every `every` seconds."""
    phase = (t - offset) % every
    if phase < length:
        return abs(math.cos(math.pi * phase / length)) * 0.9 + 0.02
    return 0.95


def text_centered(p, text, rect, f, color):
    p.setFont(f)
    p.setPen(color)
    p.drawText(rect, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, text)


# ------------------------------------------------------------------ the film
class Trailer:
    def __init__(self, out: Path, keyframes: Path | None, voice: dict | None = None):
        self.out = out
        self.keyframes = keyframes
        self.voice = voice or {}
        self.cues = []  # (seconds into the film, label): where each voice line starts
        self.confetti = Confetti()
        self.frames = 0
        self.last: QImage | None = None
        silent = WORK / "video.mp4"
        self.video_path = silent
        self.ffmpeg = subprocess.Popen(
            ["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
             "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
             str(silent)], stdin=subprocess.PIPE)

    # --- output
    def emit(self, img: QImage, label: str = "") -> None:
        img = img.convertToFormat(QImage.Format.Format_RGB888)
        if img.bytesPerLine() == W * 3:
            data = bytes(img.constBits())
        else:
            data = b"".join(bytes(img.constScanLine(y))[:W * 3] for y in range(H))
        self.ffmpeg.stdin.write(data)
        self.frames += 1
        CLOCK.advance()
        self.last = img
        if self.keyframes and label:
            img.save(str(self.keyframes / f"{self.frames:05d}-{label}.png"))

    def canvas(self, t: float) -> tuple[QImage, QPainter]:
        img = QImage(W, H, QImage.Format.Format_RGB888)
        img.fill(PAPER)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.confetti.draw(p, t)
        return img, p

    def time(self) -> float:
        return self.frames / FPS

    def length(self, seconds: float, label: str) -> int:
        """Frames for a scene: at least `seconds`, and long enough for its voice line (cued 0.3 s in)."""
        if label in self.voice:
            self.cues.append((self.time() + 0.3, label))
            seconds = max(seconds, self.voice[label][1] + 0.9)
        return int(seconds * FPS)

    # --- building blocks
    def card(self, seconds, title, subtitle="", eye=True, accent=VERMILION, voice=""):
        n = self.length(seconds, voice)
        for i in range(n):
            t = i / FPS
            img, p = self.canvas(self.time())
            appear = ease(t / 0.5)
            if eye:
                draw_eye(p, W / 2, 330 - (1 - appear) * 30, 260, blink_curve(t, every=1.6, offset=0.6))
            p.setOpacity(appear)
            text_centered(p, title, QRectF(160, 470 if eye else 360, W - 320, 170), font(96), INK)
            if subtitle:
                p.setOpacity(ease((t - 0.35) / 0.5))
                text_centered(p, subtitle, QRectF(200, 640 if eye else 540, W - 400, 160),
                              font(44, QFont.Weight.Medium), GRAPHITE)
            p.setOpacity(1)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(accent)
            p.drawRoundedRect(QRectF(W / 2 - 60 * appear, 820 if eye else 740, 120 * appear, 10), 5, 5)
            p.end()
            self.emit(self.fade(img, i, n), title[:20] if i == n // 2 else "")

    def call_to_action(self, seconds):
        """The last card: "What are you waiting for?", a pulsing download button, the other platforms."""
        n = self.length(seconds, "download")
        for i in range(n):
            t = i / FPS
            img, p = self.canvas(self.time())
            appear = ease(t / 0.5)
            draw_eye(p, W / 2, 250, 200, blink_curve(t, every=1.3, offset=0.8))
            p.setOpacity(appear)
            text_centered(p, "What are you waiting for?", QRectF(120, 360, W - 240, 150), font(100), INK)
            p.setOpacity(ease((t - 0.4) / 0.5))
            text_centered(p, "Download OcuSense and give your eyes the break they deserve.",
                          QRectF(200, 520, W - 400, 80), font(44, QFont.Weight.Medium), GRAPHITE)
            pulse = 1 + 0.04 * math.sin(t * 6) if t > 0.9 else ease((t - 0.6) / 0.3)
            bw, bh = 560 * pulse, 120 * pulse
            p.setOpacity(ease((t - 0.6) / 0.3))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 45))
            p.drawRoundedRect(QRectF(W / 2 - bw / 2 + 6, 668 + 10, bw, bh), bh / 2, bh / 2)
            p.setBrush(COBALT)
            p.drawRoundedRect(QRectF(W / 2 - bw / 2, 668, bw, bh), bh / 2, bh / 2)
            text_centered(p, "Download for Mac", QRectF(W / 2 - bw / 2, 668, bw, bh), font(max(1, int(50 * pulse))),
                          PAPER)
            for k, (name, at) in enumerate((("Windows · beta", 3.6), ("Linux · beta", 4.1))):
                p.setOpacity(ease((t - at) / 0.4))
                x = W / 2 - 330 + k * 340
                p.setPen(QPen(INK, 4))
                p.setBrush(PAPER)
                p.drawRoundedRect(QRectF(x, 830, 320, 76), 38, 38)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(GOLDEN)
                p.drawEllipse(QPointF(x + 34, 868), 10, 10)
                text_centered(p, name, QRectF(x + 50, 830, 262, 76), font(32), INK)
            p.setOpacity(ease((t - 5.0) / 0.5))
            text_centered(p, "…and more to come.", QRectF(200, 930, W - 400, 60), font(36, QFont.Weight.Medium),
                          GRAPHITE)
            p.end()
            self.emit(self.fade(img, i, n), "download" if i == n // 2 else "")

    def fade(self, img: QImage, i: int, n: int, edge: int = 8) -> QImage:
        """Cross-fade from the previous scene over the first frames."""
        if self.last is None or i >= edge:
            return img
        out = QImage(self.last)
        p = QPainter(out)
        p.setOpacity(ease((i + 1) / edge))
        p.drawImage(0, 0, img)
        p.end()
        return out

    def app_frame(self, window, caption: str, t: float, overlay=None) -> QImage:
        """The app window, framed like a laptop screen, with a caption underneath."""
        shot = window.grab().toImage()
        img, p = self.canvas(self.time())
        target_w = 1392
        target_h = int(shot.height() * target_w / shot.width())
        x, y = (W - target_w) / 2, 34
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 40))
        p.drawRoundedRect(QRectF(x + 10, y + 14, target_w, target_h), 22, 22)  # soft shadow
        p.setBrush(INK)
        p.drawRoundedRect(QRectF(x - 12, y - 12, target_w + 24, target_h + 24), 26, 26)  # bezel
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(x, y, target_w, target_h), 14, 14)
        p.save()
        p.setClipPath(clip)
        p.drawImage(QRectF(x, y, target_w, target_h), shot)
        if overlay is not None:
            overlay(p, QRectF(x, y, target_w, target_h), shot.width())
        p.restore()
        # caption pill
        appear = ease(t / 0.45)
        p.setFont(font(40))
        width = min(W - 200, p.fontMetrics().horizontalAdvance(caption) + 90)
        cy = y + target_h + 42 + (1 - appear) * 20
        p.setOpacity(appear)
        p.setBrush(INK)
        p.drawRoundedRect(QRectF((W - width) / 2, cy, width, 74), 37, 37)
        p.setBrush(VERMILION)
        p.drawEllipse(QPointF((W - width) / 2 + 40, cy + 37), 9, 9)
        p.setPen(PAPER)
        p.drawText(QRectF((W - width) / 2 + 50, cy, width - 60, 74), Qt.AlignmentFlag.AlignCenter, caption)
        p.end()
        return img

    def scene(self, seconds, window, caption, step=None, overlay=None, label=""):
        """step(i, t) changes the app before each frame (feed blinks, move the game, …)."""
        app = QApplication.instance()
        n = self.length(seconds, label)
        for i in range(n):
            t = i / FPS
            if step:
                step(i, t)
            window._tick()  # what the window's own timer does, now once per video frame
            window.pomodoro_page.tick()
            app.processEvents()
            frame = self.app_frame(window, caption, t, overlay)
            self.emit(self.fade(frame, i, n), label if i == n // 2 else "")

    def close(self):
        self.ffmpeg.stdin.close()
        self.ffmpeg.wait()


# ------------------------------------------------------------------ music (synthesised, ~120 bpm chiptune)
def make_music(seconds: float, rate=44100) -> np.ndarray:
    bpm = 118
    beat = 60 / bpm
    t = np.arange(int(seconds * rate)) / rate
    out = np.zeros_like(t)
    notes = {"C": 261.63, "D": 293.66, "E": 329.63, "F": 349.23, "G": 392.0, "A": 440.0, "B": 493.88}
    chords = [("C", "E", "G"), ("G", "B", "D"), ("A", "C", "E"), ("F", "A", "C")]  # I–V–vi–IV
    melody = "E G A G E D C D E E D C D E G E".split()

    def tone(freq, start, length, kind="square", volume=0.12):
        a, b = int(start * rate), min(len(t), int((start + length) * rate))
        if a >= len(t):
            return
        tt = np.arange(b - a) / rate
        if kind == "square":
            wave_ = np.sign(np.sin(2 * np.pi * freq * tt)) * 0.6
        elif kind == "triangle":
            wave_ = 2 / np.pi * np.arcsin(np.sin(2 * np.pi * freq * tt))
        else:
            wave_ = np.sin(2 * np.pi * freq * tt)
        env = np.minimum(1, tt / 0.01) * np.exp(-tt * 3.5)
        out[a:b] += volume * wave_ * env

    rng = np.random.default_rng(1)
    n_beats = int(seconds / beat) + 1
    for k in range(n_beats):
        start = k * beat
        chord = chords[(k // 4) % 4]
        tone(notes[chord[0]] / 2, start, beat * 0.9, "triangle", 0.22)  # bass
        for j, name in enumerate(chord):  # arpeggio in eighths
            tone(notes[name] * 2, start + j * beat / 3, beat / 3, "square", 0.045)
        a = int(start * rate)
        if k % 2 == 0 and a < len(t):  # kick
            tt = np.arange(min(int(0.15 * rate), len(t) - a)) / rate
            out[a:a + len(tt)] += 0.5 * np.sin(2 * np.pi * (110 * np.exp(-tt * 25) + 40) * tt) * np.exp(-tt * 18)
        h = int((start + beat / 2) * rate)
        if h < len(t):  # hi-hat
            m = min(int(0.04 * rate), len(t) - h)
            out[h:h + m] += 0.06 * rng.standard_normal(m) * np.exp(-np.arange(m) / rate * 90)
        if 8 <= k < n_beats - 8:  # melody after the intro
            tone(notes[melody[k % len(melody)]] * 2, start, beat * 0.7, "square", 0.06)
    fade = np.minimum(1, np.minimum(t / 1.5, (seconds - t) / 2.5))
    return np.tanh(out * fade * 1.3) * 0.8


def write_soundtrack(path: Path, seconds: float, cues, clips, rate=44100) -> None:
    """Music plus voiceover; the music dips to 30 % while the voice speaks (smoothed, no clicks)."""
    music = make_music(seconds, rate)
    voice = np.zeros_like(music)
    for start, label in cues:
        data = clips[label][0]
        a = int(start * rate)
        b = min(len(voice), a + len(data))
        voice[a:b] += data[:b - a]
    speaking = (np.abs(voice) > 0.01).astype(np.float32)
    window = int(0.35 * rate)
    speaking = np.convolve(speaking, np.ones(window) / window, mode="same") > 0.02  # hold through short pauses
    duck = np.convolve(speaking.astype(np.float32), np.ones(int(0.2 * rate)) / int(0.2 * rate), mode="same")
    mix = music * (1 - 0.7 * duck) + voice * 1.35
    mix = mix / max(1.0, np.max(np.abs(mix)) / 0.95)
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes((mix * 32767).astype(np.int16).tobytes())


# ------------------------------------------------------------------ main
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=Path.home() / "Desktop" / "OcuSense-trailer.mp4")
    parser.add_argument("--keyframes", action="store_true", help="save one PNG per scene next to the video")
    parser.add_argument("--voice", default="Samantha", help="a macOS voice (say -v '?' lists them)")
    parser.add_argument("--rate", type=int, default=178, help="speaking rate, words per minute")
    parser.add_argument("--no-voiceover", action="store_true")
    args = parser.parse_args(argv)
    if shutil.which("ffmpeg") is None:
        sys.exit("ffmpeg is needed: brew install ffmpeg")

    app = QApplication.instance() or QApplication([])
    from ocusense.monitoring.pipeline import MODEL_PATH
    if not MODEL_PATH.exists():
        sys.exit("The face model is missing: python download_model.py")
    from ocusense.ui import main_window as mw
    from ocusense.ui import theme, window_chrome
    from ocusense.core.blink_counter import BlinkCounter
    from ocusense.core.history import ScoreHistory
    from ocusense.core.models import FrameObservation
    from ocusense.core.morse import MORSE
    from ocusense.core import runner as R
    from ocusense.monitoring.camera_worker import MonitorUpdate

    app.setApplicationName("OcuSense")
    app.setStyle("Fusion")
    app.setStyleSheet(theme.STYLE_SHEET)
    window_chrome.install(app)
    seed_garden()
    service = make_account_service()
    mw.AccountService = lambda: service
    window = mw.MainWindow(demo_history=True)
    window.notify = lambda message, title: None
    window.resize(1440, 900)
    window.show()
    app.processEvents()
    for i in range(4):  # some finished games on this Mac, too
        window.games_page.scores.book.record("eye_runner", [640, 1105, 480, 920][i], now=time.time() - 86400 * i)

    keyframes = None
    if args.keyframes:
        keyframes = args.out.with_suffix("")
        keyframes.mkdir(parents=True, exist_ok=True)
    clips = {} if args.no_voiceover else record_voiceover(args.voice, args.rate, WORK)
    film = Trailer(args.out, keyframes, clips)

    # ---------------- 1. hello
    film.card(3.6, "OcuSense", "your eyes' new study buddy", voice="intro")
    film.card(3.0, "You stare at screens for hours.", "Your eyes forget to blink. (Rude.)", eye=False, accent=COBALT,
              voice="problem")

    # ---------------- 2. study: a cartoon face drives the real detector, graph and counters
    thread = FakeThread()
    window._start_camera = lambda: (setattr(window, "thread", thread), True)[1]
    window.monitor.calibration = object()
    window.show_page("study")
    window.start()
    from ocusense.core.models import PostureStatus
    counter, history = BlinkCounter(), ScoreHistory()
    blinks, current = [0], {"value": 0.95, "t": 0.0}
    env = {"zoom": 1.0, "slump": 0.0, "dark": 0.0, "posture": None}  # what the next scenes act out
    still_face = cartoon_face(0.95, 0.0)  # for the pre-roll, which is never shown

    def feed_study(i, t):
        now = time.monotonic()
        value = blink_curve(t, every=3.1 if t < 0 else 1.9)
        current.update(value=value, t=t)
        if t >= 0:
            window.study.verticalScrollBar().setValue(0)  # the timer and controls at the top
        before = counter.state
        blinked = counter.update(value)
        blinks[0] += blinked
        history.add(now, (value, value, value), blinked)
        obs = FrameObservation(t=now, valid=True, left_raw=value, right_raw=value, left_ear=0.3 * value,
                               right_ear=0.3 * value, detector_closed=counter.state == BlinkCounter.CLOSED,
                               closing_started=before == BlinkCounter.OPEN and counter.state == BlinkCounter.CLOSED,
                               blink_completed=blinked)
        posture = env["posture"]
        window._on_update(MonitorUpdate(now=now, face_found=True, reliable=True, reason="", openness=(value,) * 3,
                                        closeness=env["zoom"], brightness=130 - 110 * env["dark"],
                                        posture_enabled=posture is not None, posture_status=posture,
                                        blinked=blinked, events=[], blinks=blinks[0], calibrated=True,
                                        cal_status="done", cal_step=None, cal_measuring=False, cal_seconds_left=0,
                                        cal_error="", samples=list(history.samples) if t > -12 else [],
                                        preview=cartoon_face(value, t) if t >= 0 else still_face,
                                        source=thread, observation=obs))

    PREROLL = 41 * 60  # 41 minutes of real (simulated) study before the scene: timer, counts and recap agree
    for k in range(PREROLL * FPS):
        feed_study(k, -PREROLL + k / FPS)
        CLOCK.advance()
        if k % 30 == 0:
            window._tick()

    def webcam_bubble(p, rect, shot_width):
        r = 118
        cx, cy = rect.right() - r - 28, rect.bottom() - r - 28
        clip = QPainterPath()
        clip.addEllipse(QPointF(cx, cy), r, r)
        p.save()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 50))
        p.drawEllipse(QPointF(cx + 6, cy + 8), r, r)
        p.setClipPath(clip)
        face = cartoon_face(current["value"], current["t"], env["zoom"], env["slump"], env["dark"])
        p.drawImage(QRectF(cx - r * 1.33, cy - r, r * 2.67, r * 2), face)
        p.setClipping(False)
        p.setPen(QPen(INK, 6))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), r, r)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(VERMILION)
        p.drawEllipse(QPointF(cx - r * 0.72, cy - r * 0.72), 11, 11)  # the "recording" dot
        p.setFont(font(20))
        p.setPen(INK)
        p.drawText(QRectF(cx - 140, cy + r + 4, 280, 30), Qt.AlignmentFlag.AlignCenter, "you (well, a drawing of you)")
        p.restore()

    film.scene(6.5, window, "It counts your blinks while you study. Only numbers, never photos.", feed_study,
               overlay=webcam_bubble, label="study")

    # ---------------- 2b. ergonomics: too close, slouching, a dark room (each through the real checks)
    film.card(2.4, "Your body counts too.", "Little nudges, not nagging.", eye=False, accent=GREEN, voice="body")
    offset = [0.0]

    def directed(direct):
        def step(i, t):
            direct(t)
            window.study.verticalScrollBar().setValue(0)
            feed_study(i, offset[0] + t)
        return step

    film.scene(6.0, window, "Leaning in too close? It'll tell you. Politely-ish.",
               directed(lambda t: env.update(zoom=1.0 + 0.9 * ease((t - 0.3) / 0.8))), overlay=webcam_bubble,
               label="distance")
    env.update(zoom=1.0)
    for k in range(int(1.5 * FPS)):  # back at arm's length: the reminder goes away by itself
        feed_study(k, 100 + k / FPS)
        CLOCK.advance()
    poor = PostureStatus(tracked=True, poor=True, problems=("head dropped",))
    upright = PostureStatus(tracked=True, poor=False)

    def slouch(t):
        env.update(slump=ease((t - 0.2) / 1.0), posture=poor if t > 1.0 else upright)

    film.scene(5.0, window, "Slouching? It notices that too.", directed(slouch), overlay=webcam_bubble,
               label="posture")
    env.update(slump=0.0, posture=upright)
    for k in range(int(1.0 * FPS)):  # sitting up again: the card goes away by itself
        feed_study(k, 200 + k / FPS)
        CLOCK.advance()
    env["posture"] = None
    window.study.message_label.setText("")  # the slouch note under the timer has done its job
    window.settings_page.lighting.setChecked(True)  # the lighting check is off unless switched on
    env["dark"] = 1.0
    for k in range(58 * FPS):  # the room has been dark for almost a minute
        feed_study(k, 300 + k / FPS)
        CLOCK.advance()
    film.scene(5.0, window, "Studying in a cave? It suggests a lamp.", directed(lambda t: env.update(dark=1.0)),
               overlay=webcam_bubble, label="lighting")
    env["dark"] = 0.0
    for k in range(int(1.5 * FPS)):
        feed_study(k, 400 + k / FPS)
        CLOCK.advance()
    window.lighting_card.setVisible(False)

    # ---------------- 2c. settings: every reminder has its own switch
    window.show_page("settings")
    settings = window.settings_page
    app.processEvents()
    heading_y = settings.reminders.mapTo(settings.widget(), settings.reminders.rect().topLeft()).y()
    settings.verticalScrollBar().setValue(max(0, heading_y - 200))  # the whole Reminders section in view
    app.processEvents()
    # switch the 20-20-20 eye rest on, the lighting check off and on again, the distance reminder off and on
    clicks = [(0.9, settings.eye_rest), (2.0, settings.lighting), (2.9, settings.lighting),
              (4.0, settings.distance), (4.9, settings.distance)]
    pointer = {"pos": None, "clicked_at": -9.0}

    def point_and_click(i, t):
        target = next((w for at, w in clicks if t < at), clicks[-1][1])
        start = next(((at, w) for at, w in reversed(clicks) if t >= at), None)
        centre = target.mapTo(window, target.rect().center())
        if pointer["pos"] is None:
            pointer["pos"] = (centre.x() + 260.0, centre.y() + 160.0)
        x, y = pointer["pos"]
        pointer["pos"] = (x + (centre.x() - x) * 0.18, y + (centre.y() - y) * 0.18)  # glide towards the switch
        for at, w in clicks:
            if abs(t - at) < 0.5 / FPS:
                w.click()
                pointer["clicked_at"] = t
        pointer["t"] = t
        del start

    def draw_pointer(p, rect, shot_width):
        if pointer["pos"] is None:
            return
        k = rect.width() / shot_width
        x, y = rect.left() + pointer["pos"][0] * k, rect.top() + pointer["pos"][1] * k
        since = pointer.get("t", 0) - pointer["clicked_at"]
        if 0 <= since < 0.5:  # a click ripple
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

    film.scene(6.0, window, "Every reminder has its own switch. You're the boss.", point_and_click,
               overlay=draw_pointer, label="settings")
    window.show_page("study")

    # ---------------- 3. pomodoro
    window.show_page("pomodoro")
    window.pomodoro_page.main_button.click()  # start a focus round, as a person would
    film.scene(3.8, window, "Focus in rounds. Breaks are part of the plan.", label="pomodoro")
    window.stop()
    if window.summary_card is not None:
        summary_card = window.summary_card
    else:
        summary_card = None

    # ---------------- 4. games
    film.card(2.4, "Break time?", "Play games… with your eyes.", accent=GOLDEN, voice="break")
    window.show_page("games")
    film.scene(2.6, window, "Little games for your breaks.", label="games-hub")

    page = window.games_page
    page.open_eye_runner()
    runner = page.eye_runner
    runner.frames.stop()  # the trailer moves the game itself, one video frame at a time
    game = runner.game
    game.rng = random.Random(11)
    game.jump()
    game.score = 240
    game.highscore = 1105
    crash_at = 6.4

    def play_runner(i, t):
        p = game.player
        ahead = [o for o in game.obstacles if o.rect.right > p.x - 10 and o.kind in ("ground", "low")]
        if ahead and t < crash_at - 0.6:
            o = min(ahead, key=lambda o: o.rect.x)
            gap = o.rect.x - (p.x + 34)
            if 0 < gap < game.speed * 0.2 and p.on_ground:
                game.jump()
                runner.canvas.eyes_closed = True
            elif o.kind == "low" and not p.on_ground and p.vy > 0 and 0 < gap < 60:
                game.jump()  # the extra jump over a flying toilet
        else:
            runner.canvas.eyes_closed = False
        if t >= crash_at - 0.6 and game.state == "play" and not any(o.rect.x < 400 for o in game.obstacles):
            game.obstacles.append(R.Obstacle(p.x + 120, "ground", game.sizes.obstacles[0], game.rng))
        runner.canvas.eyes = "eyes closed" if runner.canvas.eyes_closed else "eyes open"
        if game.state == "play":
            game.update(1 / FPS, False)
        elif game.state == "over":
            game.over_timer += 1 / FPS
            game.update(1 / FPS, False)
        runner.canvas.update()

    film.scene(8.0, window, "EyeGame: blink to jump. Yes, those are toilets.", play_runner, label="eyegame")

    page.show_hub()
    page.open_blink_code()
    code = page.blink_code
    code.set_input("keys")
    code.set_mode("challenge")
    code.start_challenge()
    typed = {"i": 0}

    def play_code(i, t):
        if i % 12 == 6 and code.challenge.started_at is not None:
            letter = code.challenge.expected
            code._letter(letter, MORSE[letter])
            typed["i"] += 1

    film.scene(5.0, window, "Blink Code: learn Morse code with your eyelids.", play_code, label="blinkcode")
    page.show_hub()
    page.open_blink_garden()
    film.scene(4.2, window, "Grow a garden with gentle eye exercises.", label="garden")
    page.show_hub()

    # ---------------- 5. leaderboard
    board = page.leaderboard
    board.set_game("eye_runner")
    board.set_scope("friends")

    def scroll_to_board(i, t):
        if i == int(2.6 * FPS):
            board.set_scope("everyone")

    film.scene(5.2, window, "Beat your friends. Then beat your own record.", scroll_to_board, label="leaderboard")
    window.show_page("account")
    window.account_page.verticalScrollBar().setValue(10 ** 6)
    film.scene(2.8, window, "Add friends by username. Nothing else is shared.", label="friends")

    # ---------------- 6. gallery and the theme switch
    window.show_page("library")
    switched = {"done": False}

    def switch_theme(i, t):
        if t > 2.2 and not switched["done"]:
            window.apply_theme("haring")
            switched["done"] = True

    film.scene(4.6, window, "Collect paintings. Change the whole look in one click.", switch_theme, label="gallery")
    window.show_page("pomodoro")
    film.scene(2.6, window, "Keith Haring mode, because why not.", label="haring")
    window.apply_theme("miro")

    # ---------------- 7. statistics and the summary card
    window.show_page("all_time")
    film.scene(3.6, window, "See how your eyes did. No judgement, just numbers.", label="stats")
    if summary_card is not None:
        summary_card.show()
        app.processEvents()

        def card_overlay(p, rect, shot_width):
            card = summary_card.grab().toImage()
            k = rect.width() / shot_width
            cw, ch = card.width() * k, card.height() * k
            p.fillRect(rect, QColor(0, 0, 0, 70))
            p.drawImage(QRectF(rect.center().x() - cw / 2, rect.center().y() - ch / 2, cw, ch), card)

        film.scene(3.4, window, "Every session ends with a little recap.", overlay=card_overlay, label="summary")
        summary_card.close()

    # ---------------- 8. bye
    film.card(3.2, "Blink more. Stress less.", "OcuSense · made by students, for tired student eyes", voice="outro")
    film.call_to_action(4.6)
    seconds = film.frames / FPS
    film.close()
    window.close()

    music = WORK / "soundtrack.wav"
    write_soundtrack(music, seconds, film.cues, clips)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(film.video_path), "-i", str(music),
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart",
                    str(args.out)], check=True)
    shutil.rmtree(WORK, ignore_errors=True)
    print(f"{args.out}  ·  {seconds:.1f} s, {W}×{H}, {FPS} fps")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
