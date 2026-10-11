"""Online game leaderboards and friends: the Supabase calls (tables and functions in supabase/schema.sql).

Uses the same project and the same AuthClient request as sign-in (ocusense/accounts.py):
    submit       POST /rest/v1/game_scores                     (signed in; a score can't be edited later)
    leaderboard  POST /rest/v1/rpc/game_leaderboard            scope "everyone" (also signed out) or "friends"
    friends      POST /rest/v1/rpc/my_friends | request_friend | respond_friend | remove_friend

Only usernames and game scores are shared — never eye measurements, recordings or calibration.
Pure Python and blocking: the window runs these calls on a background thread (AccountService).
"""

from dataclasses import dataclass

from .accounts import AuthClient, AuthError

SCOPES = ("friends", "everyone")
# What request_friend answers, as messages for the person.
FRIEND_REPLIES = {
    "requested": "Request sent to @{name}. You’ll see each other’s scores once they accept.",
    "accepted": "You and @{name} are friends now.",
    "already_friends": "You and @{name} are already friends.",
    "already_requested": "You’ve already asked @{name}. Waiting for them to accept.",
    "not_found": "No player is called @{name}. Check the spelling.",
    "self": "That’s you!",
    "too_many": "You have a lot of open requests. Wait for some answers first.",
}
MISSING_ON_SERVER = ("pgrst202", "pgrst205", "42p01", "42883", "could not find", "does not exist")


class NotSetUp(AuthError):
    """The Supabase project has accounts but not the leaderboard tables (supabase/schema.sql wasn't run)."""

    def __init__(self):
        super().__init__("Online leaderboards aren’t switched on for this OcuSense yet (see docs/accounts.md).")


@dataclass(frozen=True)
class Row:
    place: int
    username: str
    score: int
    created_at: str  # ISO time from the server
    is_me: bool = False


@dataclass(frozen=True)
class Friend:
    user_id: str
    username: str
    status: str  # "friend", "incoming" (they asked you) or "outgoing" (you asked them)


class LeaderboardClient:
    def __init__(self, auth: AuthClient):
        self.auth = auth

    def _call(self, method: str, path: str, body=None, token: str | None = None, headers=None):
        try:
            return self.auth._request(method, path, body, token=token, headers=headers)
        except AuthError as error:
            raw = (error.raw or "").lower()
            if error.status == 404 or any(code in raw for code in MISSING_ON_SERVER):
                raise NotSetUp() from error
            raise

    def submit(self, token: str, game: str, score: int, details: dict | None = None) -> None:
        self._call("POST", "/rest/v1/game_scores", {"game": game, "score": int(score), "details": details or {}},
                   token=token, headers={"Prefer": "return=minimal"})

    def leaderboard(self, game: str, scope: str = "everyone", token: str | None = None, limit: int = 50) -> list[Row]:
        if scope not in SCOPES:
            raise ValueError(f"Unknown scope {scope!r}")
        data = self._call("POST", "/rest/v1/rpc/game_leaderboard",
                          {"game_name": game, "scope": scope, "max_rows": limit}, token=token)
        rows = []
        for item in data if isinstance(data, list) else []:
            try:
                rows.append(Row(int(item["place"]), str(item["username"]), int(item["score"]),
                                str(item.get("created_at") or ""), bool(item.get("is_me"))))
            except (KeyError, TypeError, ValueError):
                continue
        return rows

    def friends(self, token: str) -> list[Friend]:
        data = self._call("POST", "/rest/v1/rpc/my_friends", {}, token=token)
        result = []
        for item in data if isinstance(data, list) else []:
            if isinstance(item, dict) and item.get("status") in ("friend", "incoming", "outgoing"):
                result.append(Friend(str(item.get("user_id", "")), str(item.get("username") or ""), item["status"]))
        return result

    def request_friend(self, token: str, username: str) -> str:
        """One of FRIEND_REPLIES' keys."""
        reply = self._call("POST", "/rest/v1/rpc/request_friend", {"name": username}, token=token)
        return reply if reply in FRIEND_REPLIES else "requested"

    def respond_friend(self, token: str, user_id: str, accept: bool) -> str:
        return str(self._call("POST", "/rest/v1/rpc/respond_friend", {"other": user_id, "accept": bool(accept)},
                              token=token))

    def remove_friend(self, token: str, user_id: str) -> None:
        self._call("POST", "/rest/v1/rpc/remove_friend", {"other": user_id}, token=token)
