"""Continuous bilateral exercise holds on calibrated openness, not new blink detection."""
from dataclasses import dataclass
import math
from ocusense.config import CLOSE_BELOW, REOPEN_ABOVE, MAX_FRAME_GAP


@dataclass
class EyeExercise:
    hold_seconds: float = 2.0
    closure_mode: str = 'bilateral_closure'  # Squeeze strength is not measured.
    step: int = 0
    since: float | None = None
    last: float | None = None
    progress: float = 0.0
    reopen_required: bool = False

    def __post_init__(self):
        if self.closure_mode != 'bilateral_closure':
            raise ValueError('Unsupported closure detection mode')

    @property
    def complete(self):
        return self.step >= 3

    def interrupt(self):
        self.since = self.last = None
        self.progress = 0.0

    def feed(self, now, left, right, valid=True):
        if self.complete:
            return
        if not valid or not all(type(v) in (int, float) and math.isfinite(v) for v in (now, left, right)):
            self.interrupt()
            return
        if self.last is not None and (now <= self.last or now - self.last > MAX_FRAME_GAP):
            self.interrupt()
        self.last = now
        opened = left >= REOPEN_ABOVE and right >= REOPEN_ABOVE
        closed = left <= CLOSE_BELOW and right <= CLOSE_BELOW
        if self.reopen_required:
            if opened:
                self.reopen_required = False
            self.since = None
            self.progress = 0
            return
        matches = opened if self.step == 0 else closed
        if not matches:
            self.since = None
            self.progress = 0
            return
        if self.since is None:
            self.since = now
        self.progress = min(1.0, (now - self.since) / self.hold_seconds)
        if self.progress >= 1:
            self.step += 1
            self.since = None
            self.progress = 0
            self.reopen_required = self.step == 2


@dataclass
class GardenReminder:
    elapsed: float = 0
    last: float | None = None
    snoozed_until: float = 0

    def update(self, now, monitoring, enabled, minutes, needs_water):
        delta = min(1.0, max(0.0, now - self.last)) if self.last is not None else 0
        self.last = now
        if not enabled:
            self.elapsed = 0
            return False
        if monitoring:
            self.elapsed += delta
        if monitoring and needs_water and now >= self.snoozed_until and self.elapsed >= minutes * 60:
            self.elapsed = 0
            return True
        return False

    def snooze(self, now):
        self.snoozed_until = now + 600
        self.elapsed = 0
