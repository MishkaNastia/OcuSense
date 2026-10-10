"""Where completed session summaries are kept.

For now they live in memory and are forgotten when the app quits. A version
that saves summaries (numbers only, never images) to a file on this Mac can
replace SessionStore later without changing the rest of the app.
"""

from ocusense.core.models import SessionSummary


class SessionStore:
    """Completed sessions, in memory only."""

    def __init__(self, sessions: list[SessionSummary] | None = None):
        self._sessions = list(sessions or [])

    def add(self, summary: SessionSummary) -> None:
        self._sessions.append(summary)

    def all(self) -> list[SessionSummary]:
        return sorted(self._sessions, key=lambda s: s.started_at)

    def clear(self) -> None:
        self._sessions.clear()
