"""The game scores kept on this Mac: each game's top scores, and scores waiting to be uploaded.

    ~/Library/Application Support/OcuSense/scores.json

Works without an account. A score played while signed in also goes into `pending`
until it reaches the online leaderboard (ocusense/leaderboards.py); a score played
while signed out stays on this Mac only, so nobody can claim it for an account later.
OCUSENSE_SCORES_FILE overrides the file; with only OCUSENSE_PREFERENCES_FILE set (tests),
it sits next to that file. A damaged file never stops the app: it starts empty.
"""

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ocusense.system import user_data_dir

# Game ids as on the server (supabase/schema.sql) → names shown in the app.
GAMES = {"blink_code_challenge": "Blink Code challenge", "eye_runner": "EyeGame"}
KEEP = 10  # top scores kept per game on this Mac
MAX_PENDING = 100  # uploads waiting; the oldest are dropped beyond this
MAX_SCORE = 100_000  # the server's limit too


def default_path() -> Path:
    override = os.environ.get("OCUSENSE_SCORES_FILE")
    if override:
        return Path(override)
    preferences = os.environ.get("OCUSENSE_PREFERENCES_FILE")
    if preferences:
        return Path(preferences).with_name("scores.json")
    return user_data_dir() / "scores.json"  # ~/Library/Application Support/OcuSense on a Mac (ocusense/system.py)


@dataclass
class Entry:
    score: int
    at: float | None  # time.time() when it was played; None = an earlier high score (from before this file)
    details: dict = field(default_factory=dict)
    username: str = ""  # the account it was played with, if any

    @classmethod
    def from_dict(cls, values) -> "Entry | None":
        try:
            score = values["score"]
            at = values.get("at")
            if not isinstance(score, int) or isinstance(score, bool) or not 0 <= score <= MAX_SCORE:
                return None
            if at is not None and not isinstance(at, (int, float)):
                return None
            details = values.get("details") if isinstance(values.get("details"), dict) else {}
            return cls(score, at, details, str(values.get("username", "") or ""))
        except (KeyError, TypeError, AttributeError):
            return None


@dataclass
class Pending:
    game: str
    score: int
    at: float
    user_id: str
    details: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, values) -> "Pending | None":
        try:
            item = cls(str(values["game"]), values["score"], float(values["at"]), str(values["user_id"]),
                       values.get("details") if isinstance(values.get("details"), dict) else {})
        except (KeyError, TypeError, ValueError, AttributeError):
            return None
        valid = (item.game in GAMES and item.user_id and isinstance(item.score, int)
                 and not isinstance(item.score, bool) and 0 <= item.score <= MAX_SCORE)
        return item if valid else None


def _order(entry: Entry):
    return (-entry.score, entry.at if entry.at is not None else float("-inf"))  # ties: the earlier one first


class ScoreBook:
    def __init__(self, path: Path | None = None):
        self.path = path or default_path()
        self.top: dict[str, list[Entry]] = {game: [] for game in GAMES}
        self.pending: list[Pending] = []
        self._load()

    # ------------------------------------------------------------ reading
    def _load(self) -> None:
        try:
            values = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return
        if not isinstance(values, dict):
            return
        for game in GAMES:
            items = values.get("top", {}).get(game, []) if isinstance(values.get("top"), dict) else []
            entries = [e for e in map(Entry.from_dict, items if isinstance(items, list) else []) if e]
            self.top[game] = sorted(entries, key=_order)[:KEEP]
        items = values.get("pending", [])
        self.pending = [p for p in map(Pending.from_dict, items if isinstance(items, list) else []) if p]

    def best(self, game: str) -> int:
        return self.top[game][0].score if self.top[game] else 0

    def entries(self, game: str) -> list[Entry]:
        return list(self.top[game])

    # ------------------------------------------------------------ writing
    def seed(self, game: str, high_score: int) -> None:
        """Keep a high score from before this file existed (preferences.json) as an undated entry."""
        if high_score > 0 and not self.top[game]:
            self.top[game] = [Entry(min(high_score, MAX_SCORE), None)]
            self.save()

    def record(self, game: str, score: int, details: dict | None = None, user_id: str = "",
               username: str = "", now: float | None = None) -> int | None:
        """Add a finished game. Returns its place on this Mac (1 = best), or None outside the top KEEP.

        With a user_id (signed in), the score is also queued for the online leaderboard.
        """
        if game not in GAMES:
            raise ValueError(f"Unknown game {game!r}")
        score = max(0, min(int(score), MAX_SCORE))
        now = time.time() if now is None else now
        entry = Entry(score, now, dict(details or {}), username)
        ranked = sorted([*self.top[game], entry], key=_order)
        self.top[game] = ranked[:KEEP]
        if user_id:
            self.pending.append(Pending(game, score, now, user_id, dict(details or {})))
            self.pending = self.pending[-MAX_PENDING:]
        self.save()
        return next((i + 1 for i, e in enumerate(self.top[game]) if e is entry), None)

    def pending_for(self, user_id: str) -> list[Pending]:
        return [p for p in self.pending if p.user_id == user_id]

    def mark_uploaded(self, items) -> None:
        done = {id(p) for p in items}
        self.pending = [p for p in self.pending if id(p) not in done]
        self.save()

    def save(self) -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps({
                "top": {game: [asdict(e) for e in entries] for game, entries in self.top.items()},
                "pending": [asdict(p) for p in self.pending]}, indent=2) + "\n")
            temporary.replace(self.path)
        except OSError:
            return False  # not critical: the scores still show until OcuSense quits
        return True
