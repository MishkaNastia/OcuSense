"""Keeps track of the OcuSense account in the window, running Supabase calls off the UI thread.

Every call ends in a callback on the UI thread with (ok, result or message), and
`changed` is emitted whenever who is signed in changes. With no Supabase project
set up (see ocusense/accounts.py) `configured` is False and nothing is attempted.
The leaderboard and friends calls (ocusense/leaderboards.py) go through here too, so
they share the sign-in and its token renewal.
"""

import threading
import time

from PySide6.QtCore import QObject, Signal

from ocusense.accounts import (
    Account, AccountStore, AuthClient, AuthError, NetworkError, SignedIn, load_config,
)
from ocusense.leaderboards import LeaderboardClient


class AccountService(QObject):
    changed = Signal(object)  # Account or None
    _finished = Signal(object, object)  # (callback, (ok, value)) — delivered on the UI thread

    def __init__(self, client: AuthClient | None = None, store: AccountStore | None = None,
                 synchronous: bool = False, leaderboards: LeaderboardClient | None = None, parent=None):
        super().__init__(parent)
        if client is None:
            config = load_config()
            client = AuthClient(config) if config else None
        self.client = client
        if leaderboards is None and isinstance(client, AuthClient):
            leaderboards = LeaderboardClient(client)
        self.leaderboards = leaderboards  # None without a Supabase project
        self.store = store or AccountStore()
        self.synchronous = synchronous  # tests: run calls right away
        self.session: SignedIn | None = None
        self.offline = False  # signed in on this Mac, but Supabase couldn't be reached yet
        self.busy = False
        self._token_lock = threading.Lock()  # background calls renew the token one at a time
        self.account: Account | None = self.store.load() if self.configured else None
        self._finished.connect(lambda callback, outcome: callback(*outcome))

    @property
    def configured(self) -> bool:
        return self.client is not None

    # ------------------------------------------------------------ plumbing
    def _run(self, work, done, busy: bool = True) -> None:
        """busy=False for leaderboard and friends calls: they don't lock the account form."""
        def call():
            try:
                return True, work()
            except NetworkError as error:
                return False, error
            except AuthError as error:
                return False, error
            except Exception:  # never let a surprise from the network take the window down
                return False, AuthError("Something went wrong. Please try again.")

        def finish(ok, value):
            if busy:
                self.busy = False
            done(ok, value)

        if busy:
            self.busy = True
        if self.synchronous:
            finish(*call())
        else:
            threading.Thread(target=lambda: self._finished.emit(finish, call()), daemon=True).start()

    def _set(self, account: Account | None) -> None:
        self.account = account
        self.changed.emit(account)

    def _signed_in(self, session: SignedIn) -> None:
        self.session, self.offline = session, False
        self.store.save(session)
        self._set(session.account)

    def _access_token(self) -> str:
        """A fresh access token (blocking; call inside _run). Refreshes once it is close to expiring."""
        with self._token_lock:
            if self.session is None or self.session.expires_at - time.time() < 60:
                token = self.session.refresh_token if self.session else self.store.tokens.load()
                if not token:
                    raise AuthError("Please log in again.")
                self.session = self.client.refresh(token)
                self.store.save(self.session)
            return self.session.access_token

    # ------------------------------------------------------------ actions
    def restore(self) -> None:
        """At launch: renew the saved sign-in in the background."""
        if not self.configured or self.account is None:
            return

        def done(ok, value):
            if ok:
                self._signed_in(value)
            elif isinstance(value, NetworkError):
                self.offline = True  # keep the account; try again next launch
                self._set(self.account)
            else:
                self.store.clear()  # the sign-in expired or was revoked
                self._set(None)

        token = self.store.tokens.load()
        if not token:
            self.store.clear()
            self._set(None)
            return
        self._run(lambda: self.client.refresh(token), done)

    def sign_in(self, email: str, password: str, done) -> None:
        def finished(ok, value):
            if ok:
                self._signed_in(value)
            done(ok, value)
        self._run(lambda: self.client.sign_in(email, password), finished)

    def sign_up(self, email: str, password: str, username: str, done) -> None:
        """done(True, None) means: check your inbox to confirm."""
        def finished(ok, value):
            if ok and value is not None:
                self._signed_in(value)
            done(ok, value)
        self._run(lambda: self.client.sign_up(email, password, username), finished)

    def request_reset(self, email: str, done) -> None:
        self._run(lambda: self.client.request_reset(email), done)

    def set_username(self, username: str, done) -> None:
        def finished(ok, value):
            if ok:
                self.store.save_account(value)
                if self.session:
                    self.session.account = value
                self._set(value)
            done(ok, value)
        self._run(lambda: self.client.set_username(self._access_token(), username), finished)

    def sign_out(self) -> None:
        """Signs out on this Mac right away; telling Supabase is best effort."""
        session = self.session
        self.session, self.offline = None, False
        self.store.clear()
        self._set(None)
        if session is not None:
            self._run(lambda: self.client.sign_out(session.access_token), lambda ok, value: None)

    # ------------------------------------------------------------ leaderboards and friends
    @property
    def signed_in(self) -> bool:
        return self.account is not None and self.leaderboards is not None

    def _with_token(self, work, done) -> None:
        """Run work(access_token) in the background; done(False, AuthError) when not signed in."""
        if not self.signed_in:
            done(False, AuthError("Log in to use this."))
            return
        self._run(lambda: work(self._access_token()), done, busy=False)

    def submit_scores(self, items, done) -> None:
        """Upload ScoreBook.Pending items one by one; done(ok, the items that were saved)."""
        def work(token):
            saved = []
            try:
                for item in items:
                    self.leaderboards.submit(token, item.game, item.score, item.details)
                    saved.append(item)
            except AuthError:
                if not saved:
                    raise
            return saved
        self._with_token(work, done)

    def leaderboard(self, game: str, scope: str, done) -> None:
        """scope "everyone" works signed out too; "friends" needs a sign-in."""
        if self.leaderboards is None:
            done(False, AuthError("Online leaderboards need OcuSense accounts."))
        elif scope == "everyone" and self.account is None:
            self._run(lambda: self.leaderboards.leaderboard(game, scope), done, busy=False)
        else:
            self._with_token(lambda token: self.leaderboards.leaderboard(game, scope, token), done)

    def friends(self, done) -> None:
        self._with_token(lambda token: self.leaderboards.friends(token), done)

    def request_friend(self, username: str, done) -> None:
        self._with_token(lambda token: self.leaderboards.request_friend(token, username), done)

    def respond_friend(self, user_id: str, accept: bool, done) -> None:
        self._with_token(lambda token: self.leaderboards.respond_friend(token, user_id, accept), done)

    def remove_friend(self, user_id: str, done) -> None:
        self._with_token(lambda token: self.leaderboards.remove_friend(token, user_id), done)
