"""Blink Code: Morse code typed with blinks (or the space bar). Pure Python, no interface.

A short closure is a dot, a long one a dash. A pause after the last blink ends the
letter; a longer pause adds a space. Times are seconds (time.monotonic()) passed in
by the caller, so everything here is easy to test.
"""

import random
from dataclasses import dataclass, field

MORSE = {
    "A": ".-", "B": "-...", "C": "-.-.", "D": "-..", "E": ".", "F": "..-.", "G": "--.", "H": "....",
    "I": "..", "J": ".---", "K": "-.-", "L": ".-..", "M": "--", "N": "-.", "O": "---", "P": ".--.",
    "Q": "--.-", "R": ".-.", "S": "...", "T": "-", "U": "..-", "V": "...-", "W": ".--", "X": "-..-",
    "Y": "-.--", "Z": "--..",
}
DECODE = {code: letter for letter, code in MORSE.items()}
# The classic learning order: short, common letters first.
LEARN_ORDER = "ETIANMSOHRDKUWGLFBCPVJXYQZ"
WORDS = ("EYE", "SOS", "HI", "SEE", "BLINK", "FOCUS", "STUDY", "MIRO", "SUN", "MOON", "STAR", "CODE", "WINK",
         "RELAX", "BREAK", "LOOK", "IDEA", "NOTE", "TEA", "SMILE")

DASH_MS = (250, 900)  # range offered for "a dash is longer than …"


def encode(text: str) -> str:
    """'SOS' → '... --- ...' (letters separated by spaces, words by ' / ')."""
    return " / ".join(" ".join(MORSE[c] for c in word if c in MORSE) for word in text.upper().split())


@dataclass
class Symbol:
    mark: str  # "." or "-"
    duration: float  # seconds the eyes (or the key) stayed closed


@dataclass
class DecoderEvent:
    kind: str  # "symbol", "letter", "space"
    symbol: Symbol | None = None
    code: str = ""  # for letters: the dots and dashes
    letter: str | None = None  # None when the code isn't a letter


@dataclass
class MorseDecoder:
    dash_seconds: float = 0.45  # closures at least this long are dashes
    letter_gap: float = 1.2  # this long without a blink ends the letter
    word_gap: float = 2.6  # this long ends the word (adds a space once)
    code: str = ""
    _last_end: float | None = None
    _spaced: bool = True

    def closure(self, start: float, end: float) -> DecoderEvent:
        """One finished closure (a blink, or a key press) from start to end."""
        duration = max(0.0, end - start)
        symbol = Symbol("-" if duration >= self.dash_seconds - 1e-9 else ".", duration)  # exactly the line: a dash
        self.code += symbol.mark
        self._last_end = end
        self._spaced = False
        return DecoderEvent("symbol", symbol=symbol)

    def tick(self, now: float) -> DecoderEvent | None:
        """Call regularly: ends the letter (and later the word) after a pause."""
        if self._last_end is None:
            return None
        quiet = now - self._last_end
        if self.code and quiet >= self.letter_gap:
            code, self.code = self.code, ""
            return DecoderEvent("letter", code=code, letter=DECODE.get(code))
        if not self.code and not self._spaced and quiet >= self.word_gap:
            self._spaced = True
            return DecoderEvent("space")
        return None

    def letter_progress(self, now: float) -> float:
        """0 → 1 while waiting for the pause that ends the letter (for the on-screen fuse)."""
        if not self.code or self._last_end is None:
            return 0.0
        return min(1.0, (now - self._last_end) / self.letter_gap)

    def reset(self) -> None:
        self.code, self._last_end, self._spaced = "", None, True


# ------------------------------------------------------------------ game modes
@dataclass
class LearnGame:
    """Blink the shown letter; every 3 in a row unlocks the next letter of LEARN_ORDER."""
    unlocked: int = 2  # E and T to start
    streak: int = 0
    best_streak: int = 0
    correct: int = 0
    target: str = "E"
    rng: random.Random = field(default_factory=random.Random)

    def next_target(self) -> str:
        pool = LEARN_ORDER[:self.unlocked]
        newest = LEARN_ORDER[self.unlocked - 1]
        # a new letter shows up often until it is practised
        self.target = newest if self.rng.random() < 0.4 else self.rng.choice(pool)
        return self.target

    def answer(self, letter: str | None) -> tuple[bool, bool]:
        """Returns (right, unlocked a new letter)."""
        if letter == self.target:
            self.correct += 1
            self.streak += 1
            self.best_streak = max(self.best_streak, self.streak)
            if self.streak % 3 == 0 and self.unlocked < len(LEARN_ORDER):
                self.unlocked += 1
                return True, True
            return True, False
        self.streak = 0
        return False, False


@dataclass
class ChallengeGame:
    """Spell words against the clock. Points grow with the combo; a wrong letter breaks it."""
    seconds: float = 90.0
    started_at: float | None = None
    score: int = 0
    combo: int = 0
    best_combo: int = 0
    words_done: int = 0
    word: str = ""
    position: int = 0
    rng: random.Random = field(default_factory=random.Random)

    def start(self, now: float) -> None:
        self.started_at, self.score, self.combo, self.best_combo, self.words_done = now, 0, 0, 0, 0
        self.new_word()

    def new_word(self) -> str:
        self.word = self.rng.choice([w for w in WORDS if w != self.word])
        self.position = 0
        return self.word

    def remaining(self, now: float) -> float:
        return 0.0 if self.started_at is None else max(0.0, self.seconds - (now - self.started_at))

    def over(self, now: float) -> bool:
        return self.started_at is not None and self.remaining(now) <= 0

    @property
    def expected(self) -> str:
        return self.word[self.position]

    def answer(self, letter: str | None) -> tuple[bool, bool]:
        """Returns (right, finished the word)."""
        if letter == self.expected:
            self.combo += 1
            self.best_combo = max(self.best_combo, self.combo)
            self.score += 10 * min(5, 1 + self.combo // 3)  # ×1 … ×5
            self.position += 1
            if self.position == len(self.word):
                self.words_done += 1
                self.score += 25 * len(self.word)  # word bonus
                self.new_word()
                return True, True
            return True, False
        self.combo = 0
        return False, False
