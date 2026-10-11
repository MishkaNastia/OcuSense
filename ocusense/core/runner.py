"""EyeGame: an endless runner you play by blinking. Pure Python, no interface.

Made by our teammate MishkaNastia (github.com/MishkaNastia/EyeGame) as a Pygame game
and ported here so it runs inside OcuSense: the rules, numbers and art are hers; the
drawing lives in ui/widgets/runner_canvas.py, and blinks come from OcuSense's own
calibrated detector instead of a second camera.

The OcuSense eye runs along the ground. A blink (or Space) = jump, another blink while
in the air = one extra jump (however long after the first), Down = duck. Toilets scroll in (the only obstacle in
assets/eye_runner/obstacles/obstacles.json; her other obstacle art is still in that folder);
touching one ends the run with a splat. Coffee, a croissant or a Blink Mate can give
double points for 5 s. After 300 points some toilets fly: jump the low ones, run
under the high ones.

Coordinates are a fixed 960 × 360 scene (y down, like the screen); the canvas scales it.
"""

import json
import math
import random
import struct
from dataclasses import dataclass, field
from pathlib import Path

from ocusense.config import CLOSE_BELOW

from .blink_counter import BlinkCounter

ASSETS = Path(__file__).resolve().parent.parent / "assets" / "eye_runner"

# --- Scene ---
WIDTH, HEIGHT = 960, 360
GROUND_Y = 290

# --- Player (pixels, seconds) ---
PLAYER_X = 90
AVATAR_WIDTH = 76
AVATAR_EYE_TOP = 0.337  # fraction of the avatar height where the asterisk ends and the eye starts
LEG_LEN = 14
GRAVITY = 2600.0
FAST_FALL_GRAVITY = 6000.0  # holding Down in the air
JUMP_VELOCITY = -900.0  # apex ~155 px, airtime ~0.69 s
EXTRA_JUMP_APEX = 210  # px above ground: the extra jump aims for this peak so it stays on screen
EXTRA_GRAVITY_SCALE = 0.6  # …and is floatier
AVATAR_BLINK_S = 0.15  # the avatar's eye shuts this long when it jumps

# --- Speed / difficulty ---
START_SPEED = 420.0
SPEED_GAIN = 20.0  # px/s added per second of play
MAX_SPEED = 1100.0
MIN_GAP_S = 0.85
MAX_GAP_S = 1.8
FLYERS_FROM_SCORE = 300
SCORE_RATE = 1 / 40  # points per pixel travelled (~10 points/s at the start)

# --- Power-ups ---
POWERUPS = ("coffee", "croissant", "blinkmate")
POWERUP_HEIGHT = 48
POWERUP_CHANCE = 0.18
POWERUP_AIR_HEIGHT = 105
POWERUP_AIR_CHANCE = 0.5
DOUBLE_POINTS_S = 5.0

# --- Obstacles ---
OBSTACLE_BOX = {"ground": (110, 56), "low": (110, 44), "high": (110, 44)}
LOW_FLY_GAP = 14
HIGH_FLY_BOTTOM = 82

# --- Blinks ---
BLINK_COOLDOWN_S = 0.1  # one blink can't give two jumps
# The game's own blink rule: the study detector's closing threshold, but the eyes count as
# open again from 50 % (the study detector waits for 65 %). In a quick double blink the eyes
# often only half-open in between, and the second blink must still count. Study measurements
# keep the study detector unchanged.
GAME_CLOSE_BELOW = CLOSE_BELOW
GAME_REOPEN_ABOVE = 0.5

N_DOODLES = 9
RESTART_DELAY_S = 0.6  # so the blink you crashed with doesn't restart the run


def png_size(path: Path) -> tuple[int, int]:
    """Width and height from a PNG header (keeps this module free of image libraries)."""
    with open(path, "rb") as f:
        head = f.read(24)
    return struct.unpack(">II", head[16:24])


def fit(size: tuple[int, int], max_w: float, max_h: float) -> tuple[int, int]:
    k = min(max_w / size[0], max_h / size[1])
    return round(size[0] * k), round(size[1] * k)


@dataclass
class Rect:
    x: float
    y: float
    w: float
    h: float

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h

    def collides(self, other: "Rect") -> bool:
        return self.x < other.right and other.x < self.right and self.y < other.bottom and other.y < self.bottom

    def inflate(self, dw: float, dh: float) -> "Rect":
        return Rect(self.x - dw / 2, self.y - dh / 2, self.w + dw, self.h + dh)


@dataclass
class ObstacleKind:
    id: str
    file: str
    joke: str
    effect: str | None
    size: tuple[int, int]  # of the image file


def load_obstacles(folder: Path = ASSETS / "obstacles") -> list[ObstacleKind]:
    items = json.loads((folder / "obstacles.json").read_text())
    return [ObstacleKind(it["id"], it["file"], it["joke"], it.get("effect"), png_size(folder / it["file"]))
            for it in items]


class Presses:
    """One jump per blink or key press: presses closer together than the cooldown are the same one."""

    def __init__(self, cooldown_s: float = BLINK_COOLDOWN_S):
        self.cooldown_s = cooldown_s
        self._last = -1e9

    def press(self, t: float) -> bool:
        if t - self._last < self.cooldown_s:
            return False
        self._last = t
        return True


class EyeClosures:
    """When the eyes close, for the game: OcuSense's BlinkCounter with the game's thresholds.

    Fed the personal openness of both eyes (clipped, as the study detector gets it), or None
    when the eyes can't be measured. update() is True on the frame the eyes close, so the
    jump comes without waiting for them to reopen.
    """

    def __init__(self, close_below: float = GAME_CLOSE_BELOW, reopen_above: float = GAME_REOPEN_ABOVE):
        self.counter = BlinkCounter(close_below, reopen_above)

    @property
    def closed(self) -> bool:
        return self.counter.state == BlinkCounter.CLOSED

    def update(self, openness: float | None) -> bool:
        before = self.counter.state
        self.counter.update(openness)
        return before == BlinkCounter.OPEN and self.closed


# ------------------------------------------------------------------ things in the scene
class Player:
    """The OcuSense eye on little legs. It blinks when it jumps."""

    def __init__(self, avatar_size: tuple[int, int]):
        w = AVATAR_WIDTH
        h = round(avatar_size[1] * w / avatar_size[0])
        self.split = round(h * AVATAR_EYE_TOP)  # rows above = asterisk, below = eye
        self.eye_size = (w, h - self.split)
        self.x = PLAYER_X
        self.y = 0.0  # height above the ground
        self.vy = 0.0  # negative = going up
        self.ducking = False
        self.fast_fall = False
        self.blink_t = 0.0
        self.extra = False
        self.anim_t = 0.0
        self.dead = False
        self.splat: dict | None = None
        self.splat_age = 0.0

    @property
    def on_ground(self) -> bool:
        return self.y <= 0 and self.vy >= 0

    def jump(self) -> bool:
        if self.on_ground and not self.dead:
            self.vy = JUMP_VELOCITY
            self.blink_t = AVATAR_BLINK_S
            return True
        return False

    def extra_jump(self) -> bool:
        if self.on_ground or self.extra or self.dead:
            return False
        self.extra = True
        g = GRAVITY * EXTRA_GRAVITY_SCALE
        self.vy = -math.sqrt(2 * g * max(0.0, EXTRA_JUMP_APEX - self.y))  # v² = 2gh
        self.blink_t = AVATAR_BLINK_S
        return True

    def update(self, dt: float) -> None:
        self.anim_t += dt
        self.blink_t = max(0.0, self.blink_t - dt)
        g = FAST_FALL_GRAVITY if self.fast_fall else GRAVITY * EXTRA_GRAVITY_SCALE if self.extra else GRAVITY
        self.vy += g * dt
        self.y -= self.vy * dt
        if self.y <= 0:
            self.y, self.vy, self.extra = 0.0, 0.0, False

    def eye_rect(self) -> Rect:
        w, h = self.eye_size
        if self.ducking and self.on_ground:
            w, h = int(w * 1.15), int(h * 0.6)
        bottom = GROUND_Y - LEG_LEN - int(self.y)
        return Rect(self.x - w / 2, bottom - h, w, h)

    def hitbox(self) -> Rect:
        r = self.eye_rect()
        return Rect(r.x + 8, r.y + 4, r.w - 16, r.h - 4 + LEG_LEN)  # a bit smaller: near misses feel fair

    def get_splatted(self, rng: random.Random) -> None:
        """Crashed into the toilet. Positions are relative to the eye centre."""
        eye = self.eye_rect()
        self.splat = {
            "blobs": [(rng.uniform(-0.42, 0.42) * eye.w, rng.uniform(-0.38, 0.38) * eye.h, rng.randint(6, 12),
                       rng.randrange(4)) for _ in range(11)],
            "drips": [(rng.uniform(-0.35, 0.35) * eye.w, rng.randint(10, 22), rng.randint(4, 6)) for _ in range(4)],
            "flecks": [(rng.uniform(-260, 260), rng.uniform(-420, -80), rng.randint(2, 4)) for _ in range(14)],
        }
        self.splat_age = 0.0


class Obstacle:
    """One of her obstacles. kind = "ground" (jump), "low" (flying low: jump) or "high" (run under it)."""

    def __init__(self, x: float, kind: str, item: ObstacleKind, rng: random.Random):
        self.x, self.kind, self.item = x, kind, item
        self.joke, self.effect = item.joke, item.effect
        self.w, self.h = fit(item.size, *OBSTACLE_BOX[kind])
        self.base = {"ground": GROUND_Y, "low": GROUND_Y - LOW_FLY_GAP, "high": GROUND_Y - HIGH_FLY_BOTTOM}[kind]
        self.t = rng.random() * 10
        self.bottom = float(self.base)

    def update(self, dt: float, speed: float) -> None:
        flying = self.kind != "ground"
        self.x -= speed * dt * (1.1 if flying else 1.0)  # flyers drift a bit faster
        self.t += dt
        self.bottom = self.base + (round(math.sin(self.t * 5) * 3) if flying else 0)

    @property
    def rect(self) -> Rect:
        return Rect(int(self.x), self.bottom - self.h, self.w, self.h)

    @property
    def offscreen(self) -> bool:
        return self.x + self.w < -20

    def hitbox(self) -> Rect:
        r = self.rect.inflate(-10, -8)  # ignore the rounded corners and the drop shadow
        return Rect(r.x - 2, r.y - 2, r.w, r.h)


class PowerUp:
    """Coffee, a croissant or a Blink Mate can: touch it for double points. Doesn't hurt."""

    def __init__(self, x: float, in_air: bool, kind: str, size: tuple[int, int], rng: random.Random):
        self.kind, self.x = kind, x
        self.w, self.h = fit(size, 200, POWERUP_HEIGHT)
        self.base = GROUND_Y - (POWERUP_AIR_HEIGHT if in_air else 0)
        self.t = rng.random() * 10
        self.bottom = float(self.base)
        self.collected = False

    def update(self, dt: float, speed: float) -> None:
        self.x -= speed * dt
        self.t += dt
        self.bottom = self.base + round(math.sin(self.t * 6) * 4)  # a gentle bob

    @property
    def rect(self) -> Rect:
        return Rect(int(self.x), self.bottom - self.h, self.w, self.h)

    @property
    def offscreen(self) -> bool:
        return self.x + self.w < -20

    def hitbox(self) -> Rect:
        return self.rect.inflate(-6, -6)


@dataclass
class Popup:
    text: str
    x: float
    y: float
    age: float = 0.0

    def update(self, dt: float) -> None:
        self.age += dt
        self.y -= 50 * dt

    @property
    def done(self) -> bool:
        return self.age > 1.0


class Doodle:
    """A Miró doodle drifting across the sky: star, crescent moon, dot, squiggle or spiral."""

    KINDS = ("star", "star", "moon", "dot", "dot", "squiggle", "spiral")

    def __init__(self, x: float, rng: random.Random):
        self.x = x
        self.y = rng.randint(24, 120)  # high in the sky: never where obstacles are
        self.kind = rng.choice(self.KINDS)
        self.size = rng.randint(9, 20)
        self.color = rng.randrange(4)  # index into the Miró colours
        self.parallax = rng.uniform(0.12, 0.3)
        self.angle = rng.uniform(0, math.pi)
        self.spin = rng.uniform(-0.6, 0.6)

    def update(self, dt: float, speed: float) -> None:
        self.x -= speed * self.parallax * dt
        self.angle += self.spin * dt


# ------------------------------------------------------------------ the game
@dataclass
class Sizes:
    avatar: tuple[int, int]
    powerups: dict[str, tuple[int, int]]
    obstacles: list[ObstacleKind]

    @classmethod
    def load(cls, folder: Path = ASSETS) -> "Sizes":
        return cls(png_size(folder / "avatar.png"), {k: png_size(folder / f"{k}.png") for k in POWERUPS},
                   load_obstacles(folder / "obstacles"))


@dataclass
class RunnerGame:
    sizes: Sizes
    highscore: int = 0
    rng: random.Random = field(default_factory=random.Random)

    def __post_init__(self) -> None:
        self.state = "title"  # title | play | over
        self.paused = False
        self.doodles = [Doodle(self.rng.randint(0, WIDTH), self.rng) for _ in range(N_DOODLES)]
        self.reset()

    def reset(self) -> None:
        self.player = Player(self.sizes.avatar)
        self.obstacles: list[Obstacle] = []
        self.powerups: list[PowerUp] = []
        self.popups: list[Popup] = []
        self.speed = START_SPEED
        self.score = 0.0
        self.next_spawn = START_SPEED * 1.2  # pixels until the next obstacle
        self.ground_offset = 0.0
        self.over_timer = 0.0
        self.flash_timer = 0.0
        self.killed_by = ""
        self.double_timer = 0.0
        self.double_kind: str | None = None
        self.new_record = False

    def jump(self) -> None:
        """A blink, Space or Up: a jump on the ground, the one extra jump in mid-air."""
        if self.paused:
            return
        if self.state == "title":
            self.state = "play"
            self.player.jump()
        elif self.state == "play":
            if not self.player.jump():
                self.player.extra_jump()  # does nothing if this jump already had its extra one
        elif self.state == "over" and self.over_timer > RESTART_DELAY_S:
            self.reset()
            self.state = "play"

    def _spawn(self) -> None:
        x = WIDTH + 20
        if self.score >= FLYERS_FROM_SCORE and self.rng.random() < 0.3:
            kind = self.rng.choice(("low", "high"))
        else:
            kind = "ground"
        self.obstacles.append(Obstacle(x, kind, self.rng.choice(self.sizes.obstacles), self.rng))
        # Gaps are measured in time, so they stay fair as the speed grows; they also tighten a bit.
        tighten = max(0.75, 1 - (self.speed - START_SPEED) / 2000)
        gap_s = self.rng.uniform(MIN_GAP_S, MAX_GAP_S) * tighten
        self.next_spawn = max(self.speed * gap_s, self.speed * MIN_GAP_S * 0.8)
        if self.rng.random() < POWERUP_CHANCE and not self.powerups and self.double_timer == 0:
            middle = self.obstacles[-1].rect.right + self.next_spawn / 2
            kind = self.rng.choice(POWERUPS)
            self.powerups.append(PowerUp(middle, self.rng.random() < POWERUP_AIR_CHANCE, kind,
                                         self.sizes.powerups[kind], self.rng))

    def update(self, dt: float, down: bool = False) -> None:
        if self.paused:
            return
        p = self.player
        p.ducking = down and p.on_ground
        p.fast_fall = down and not p.on_ground
        for d in self.doodles:
            d.update(dt, self.speed if self.state == "play" else 60)
        self.doodles = [d for d in self.doodles if d.x > -100]
        while len(self.doodles) < N_DOODLES:
            self.doodles.append(Doodle(WIDTH + self.rng.randint(0, 300), self.rng))

        if self.state == "over":
            self.over_timer += dt
            p.splat_age += dt
            return
        if self.state == "title":
            p.update(dt)
            return

        self.speed = min(MAX_SPEED, self.speed + SPEED_GAIN * dt)
        moved = self.speed * dt
        hundreds = int(self.score) // 100
        self.double_timer = max(0.0, self.double_timer - dt)
        self.score += moved * SCORE_RATE * (2 if self.double_timer > 0 else 1)
        if int(self.score) // 100 > hundreds:
            self.flash_timer = 0.8
        self.flash_timer = max(0.0, self.flash_timer - dt)
        self.ground_offset = (self.ground_offset + moved) % 40

        p.update(dt)
        self.next_spawn -= moved
        if self.next_spawn <= 0:
            self._spawn()
        for o in self.obstacles:
            o.update(dt, self.speed)
        self.obstacles = [o for o in self.obstacles if not o.offscreen]

        box = p.hitbox()
        for u in self.powerups:
            u.update(dt, self.speed)
            if box.collides(u.hitbox()):
                u.collected = True
                self.double_timer = DOUBLE_POINTS_S
                self.double_kind = u.kind
                self.popups.append(Popup("2x POINTS!", u.rect.x + u.w / 2, u.rect.y))
        self.powerups = [u for u in self.powerups if not u.offscreen and not u.collected]
        for pop in self.popups:
            pop.update(dt)
        self.popups = [pop for pop in self.popups if not pop.done]

        hit = next((o for o in self.obstacles if box.collides(o.hitbox())), None)
        if hit:
            self.killed_by = hit.joke
            if hit.effect == "poop":
                p.get_splatted(self.rng)
            p.dead = True
            self.state = "over"
            self.over_timer = 0.0
            if int(self.score) > self.highscore:
                self.highscore = int(self.score)
                self.new_record = True
