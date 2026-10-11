"""Game leaderboards: the scores on this Mac, your friends' and everyone's.

ScoreKeeper records every finished Blink Code challenge and EyeGame run in the
ScoreBook (ocusense/scores.py) and, when you are signed in, uploads it through the
AccountService — straight away, or the next time OcuSense is online. LeaderboardView
shows one game at a time:
    On this Mac   your top scores here, with or without an account
    Friends       you and the friends you've added (Account page), best score each
    Everyone      every player with a username, best score each
"""

from datetime import datetime

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QVBoxLayout, QWidget

from ocusense.leaderboards import NotSetUp
from ocusense.scores import GAMES, ScoreBook

from . import theme
from .account_service import AccountService
from .widgets.common import button, label
from .widgets.segmented import Segmented

SCOPES = (("mac", "On this Mac"), ("friends", "Friends"), ("everyone", "Everyone"))
GAME_CHOICES = tuple(GAMES.items())


class ScoreKeeper(QObject):
    """Where finished games go. `changed(game)` after a new local score or a finished upload."""
    changed = Signal(str)

    def __init__(self, service: AccountService, preferences=None, book: ScoreBook | None = None, parent=None):
        super().__init__(parent)
        self.service = service
        self.book = book or ScoreBook()
        if preferences is not None:  # high scores from before the score book existed
            self.book.seed("blink_code_challenge", preferences.morse_high_score)
            self.book.seed("eye_runner", preferences.runner_high_score)
        self.uploading = False
        self.last_problem = ""
        service.changed.connect(lambda _account: self.sync())

    def record(self, game: str, score: int, details: dict | None = None) -> int | None:
        """Keep a finished game; returns its place on this Mac (1 = best) or None outside the top 10."""
        account = self.service.account if self.service.signed_in else None
        place = self.book.record(game, score, details, user_id=account.user_id if account else "",
                                 username=account.username if account else "")
        self.changed.emit(game)
        self.sync()
        return place

    def sync(self) -> None:
        """Upload this account's waiting scores (best effort; they stay queued on failure)."""
        account = self.service.account
        if self.uploading or account is None or not self.service.signed_in or self.service.offline:
            return
        items = self.book.pending_for(account.user_id)
        if not items:
            return
        self.uploading = True

        def done(ok, value):
            self.uploading = False
            if ok:
                self.book.mark_uploaded(value)
                self.last_problem = ""
                for game in {item.game for item in value}:
                    self.changed.emit(game)
            else:
                self.last_problem = str(value)
        self.service.submit_scores(items, done)


def _date(at) -> str:
    if at is None:
        return "earlier"
    if isinstance(at, str):
        try:
            at = datetime.fromisoformat(at.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return ""
    return f"{datetime.fromtimestamp(at):%d %b %Y}"


class LeaderboardView(QWidget):
    rendered = Signal()  # the rows changed, so the page may need a new height

    def __init__(self, keeper: ScoreKeeper, open_account=None, parent=None):
        super().__init__(parent)
        self.keeper = keeper
        self.service = keeper.service
        self.open_account = open_account  # shows the Account page (log in, add friends)
        self.game, self.scope = GAME_CHOICES[0][0], "mac"
        self.online: dict[tuple[str, str], list] = {}  # (game, scope) -> the last rows fetched
        self._asked: tuple[str, str] | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        controls = QHBoxLayout()
        controls.setSpacing(12)
        self.game_switch = Segmented(GAME_CHOICES, self.game, "Game")
        self.game_switch.changed.connect(self.set_game)
        self.scope_switch = Segmented(SCOPES, self.scope, "Whose scores")
        self.scope_switch.changed.connect(self.set_scope)
        controls.addWidget(self.game_switch)
        controls.addWidget(self.scope_switch)
        controls.addStretch(1)
        self.refresh_button = button("Refresh", "quiet")
        self.refresh_button.clicked.connect(lambda: self.render(fetch=True))
        controls.addWidget(self.refresh_button)
        layout.addLayout(controls)

        self.table = QWidget()
        self.grid = QGridLayout(self.table)
        self.grid.setContentsMargins(0, 4, 0, 4)
        self.grid.setHorizontalSpacing(24)
        self.grid.setVerticalSpacing(6)
        layout.addWidget(self.table)
        note = QHBoxLayout()
        self.status = label("", "secondary", theme.ui_font(13), wrap=True)
        note.addWidget(self.status, 1)
        self.account_button = button("Log in", "secondary")
        self.account_button.clicked.connect(lambda: self.open_account and self.open_account())
        note.addWidget(self.account_button, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(note)

        keeper.changed.connect(self._score_changed)
        self.service.changed.connect(lambda _account: (self.online.clear(), self.render(fetch=True)))
        self.render()

    # ------------------------------------------------------------ choices
    def set_game(self, game: str) -> None:
        self.game = game
        self.render(fetch=(game, self.scope) not in self.online)

    def set_scope(self, scope: str) -> None:
        self.scope = scope
        self.render(fetch=(self.game, scope) not in self.online)

    def _score_changed(self, game: str) -> None:
        if game == self.game:
            self.render(fetch=self.scope != "mac")

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self.scope != "mac":
            self.render(fetch=True)

    # ------------------------------------------------------------ display
    def _rows(self, rows) -> None:
        """rows: [(place, name, score, date, highlight)]."""
        while self.grid.count():
            widget = self.grid.takeAt(0).widget()
            if widget is not None:
                widget.setParent(None)  # gone at once, not only once Qt gets round to deleting it
                widget.deleteLater()
        for column, title in enumerate(("#", "Player", "Score", "Date")):
            self.grid.addWidget(label(title, "secondary", theme.ui_font(12, QFont.Weight.Bold)), 0, column)
        for r, (place, name, score, date, highlight) in enumerate(rows, start=1):
            weight = QFont.Weight.Bold if highlight else QFont.Weight.Normal
            cells = (label(str(place), font=theme.number_font(15, weight)),
                     label(name, font=theme.ui_font(15, weight)),
                     label(f"{score:,}".replace(",", " "), font=theme.number_font(15, weight)),
                     label(date, "secondary", theme.ui_font(13)))
            for column, cell in enumerate(cells):
                if highlight:
                    cell.setStyleSheet(f"color: {theme.COBALT};")
                self.grid.addWidget(cell, r, column,
                                    Qt.AlignmentFlag.AlignRight if column == 2 else Qt.AlignmentFlag.AlignLeft)
        self.grid.setColumnStretch(1, 1)
        self.grid.setColumnStretch(3, 1)
        self.table.setVisible(bool(rows))
        self.table.adjustSize()
        self.rendered.emit()

    def render(self, fetch: bool = False) -> None:
        self.game_switch.set_current(self.game)
        self.scope_switch.set_current(self.scope)
        self.account_button.setVisible(False)
        self.refresh_button.setVisible(self.scope != "mac")
        if self.scope == "mac":
            self._render_mac()
            return
        if not self.service.configured:
            self._rows([])
            self.status.setText("Online leaderboards need OcuSense accounts, which aren’t set up in this copy "
                                "(see docs/accounts.md). Your scores on this Mac are always kept.")
            return
        if self.scope == "friends" and self.service.account is None:
            self._rows([])
            self.status.setText("Log in to compare scores with your friends.")
            self.account_button.setText("Log in")
            self.account_button.setVisible(True)
            return
        key = (self.game, self.scope)
        if key in self.online:
            self._render_online(self.online[key])
        else:
            self._rows([])
            self.status.setText("Loading…")
        if fetch:
            self._fetch(key)

    def _render_mac(self) -> None:
        entries = self.keeper.book.entries(self.game)
        account = self.service.account
        self._rows([(i + 1, f"@{e.username}" if e.username else "You", e.score, _date(e.at),
                     bool(account and e.username and e.username == account.username))
                    for i, e in enumerate(entries)])
        waiting = len(self.keeper.book.pending_for(account.user_id)) if account else 0
        text = ("No scores yet. Play a game and your best ones show up here." if not entries
                else f"Your top {len(entries)} on this Mac.")
        if waiting:
            text += f" {waiting} score{'s' if waiting != 1 else ''} waiting to go online."
        elif self.service.configured and account is None and entries:
            text += " Log in before you play to put your scores online."
        self.status.setText(text)

    def _render_online(self, rows) -> None:
        account = self.service.account
        self._rows([(r.place, f"@{r.username}", r.score, _date(r.created_at), r.is_me) for r in rows])
        if not rows:
            self.status.setText("No scores yet. Be the first!" if self.scope == "everyone" else
                                "No scores yet from you or your friends. Add friends on the Account page.")
        elif self.scope == "friends":
            self.status.setText("You and your friends, best score each. Add friends on the Account page.")
        else:
            self.status.setText("Every player’s best score.")
        if account is not None and not account.username:
            self.status.setText(self.status.text() + " Choose a username on the Account page to appear here.")
        if self.scope == "friends" or (account is not None and not account.username):
            self.account_button.setText("Manage friends" if self.scope == "friends" else "Choose a username")
            self.account_button.setVisible(True)
        if self.keeper.last_problem:
            self.status.setText(self.status.text() + f" Couldn’t upload yet: {self.keeper.last_problem}")

    def _fetch(self, key) -> None:
        self._asked = key

        def done(ok, value):
            if ok:
                self.online[key] = value
            if self._asked != key or (self.game, self.scope) != key:
                return  # the person has moved on to another game or scope
            if ok:
                self._render_online(value)
            elif isinstance(value, NotSetUp) or key not in self.online:
                self._rows([])
                self.status.setText(str(value))
            else:
                self.status.setText(f"Showing the last scores we fetched ({value})")
        self.service.leaderboard(*key, done)
