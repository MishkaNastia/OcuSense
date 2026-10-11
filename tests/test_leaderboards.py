"""Leaderboards and friends: the score book on this Mac, the Supabase calls (network faked), uploads,
the Leaderboards view in Games, the Friends section on the Account page, and the games' hooks.

The SQL itself (supabase/schema.sql) needs a Postgres server; docs/accounts.md says how it was checked.
"""

import json
import os
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from ocusense.accounts import Account, AccountStore, AuthClient, AuthError, FileTokens, SignedIn  # noqa: E402
from ocusense.leaderboards import Friend, LeaderboardClient, NotSetUp, Row  # noqa: E402
from ocusense.scores import KEEP, ScoreBook, default_path  # noqa: E402
from ocusense.ui.account_service import AccountService  # noqa: E402
from ocusense.ui.friends_panel import FriendsPanel  # noqa: E402
from ocusense.ui.leaderboard_view import LeaderboardView, ScoreKeeper  # noqa: E402
from tests.test_accounts import CONFIG, FakeClient, FakeResponse, http_error  # noqa: E402

app = QApplication.instance() or QApplication([])


def temp_book() -> ScoreBook:
    return ScoreBook(Path(tempfile.mkdtemp()) / "scores.json")


class ScoreBookTest(unittest.TestCase):
    def test_places_ties_and_the_top_ten(self):
        book = temp_book()
        self.assertEqual(book.record("eye_runner", 100, now=1), 1)
        self.assertEqual(book.record("eye_runner", 300, now=2), 1)
        self.assertEqual(book.record("eye_runner", 100, now=3), 3)  # a tie goes after the earlier one
        self.assertEqual([e.score for e in book.entries("eye_runner")], [300, 100, 100])
        self.assertEqual([e.at for e in book.entries("eye_runner")], [2, 1, 3])
        for i in range(KEEP):
            book.record("eye_runner", 1000 + i, now=10 + i)
        self.assertEqual(len(book.entries("eye_runner")), KEEP)
        self.assertIsNone(book.record("eye_runner", 5, now=99))  # not in the top 10
        self.assertEqual(book.best("eye_runner"), 1009)
        self.assertEqual(book.best("blink_code_challenge"), 0)
        with self.assertRaises(ValueError):
            book.record("chess", 1)

    def test_only_signed_in_scores_wait_for_upload(self):
        book = temp_book()
        book.record("blink_code_challenge", 50)
        book.record("blink_code_challenge", 70, {"words": 2}, user_id="u1", username="mira")
        self.assertEqual([p.score for p in book.pending_for("u1")], [70])
        self.assertEqual(book.pending_for("u2"), [])
        book.mark_uploaded(book.pending_for("u1"))
        self.assertEqual(book.pending, [])
        self.assertEqual(book.entries("blink_code_challenge")[0].username, "mira")

    def test_kept_between_launches_and_robust_to_damage(self):
        book = temp_book()
        book.record("eye_runner", 120, user_id="u1")
        again = ScoreBook(book.path)
        self.assertEqual(again.best("eye_runner"), 120)
        self.assertEqual(len(again.pending), 1)
        book.path.write_text("{not json")
        self.assertEqual(ScoreBook(book.path).best("eye_runner"), 0)
        book.path.write_text(json.dumps({"top": {"eye_runner": [{"score": -5, "at": 1}, {"score": True, "at": 1},
                                                                 {"score": 40, "at": "x"}, {"score": 30, "at": 2}]},
                                         "pending": [{"game": "chess", "score": 1, "at": 1, "user_id": "u"}]}))
        damaged = ScoreBook(book.path)
        self.assertEqual([e.score for e in damaged.entries("eye_runner")], [30])
        self.assertEqual(damaged.pending, [])

    def test_earlier_high_score_is_kept_once(self):
        book = temp_book()
        book.seed("eye_runner", 250)
        book.seed("eye_runner", 999)  # only into an empty list
        book.seed("blink_code_challenge", 0)
        self.assertEqual([(e.score, e.at) for e in book.entries("eye_runner")], [(250, None)])
        self.assertEqual(book.entries("blink_code_challenge"), [])
        self.assertEqual(book.record("eye_runner", 300, now=5), 1)

    def test_file_sits_next_to_the_test_preferences(self):
        with mock.patch.dict(os.environ, {"OCUSENSE_PREFERENCES_FILE": "/tmp/x/preferences.json"}, clear=True):
            self.assertEqual(default_path(), Path("/tmp/x/scores.json"))
        with mock.patch.dict(os.environ, {"OCUSENSE_SCORES_FILE": "/tmp/y.json"}, clear=True):
            self.assertEqual(default_path(), Path("/tmp/y.json"))


class LeaderboardClientTest(unittest.TestCase):
    def setUp(self):
        self.client = LeaderboardClient(AuthClient(CONFIG))
        self.requests, self.replies = [], []

    def fake_urlopen(self, request, timeout, context):
        self.requests.append(request)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return FakeResponse(b"" if reply is None else json.dumps(reply).encode())

    def run_with(self, *replies):
        self.replies = list(replies)
        return mock.patch("urllib.request.urlopen", self.fake_urlopen)

    def test_submit_a_score(self):
        with self.run_with(None):
            self.client.submit("a1", "eye_runner", 512, {"x": 1})
        request = self.requests[0]
        self.assertTrue(request.full_url.endswith("/rest/v1/game_scores"))
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Authorization"), "Bearer a1")
        self.assertEqual(request.get_header("Prefer"), "return=minimal")
        self.assertEqual(json.loads(request.data), {"game": "eye_runner", "score": 512, "details": {"x": 1}})

    def test_read_a_leaderboard(self):
        reply = [{"place": 1, "username": "nastia", "score": 500, "created_at": "2026-10-11T09:00:00+00:00",
                  "is_me": False},
                 {"place": 2, "username": "mira", "score": 420, "created_at": "2026-10-11T10:00:00Z", "is_me": True},
                 {"place": "?", "username": "broken"}]
        with self.run_with(reply):
            rows = self.client.leaderboard("blink_code_challenge", "friends", "a1", limit=10)
        self.assertEqual(json.loads(self.requests[0].data),
                         {"game_name": "blink_code_challenge", "scope": "friends", "max_rows": 10})
        self.assertTrue(self.requests[0].full_url.endswith("/rest/v1/rpc/game_leaderboard"))
        self.assertEqual([r.username for r in rows], ["nastia", "mira"])
        self.assertTrue(rows[1].is_me)
        with self.run_with([]):
            self.client.leaderboard("eye_runner")  # everyone, signed out: only the publishable key
        self.assertIsNone(self.requests[1].get_header("Authorization"))
        with self.assertRaises(ValueError):
            self.client.leaderboard("eye_runner", "galaxy")

    def test_friends_calls(self):
        friends = [{"user_id": "u2", "username": "nastia", "status": "incoming"},
                   {"user_id": "u3", "username": "olek", "status": "weird"}]
        with self.run_with(friends, "accepted", "declined", None):
            self.assertEqual(self.client.friends("a1"), [Friend("u2", "nastia", "incoming")])
            self.assertEqual(self.client.request_friend("a1", "nastia"), "accepted")
            self.assertEqual(self.client.respond_friend("a1", "u2", False), "declined")
            self.client.remove_friend("a1", "u2")
        self.assertEqual(json.loads(self.requests[1].data), {"name": "nastia"})
        self.assertEqual(json.loads(self.requests[2].data), {"other": "u2", "accept": False})
        self.assertTrue(self.requests[3].full_url.endswith("/rpc/remove_friend"))

    def test_server_without_the_tables(self):
        missing = http_error(404, {"code": "PGRST202", "message": "Could not find the function"})
        with self.run_with(missing):
            with self.assertRaises(NotSetUp):
                self.client.leaderboard("eye_runner")
        with self.run_with(http_error(400, {"code": "23514", "message": "violates check constraint"})):
            with self.assertRaises(AuthError) as caught:
                self.client.submit("a1", "eye_runner", 1)
        self.assertNotIsInstance(caught.exception, NotSetUp)
        with self.run_with(urllib.error.URLError("offline")):
            with self.assertRaisesRegex(AuthError, "couldn’t reach"):
                self.client.friends("a1")


class FakeLeaderboards:
    def __init__(self):
        self.calls, self.fail, self.scores = [], None, []
        self.board = {("blink_code_challenge", "everyone"): [Row(1, "nastia", 500, "2026-10-11T09:00:00Z"),
                                                             Row(2, "mira", 420, "2026-10-11T10:00:00Z", True)]}
        self.people = [Friend("u2", "nastia", "incoming"), Friend("u3", "olek", "friend")]

    def _call(self, *args):
        self.calls.append(args)
        if self.fail:
            raise self.fail

    def submit(self, token, game, score, details):
        self._call("submit", token, game, score)
        self.scores.append((game, score))

    def leaderboard(self, game, scope="everyone", token=None, limit=50):
        self._call("leaderboard", game, scope, token)
        return self.board.get((game, scope), [])

    def friends(self, token):
        self._call("friends", token)
        return list(self.people)

    def request_friend(self, token, username):
        self._call("request", username)
        return "requested"

    def respond_friend(self, token, user_id, accept):
        self._call("respond", user_id, accept)
        self.people = [Friend(f.user_id, f.username, "friend") if f.user_id == user_id and accept else f
                       for f in self.people if f.user_id != user_id or accept]
        return "accepted" if accept else "declined"

    def remove_friend(self, token, user_id):
        self._call("remove", user_id)
        self.people = [f for f in self.people if f.user_id != user_id]


class OnlineTest(unittest.TestCase):
    def setUp(self):
        folder = Path(tempfile.mkdtemp())
        self.store = AccountStore(folder / "account.json", FileTokens(folder / "token"))
        self.client = FakeClient()
        self.boards = FakeLeaderboards()
        self.service = AccountService(self.client, self.store, synchronous=True, leaderboards=self.boards)
        self.keeper = ScoreKeeper(self.service, book=ScoreBook(folder / "scores.json"))

    def sign_in(self):
        self.service.sign_in("mira@example.com", "secret123", lambda ok, value: None)

    def test_scores_upload_when_signed_in_and_wait_when_not(self):
        self.keeper.record("eye_runner", 80)  # signed out: this Mac only
        self.assertEqual(self.boards.scores, [])
        self.assertEqual(self.keeper.book.pending, [])
        self.sign_in()
        self.keeper.record("eye_runner", 90)
        self.assertEqual(self.boards.scores, [("eye_runner", 90)])
        self.assertEqual(self.keeper.book.pending, [])
        self.boards.fail = AuthError("We couldn’t reach the sign-in service.")
        self.keeper.record("blink_code_challenge", 300)
        self.assertEqual(len(self.keeper.book.pending), 1)  # kept for later
        self.assertIn("couldn’t reach", self.keeper.last_problem)
        self.boards.fail = None
        self.service.changed.emit(self.service.account)  # e.g. the next launch renews the sign-in
        self.assertEqual(self.boards.scores[-1], ("blink_code_challenge", 300))
        self.assertEqual(self.keeper.book.pending, [])

    def test_offline_and_other_accounts_wait(self):
        self.sign_in()
        self.service.offline = True
        self.keeper.record("eye_runner", 40)
        self.assertEqual(self.boards.scores, [])
        self.service.offline = False
        self.service.sign_out()
        self.service.sign_in("olek@example.com", "secret123", lambda ok, value: None)  # FakeClient: same id u1
        self.assertEqual(self.boards.scores, [("eye_runner", 40)])

    def test_leaderboard_view(self):
        opened = []
        view = LeaderboardView(self.keeper, open_account=lambda: opened.append(True))
        self.assertIn("No scores yet", view.status.text())
        self.keeper.record("blink_code_challenge", 250)
        self.assertEqual(view.grid.itemAtPosition(1, 2).widget().text(), "250")
        self.assertIn("Your top 1", view.status.text())
        view.set_scope("friends")
        self.assertIn("Log in to compare", view.status.text())
        self.assertFalse(view.account_button.isHidden())
        view.account_button.click()
        self.assertEqual(opened, [True])
        view.set_scope("everyone")  # works signed out
        self.assertEqual(self.boards.calls[-1], ("leaderboard", "blink_code_challenge", "everyone", None))
        self.assertEqual(view.grid.itemAtPosition(1, 1).widget().text(), "@nastia")
        self.assertIn("color", view.grid.itemAtPosition(2, 1).widget().styleSheet())  # your own row stands out
        self.assertEqual(view.grid.itemAtPosition(1, 1).widget().styleSheet(), "")
        self.sign_in()
        view.set_scope("friends")
        self.assertEqual(self.boards.calls[-1], ("leaderboard", "blink_code_challenge", "friends", "a1"))
        self.assertIn("No scores yet from you or your friends", view.status.text())
        self.boards.fail = NotSetUp()
        view.set_game("eye_runner")
        self.assertIn("aren’t switched on", view.status.text())

    def test_leaderboard_without_accounts(self):
        service = AccountService(None, self.store, synchronous=True)
        view = LeaderboardView(ScoreKeeper(service, book=temp_book()))
        view.set_scope("everyone")
        self.assertIn("aren’t set up in this copy", view.status.text())

    def test_friends_panel(self):
        panel = FriendsPanel(self.service)
        panel.load()
        self.assertEqual(self.boards.calls, [])  # signed out: nothing asked
        self.sign_in()
        panel.load()
        names = [panel.list_layout.itemAt(i).widget() for i in range(panel.list_layout.count())]
        self.assertEqual(len(names), 4)  # two headings, two people
        panel.name_field.setText("x")
        panel.add()
        self.assertIn("3 to 20", panel.status.text())
        panel.name_field.setText("@olek_2")
        panel.add()
        self.assertEqual(self.boards.calls[-2], ("request", "olek_2"))
        self.assertIn("Request sent to @olek_2", panel.status.text())
        self.assertEqual(panel.name_field.text(), "")
        panel.respond(Friend("u2", "nastia", "incoming"), True)
        self.assertIn("friends now", panel.status.text())
        self.assertEqual({f.status for f in panel.friends}, {"friend"})
        panel.remove(Friend("u3", "olek", "friend"))
        self.assertEqual([f.username for f in panel.friends], ["nastia"])
        self.assertIn("Removed @olek", panel.status.text())

    def test_friends_need_a_username(self):
        self.client.sign_in = lambda email, password: SignedIn(Account("u1", email, ""), "a1", "r1",
                                                               time.time() + 3600)
        self.sign_in()
        panel = FriendsPanel(self.service)
        panel.load()
        self.assertFalse(panel.add_button.isEnabled())
        self.assertIn("Choose a username", panel.status.text())


class GameHooksTest(unittest.TestCase):
    """The real games page inside the window: finished games reach the score book."""

    def setUp(self):
        from tests.test_main_window import MODEL_PATH
        if not MODEL_PATH.exists():
            self.skipTest("model file missing - run download_model.py")
        from ocusense.ui.main_window import MainWindow
        self.window = MainWindow()
        self.window.notify = lambda message, title: None
        self.page = self.window.games_page
        self.page.scores.book = temp_book()

    def tearDown(self):
        self.window.close()

    def test_blink_code_challenge_and_eye_game_runs_are_recorded(self):
        game = self.page.blink_code
        game.challenge.score, game.challenge.words_done, game.challenge.best_combo = 140, 2, 6
        game._challenge_over()
        entry = self.page.scores.book.entries("blink_code_challenge")[0]
        self.assertEqual((entry.score, entry.details), (140, {"words": 2, "best_combo": 6}))
        game.challenge.score = 90
        game._challenge_over()
        self.assertIn("#2 on this Mac", game.canvas.message)
        runner = self.page.eye_runner
        runner.game.state, runner.game.score = "play", 321.7
        runner.game.update = lambda dt, down=False: setattr(runner.game, "state", "over")  # the run ends now
        runner.tick()
        runner.tick()  # already over: not recorded twice
        self.assertEqual([e.score for e in self.page.scores.book.entries("eye_runner")], [321])
        self.page.leaderboard.set_scope("mac")
        self.page.leaderboard.set_game("blink_code_challenge")
        self.assertEqual(self.page.leaderboard.grid.itemAtPosition(1, 2).widget().text(), "140")

    def test_the_hub_shows_the_leaderboards(self):
        self.window.show_page("games")
        self.assertFalse(self.page.leaderboard.isHidden())
        self.page.leaderboard.set_scope("friends")
        self.assertIn("aren’t set up in this copy", self.page.leaderboard.status.text())  # tests: no accounts


if __name__ == "__main__":
    unittest.main()
