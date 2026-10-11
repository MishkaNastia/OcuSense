"""Time log: which subject or project you work on, and when (like Toggl, kept on this Mac).

Pure data and rules, no Qt and no files (the file lives in ocusense/timelog_store.py):

  Subject  a course ("subject") or a project, with a name and a Miró colour
  Entry    one stretch of work on a subject: start and end as wall-clock times
           (time.time()), end = None while its timer runs, plus an optional note

Only one timer runs at a time: starting one stops the one that was running. Like Toggl, a
timer can start without a subject (subject_id ""), and get one while it runs or later.
Totals are clipped to a period, so an entry across midnight counts on both days.
"""

import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta

KINDS = ("subject", "project")
# Colour names (ui/time_log_page.py maps them to hex). New ones are only ever added at the end,
# so the colours already saved in timelog.json keep their meaning.
COLOURS = ("cobalt", "vermilion", "golden", "green", "sky", "ink",
           "orange", "rose", "violet", "teal", "ochre", "lime", "plum", "brown", "lilac", "navy", "peach", "stone")
MAX_NAME = 60
MAX_NOTE = 200


NO_SUBJECT = ""  # the subject_id of an entry that has no subject or project (yet)


def new_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class Subject:
    id: str
    name: str
    kind: str = "subject"
    colour: str = "cobalt"
    archived: bool = False

    @classmethod
    def from_dict(cls, values) -> "Subject | None":
        if not isinstance(values, dict):
            return None
        sid, name = values.get("id"), values.get("name")
        if not isinstance(sid, str) or not sid or not isinstance(name, str) or not name.strip():
            return None
        kind = values.get("kind") if values.get("kind") in KINDS else "subject"
        colour = values.get("colour") if values.get("colour") in COLOURS else "cobalt"
        return cls(sid, name.strip()[:MAX_NAME], kind, colour, values.get("archived") is True)


@dataclass
class Entry:
    id: str
    subject_id: str
    start: float
    end: float | None = None  # None: the timer is running
    note: str = ""

    @property
    def running(self) -> bool:
        return self.end is None

    def seconds(self, now: float) -> float:
        return max(0.0, (now if self.end is None else self.end) - self.start)

    def overlap(self, a: float, b: float, now: float) -> float:
        """Seconds of this entry inside [a, b)."""
        end = now if self.end is None else self.end
        return max(0.0, min(end, b) - max(self.start, a))

    @classmethod
    def from_dict(cls, values) -> "Entry | None":
        if not isinstance(values, dict):
            return None
        try:
            start = float(values["start"])
            end = None if values.get("end") is None else float(values["end"])
            item = cls(str(values["id"]), str(values["subject_id"]), start, end, str(values.get("note", ""))[:MAX_NOTE])
        except (KeyError, TypeError, ValueError):
            return None
        if not item.id or (item.end is not None and item.end < item.start):
            return None
        return item


def day_start(day: date) -> float:
    return datetime(day.year, day.month, day.day).timestamp()


def week_monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def period_bounds(period: str, today: date) -> tuple[float, float]:
    """[start, end) as timestamps for "today", "week" (Monday–Sunday), "month" or "all"."""
    if period == "today":
        return day_start(today), day_start(today + timedelta(days=1))
    if period == "week":
        monday = week_monday(today)
        return day_start(monday), day_start(monday + timedelta(days=7))
    if period == "month":
        first = today.replace(day=1)
        following = (first + timedelta(days=32)).replace(day=1)
        return day_start(first), day_start(following)
    return float("-inf"), float("inf")


UNASSIGNED = Subject(NO_SUBJECT, "No project", "subject", "stone")


@dataclass
class TimeLog:
    subjects: list[Subject] = field(default_factory=list)
    entries: list[Entry] = field(default_factory=list)

    # ------------------------------------------------------------ subjects
    def subject(self, sid: str) -> Subject | None:
        return next((s for s in self.subjects if s.id == sid), None)

    def known(self, sid: str) -> bool:
        return sid == NO_SUBJECT or self.subject(sid) is not None

    def shown_subject(self, sid: str) -> Subject:
        """The subject to show for an entry: "No project" when it has none."""
        return self.subject(sid) or UNASSIGNED

    def visible_subjects(self) -> list[Subject]:
        return [s for s in self.subjects if not s.archived]

    def add_subject(self, name: str, kind: str = "subject", colour: str | None = None) -> Subject:
        name = name.strip()[:MAX_NAME]
        if not name:
            raise ValueError("A subject needs a name.")
        if kind not in KINDS:
            raise ValueError(f"Unknown kind {kind!r}")
        if colour not in COLOURS:
            colour = COLOURS[len(self.subjects) % len(COLOURS)]
        subject = Subject(new_id(), name, kind, colour)
        self.subjects.append(subject)
        return subject

    def edit_subject(self, sid: str, name: str | None = None, kind: str | None = None,
                     colour: str | None = None) -> bool:
        subject = self.subject(sid)
        if subject is None:
            return False
        if name is not None and name.strip():
            subject.name = name.strip()[:MAX_NAME]
        if kind in KINDS:
            subject.kind = kind
        if colour in COLOURS:
            subject.colour = colour
        return True

    def remove_subject(self, sid: str) -> bool:
        """Delete a subject together with its entries."""
        if self.subject(sid) is None:
            return False
        self.subjects = [s for s in self.subjects if s.id != sid]
        self.entries = [e for e in self.entries if e.subject_id != sid]
        return True

    # ------------------------------------------------------------ the timer
    def running(self) -> Entry | None:
        live = [e for e in self.entries if e.running]
        return max(live, key=lambda e: e.start) if live else None

    def start(self, sid: str, now: float, note: str = "") -> Entry:
        """Start a timer now; sid may be NO_SUBJECT (choose the subject later)."""
        if not self.known(sid):
            raise ValueError("Unknown subject")
        self.stop(now)
        entry = Entry(new_id(), sid, now, None, note.strip()[:MAX_NOTE])
        self.entries.append(entry)
        return entry

    def stop(self, now: float) -> Entry | None:
        """Stop every running timer (normally one). Returns the one that was shown as running."""
        shown = self.running()
        for entry in self.entries:
            if entry.running:
                entry.end = max(entry.start, now)
        return shown

    def toggle(self, sid: str, now: float) -> Entry | None:
        """Start this subject, or stop it if it is the one running. Returns the running entry afterwards."""
        current = self.running()
        if current is not None and current.subject_id == sid:
            self.stop(now)
            return None
        return self.start(sid, now)

    # ------------------------------------------------------------ entries
    def entry(self, eid: str) -> Entry | None:
        return next((e for e in self.entries if e.id == eid), None)

    def add_entry(self, sid: str, start: float, end: float, note: str = "") -> Entry:
        """A past stretch of work, entered by hand."""
        if not self.known(sid):
            raise ValueError("Unknown subject")
        if end <= start:
            raise ValueError("The end has to be after the start.")
        entry = Entry(new_id(), sid, start, end, note.strip()[:MAX_NOTE])
        self.entries.append(entry)
        return entry

    def edit_entry(self, eid: str, sid: str | None = None, start: float | None = None, end: float | None = None,
                   note: str | None = None) -> None:
        entry = self.entry(eid)
        if entry is None:
            raise ValueError("Unknown entry")
        if sid is not None and not self.known(sid):
            raise ValueError("Unknown subject")
        new_start = entry.start if start is None else start
        new_end = entry.end if end is None else end
        if new_end is not None and new_end <= new_start:
            raise ValueError("The end has to be after the start.")
        entry.subject_id = entry.subject_id if sid is None else sid
        entry.start, entry.end = new_start, new_end
        if note is not None:
            entry.note = note.strip()[:MAX_NOTE]

    def remove_entry(self, eid: str) -> bool:
        before = len(self.entries)
        self.entries = [e for e in self.entries if e.id != eid]
        return len(self.entries) != before

    # ------------------------------------------------------------ totals
    def total(self, a: float, b: float, now: float, sid: str | None = None) -> float:
        return sum(e.overlap(a, b, now) for e in self.entries if sid is None or e.subject_id == sid)

    def totals_by_subject(self, a: float, b: float, now: float) -> list[tuple[Subject, float]]:
        """Subjects with time in [a, b), most time first."""
        rows = [(s, self.total(a, b, now, s.id)) for s in (*self.subjects, UNASSIGNED)]
        return sorted([r for r in rows if r[1] > 0], key=lambda r: -r[1])

    def between(self, a: float, b: float, now: float) -> list[Entry]:
        """Entries touching [a, b), newest first."""
        return sorted((e for e in self.entries if e.overlap(a, b, now) > 0 or (e.running and a <= e.start < b)),
                      key=lambda e: -e.start)

    # ------------------------------------------------------------ file format
    def to_dict(self) -> dict:
        return {"version": 1, "subjects": [asdict(s) for s in self.subjects],
                "entries": [asdict(e) for e in self.entries]}

    @classmethod
    def from_dict(cls, values) -> "TimeLog":
        if not isinstance(values, dict):
            raise ValueError("Not a time log")
        subjects = [s for s in map(Subject.from_dict, values.get("subjects") or []) if s]
        known = {s.id for s in subjects}
        entries = [e for e in map(Entry.from_dict, values.get("entries") or []) if e and (e.subject_id in known or e.subject_id == NO_SUBJECT)]
        return cls(subjects, entries)
