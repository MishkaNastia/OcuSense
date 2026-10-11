"""OcuSense accounts in the Mac app: the same Supabase sign-in as the website.

One account works on the website and in the app. It is optional — monitoring,
Statistics and the games all work without one — and it is what the online game
leaderboards and friends hang on (ocusense/leaderboards.py, supabase/schema.sql,
docs/accounts.md).

Where things are kept:
    the Supabase project      OCUSENSE_SUPABASE_URL + OCUSENSE_SUPABASE_KEY, or
                              <data folder>/supabase.json (see ocusense/system.py), or
                              ocusense/supabase.json (bundled into the app)
    who is signed in          <data folder>/account.json
                              (user id, email and username — nothing secret)
    the sign-in token         the macOS Keychain ("OcuSense" / refresh-token), or the Windows
                              Credential Manager ("app.ocusense.OcuSense/refresh-token")

Only the public project URL and the publishable (anon) key are used, as on the
website. Passwords are sent to Supabase over HTTPS and never stored on this Mac.
OCUSENSE_ACCOUNT_FILE overrides account.json and then keeps the token in a file
next to it instead of the Keychain, and OCUSENSE_NO_ACCOUNTS=1 switches accounts
off (both for tests only).

Pure Python and blocking: the window runs these calls on a background thread.
"""

import json
import os
import re
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

from ocusense.system import IS_MAC, IS_WINDOWS, user_data_dir
KEYCHAIN_SERVICE = "app.ocusense.OcuSense"
KEYCHAIN_ACCOUNT = "refresh-token"
TIMEOUT = 15  # seconds per request

# The same rules as the website's sign-up form (website/src/lib/auth/validation.ts).
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 72  # bcrypt limit used by Supabase Auth
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{3,20}$")  # what leaderboards will show


class AuthError(Exception):
    """A message that can be shown to the person as it is.

    status and raw keep what the server said (HTTP status, error code and message), so
    callers such as ocusense/leaderboards.py can tell specific failures apart.
    """

    def __init__(self, message: str = "", status: int | None = None, raw: str = ""):
        super().__init__(message)
        self.status = status
        self.raw = raw


class NetworkError(AuthError):
    """Supabase couldn't be reached (offline, timed out): nothing about the account changed."""


# ------------------------------------------------------------------ configuration
@dataclass(frozen=True)
class SupabaseConfig:
    url: str
    key: str


def _bundled_config_path() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "ocusense" / "supabase.json"


def load_config() -> SupabaseConfig | None:
    """The Supabase project to sign in with, or None when this copy isn't set up for accounts.

    OCUSENSE_NO_ACCOUNTS=1 switches accounts off (the tests never reach a real project).
    """
    if os.environ.get("OCUSENSE_NO_ACCOUNTS"):
        return None
    url, key = os.environ.get("OCUSENSE_SUPABASE_URL", ""), os.environ.get("OCUSENSE_SUPABASE_KEY", "")
    if not (url and key):
        for path in (user_data_dir() / "supabase.json", _bundled_config_path()):
            try:
                values = json.loads(path.read_text())
            except (OSError, ValueError):
                continue
            if isinstance(values, dict):
                url, key = str(values.get("url", "")), str(values.get("publishable_key", ""))
                break
    url, key = url.strip().rstrip("/"), key.strip()
    if not key or not re.match(r"^https://[^\s/]+$", url):
        return None
    if key.startswith("sb_secret_") or '"service_role"' in key:
        return None  # never ship a secret key in an app
    return SupabaseConfig(url, key)


# ------------------------------------------------------------------ form checks
def validate_email(email: str) -> str | None:
    if not email:
        return "Enter your email address."
    if len(email) > 254 or not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email):
        return "Enter a valid email address, like name@example.com."
    return None


def validate_password(password: str) -> str | None:
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Use at least {MIN_PASSWORD_LENGTH} characters."
    if len(password) > MAX_PASSWORD_LENGTH:
        return f"Use at most {MAX_PASSWORD_LENGTH} characters."
    return None


def validate_confirm(password: str, confirm: str) -> str | None:
    return None if password == confirm else "The two passwords don’t match."


def validate_username(username: str) -> str | None:
    if not USERNAME_PATTERN.match(username):
        return "Use 3 to 20 letters, numbers or underscores. It’s shown on leaderboards."
    return None


def friendly_error(message: str) -> str:
    """Friendly wording for errors from Supabase (the same as the website's)."""
    m = message.lower()
    if "invalid login credentials" in m:
        return "Email or password is incorrect."
    if "email not confirmed" in m:
        return "Please confirm your email first. Check your inbox for the link we sent."
    if "already registered" in m or "already been registered" in m or "user_already_exists" in m:
        return "There’s already an account with that email. Log in instead."
    if "rate limit" in m or "too many" in m:
        return "Too many attempts. Please wait a few minutes and try again."
    if "password" in m and "weak" in m:
        return "That password is too easy to guess. Try a longer one."
    if "network" in m or "fetch" in m or "timed out" in m:
        return "We couldn’t reach the login service. Check your connection and try again."
    return "Something went wrong. Please try again."


# ------------------------------------------------------------------ the HTTP calls
def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi  # the packaged app has no system certificate bundle of its own
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


@dataclass
class Account:
    user_id: str
    email: str
    username: str = ""  # empty for accounts made on the website before usernames existed


@dataclass
class SignedIn:
    account: Account
    access_token: str
    refresh_token: str
    expires_at: float  # time.time()


class AuthClient:
    """Supabase Auth over its REST API (the same calls supabase-js makes)."""

    def __init__(self, config: SupabaseConfig):
        self.config = config
        self._context = _ssl_context()

    def _request(self, method: str, path: str, body: dict | None = None, token: str | None = None,
                 headers: dict | None = None):
        headers = {"apikey": self.config.key, "Content-Type": "application/json", **(headers or {})}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.config.url + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT, context=self._context) as response:
                text = response.read().decode() or "null"
                return json.loads(text)
        except urllib.error.HTTPError as error:
            try:
                details = json.loads(error.read().decode() or "{}")
            except ValueError:
                details = {}
            finally:
                error.close()
            message = ""
            if isinstance(details, dict):
                message = " ".join(str(details.get(k, "")) for k in ("error_code", "code", "msg", "message",
                                                                       "error_description", "error"))
            raise AuthError(friendly_error(message), error.code, message) from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise NetworkError(friendly_error("network")) from error
        except ValueError as error:
            raise AuthError(friendly_error("")) from error

    @staticmethod
    def _signed_in(data: dict) -> SignedIn:
        user = data.get("user") or {}
        meta = user.get("user_metadata") or {}
        account = Account(str(user.get("id", "")), str(user.get("email", "")), str(meta.get("username", "") or ""))
        return SignedIn(account, data["access_token"], data["refresh_token"],
                        time.time() + float(data.get("expires_in", 3600)))

    def username_available(self, username: str, access_token: str | None = None) -> bool | None:
        """None when the leaderboard tables aren't set up yet (supabase/schema.sql), so it can't tell.

        Signed in (access_token), your own current username counts as available.
        """
        try:
            result = self._request("POST", "/rest/v1/rpc/username_available", {"name": username},
                                   token=access_token)
        except AuthError:
            return None
        return result if isinstance(result, bool) else None

    def sign_up(self, email: str, password: str, username: str) -> SignedIn | None:
        """None means a confirmation email was sent (the account works after the link is opened)."""
        if self.username_available(username) is False:
            raise AuthError("That username is taken. Try another one.")
        data = self._request("POST", "/auth/v1/signup",
                             {"email": email, "password": password, "data": {"username": username}})
        if isinstance(data, dict) and data.get("access_token"):
            return self._signed_in(data)
        identities = data.get("identities") if isinstance(data, dict) else None
        if identities == []:  # Supabase's sign that the email is already registered (without saying so)
            raise AuthError(friendly_error("already registered"))
        return None

    def sign_in(self, email: str, password: str) -> SignedIn:
        return self._signed_in(self._request("POST", "/auth/v1/token?grant_type=password",
                                             {"email": email, "password": password}))

    def refresh(self, refresh_token: str) -> SignedIn:
        return self._signed_in(self._request("POST", "/auth/v1/token?grant_type=refresh_token",
                                             {"refresh_token": refresh_token}))

    def request_reset(self, email: str) -> None:
        self._request("POST", "/auth/v1/recover", {"email": email})

    def set_username(self, access_token: str, username: str) -> Account:
        if self.username_available(username, access_token) is False:
            raise AuthError("That username is taken. Try another one.")
        user = self._request("PUT", "/auth/v1/user", {"data": {"username": username}}, token=access_token)
        meta = user.get("user_metadata") or {}
        return Account(str(user.get("id", "")), str(user.get("email", "")), str(meta.get("username", "") or ""))

    def sign_out(self, access_token: str) -> None:
        self._request("POST", "/auth/v1/logout", token=access_token)


# ------------------------------------------------------------------ remembering who is signed in
class KeychainTokens:
    """The refresh token in the macOS Keychain, through /usr/bin/security.

    The token is passed on standard input (security -i), never on the command line,
    so other processes can't read it from the process list.
    """

    def __init__(self, keychain: str | None = None):
        self.keychain = keychain  # a specific keychain file (tests); None = the login keychain

    def _target(self) -> list[str]:
        return [self.keychain] if self.keychain else []

    def save(self, token: str) -> bool:
        if not re.match(r"^[A-Za-z0-9._\-]+$", token):
            return False  # unexpected characters: don't risk the command; stay signed in only for now
        target = f' "{self.keychain}"' if self.keychain else ""
        command = f'add-generic-password -U -s "{KEYCHAIN_SERVICE}" -a "{KEYCHAIN_ACCOUNT}" -w "{token}"{target}\n'
        try:
            done = subprocess.run(["/usr/bin/security", "-i"], input=command, text=True, capture_output=True,
                                  timeout=10)
        except (OSError, subprocess.SubprocessError):
            return False
        return done.returncode == 0 and "error" not in (done.stdout + done.stderr).lower()

    def load(self) -> str | None:
        try:
            done = subprocess.run(["/usr/bin/security", "find-generic-password", "-s", KEYCHAIN_SERVICE,
                                   "-a", KEYCHAIN_ACCOUNT, "-w", *self._target()],
                                  capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            return None
        token = done.stdout.strip()
        return token if done.returncode == 0 and token else None

    def clear(self) -> None:
        try:
            subprocess.run(["/usr/bin/security", "delete-generic-password", "-s", KEYCHAIN_SERVICE,
                            "-a", KEYCHAIN_ACCOUNT, *self._target()], capture_output=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            pass


class FileTokens:
    """Test stand-in for the Keychain: a private file."""

    def __init__(self, path: Path):
        self.path = path

    def save(self, token: str) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(token)
        self.path.chmod(0o600)
        return True

    def load(self) -> str | None:
        try:
            return self.path.read_text().strip() or None
        except OSError:
            return None

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)


class WindowsCredentialTokens:
    """The refresh token in the Windows Credential Manager (generic credential "OcuSense").

    The Windows counterpart of the macOS Keychain: Windows keeps it encrypted for this
    user account. `api` is advapi32 (replaceable in tests).
    """

    TARGET = "app.ocusense.OcuSense/refresh-token"
    CRED_TYPE_GENERIC, CRED_PERSIST_LOCAL_MACHINE = 1, 2

    def __init__(self, api=None):
        import ctypes
        from ctypes import wintypes

        class FILETIME(ctypes.Structure):
            _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

        class CREDENTIAL(ctypes.Structure):
            _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR),
                        ("Comment", wintypes.LPWSTR), ("LastWritten", FILETIME),
                        ("CredentialBlobSize", wintypes.DWORD), ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                        ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD),
                        ("Attributes", ctypes.c_void_p), ("TargetAlias", wintypes.LPWSTR),
                        ("UserName", wintypes.LPWSTR)]

        self.ctypes, self.CREDENTIAL = ctypes, CREDENTIAL
        self.api = api if api is not None else ctypes.windll.advapi32

    def save(self, token: str) -> bool:
        ctypes = self.ctypes
        blob = token.encode("utf-8")
        buffer = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
        credential = self.CREDENTIAL()
        credential.Type = self.CRED_TYPE_GENERIC
        credential.TargetName = self.TARGET
        credential.UserName = "OcuSense"
        credential.CredentialBlobSize = len(blob)
        credential.CredentialBlob = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
        credential.Persist = self.CRED_PERSIST_LOCAL_MACHINE
        try:
            return bool(self.api.CredWriteW(ctypes.byref(credential), 0))
        except Exception:
            return False

    def load(self) -> str | None:
        ctypes = self.ctypes
        found = ctypes.POINTER(self.CREDENTIAL)()
        try:
            if not self.api.CredReadW(self.TARGET, self.CRED_TYPE_GENERIC, 0, ctypes.byref(found)):
                return None
            size = found.contents.CredentialBlobSize
            token = ctypes.string_at(found.contents.CredentialBlob, size).decode("utf-8")
        except Exception:
            return None
        finally:
            if found:
                try:
                    self.api.CredFree(found)
                except Exception:
                    pass
        return token or None

    def clear(self) -> None:
        try:
            self.api.CredDeleteW(self.TARGET, self.CRED_TYPE_GENERIC, 0)
        except Exception:
            pass


class MemoryTokens:
    """Keeps the sign-in token only while OcuSense runs (systems without a secure store)."""

    def __init__(self):
        self.token: str | None = None

    def save(self, token: str) -> bool:
        self.token = token
        return True

    def load(self) -> str | None:
        return self.token

    def clear(self) -> None:
        self.token = None


class AccountStore:
    """Who is signed in on this Mac: account.json (no secrets) plus the token store."""

    def __init__(self, path: Path | None = None, tokens=None):
        override = os.environ.get("OCUSENSE_ACCOUNT_FILE")
        self.path = path or (Path(override) if override else user_data_dir() / "account.json")
        if tokens is None:
            if override:
                tokens = FileTokens(self.path.with_suffix(".token"))
            elif IS_MAC:
                tokens = KeychainTokens()
            elif IS_WINDOWS:
                try:
                    tokens = WindowsCredentialTokens()
                except Exception:  # no Credential Manager: stay signed in until OcuSense quits
                    tokens = MemoryTokens()
            else:
                tokens = MemoryTokens()
        self.tokens = tokens

    def load(self) -> Account | None:
        try:
            values = json.loads(self.path.read_text())
            account = Account(str(values["user_id"]), str(values["email"]), str(values.get("username", "")))
        except (OSError, ValueError, KeyError, TypeError):
            return None
        return account if account.user_id and account.email else None

    def save(self, signed_in: SignedIn) -> None:
        self.save_account(signed_in.account)
        self.tokens.save(signed_in.refresh_token)

    def save_account(self, account: Account) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(account), indent=2))
        temporary.replace(self.path)

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)
        self.tokens.clear()
