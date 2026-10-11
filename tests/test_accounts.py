"""Accounts: form checks, the Supabase calls (with the network faked), sign-in storage and the Account page."""

import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from ocusense.accounts import (
    Account, AccountStore, AuthClient, AuthError, FileTokens, KeychainTokens, NetworkError, SignedIn,
    SupabaseConfig, friendly_error, load_config, validate_confirm, validate_email, validate_password,
    validate_username,
)

CONFIG = SupabaseConfig("https://example.supabase.co", "sb_publishable_test")


def session_json(username="mira", refresh="r1"):
    return {"access_token": "a1", "refresh_token": refresh, "expires_in": 3600,
            "user": {"id": "u1", "email": "mira@example.com", "user_metadata": {"username": username}}}


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def http_error(status, body):
    return urllib.error.HTTPError("https://x", status, "error", {}, io.BytesIO(json.dumps(body).encode()))


class ChecksTest(unittest.TestCase):
    def test_form_checks_match_the_website(self):
        self.assertIsNone(validate_email("a@b.co"))
        self.assertIsNotNone(validate_email("nope"))
        self.assertIsNotNone(validate_password("short"))
        self.assertIsNone(validate_password("long enough"))
        self.assertIsNotNone(validate_password("x" * 73))
        self.assertIsNotNone(validate_confirm("a", "b"))
        self.assertIsNone(validate_username("blink_master7"))
        for bad in ("ab", "has space", "x" * 21, "émoji"):
            self.assertIsNotNone(validate_username(bad), bad)

    def test_friendly_errors(self):
        self.assertEqual(friendly_error("Invalid login credentials"), "Email or password is incorrect.")
        self.assertIn("confirm your email", friendly_error("Email not confirmed"))
        self.assertIn("already an account", friendly_error("user_already_exists User already registered"))
        self.assertIn("Something went wrong", friendly_error("???"))

    def test_config_from_the_environment_and_never_a_secret_key(self):
        with mock.patch.dict(os.environ, {"OCUSENSE_SUPABASE_URL": "https://p.supabase.co/",
                                          "OCUSENSE_SUPABASE_KEY": "sb_publishable_x"}, clear=True):
            self.assertEqual(load_config(), SupabaseConfig("https://p.supabase.co", "sb_publishable_x"))
        with mock.patch.dict(os.environ, {"OCUSENSE_SUPABASE_URL": "https://p.supabase.co",
                                          "OCUSENSE_SUPABASE_KEY": "sb_secret_x"}, clear=True):
            self.assertIsNone(load_config())
        with mock.patch.dict(os.environ, {"OCUSENSE_SUPABASE_URL": "http://p.supabase.co",
                                          "OCUSENSE_SUPABASE_KEY": "sb_publishable_x"}, clear=True):
            self.assertIsNone(load_config())  # https only
        with mock.patch.dict(os.environ, {"OCUSENSE_NO_ACCOUNTS": "1", "OCUSENSE_SUPABASE_URL": "https://p.co",
                                          "OCUSENSE_SUPABASE_KEY": "k"}):
            self.assertIsNone(load_config())


class ClientTest(unittest.TestCase):
    def setUp(self):
        self.client = AuthClient(CONFIG)
        self.requests = []
        self.replies = []

    def fake_urlopen(self, request, timeout, context):
        self.requests.append(request)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return FakeResponse(json.dumps(reply).encode())

    def run_with(self, *replies):
        self.replies = list(replies)
        return mock.patch("urllib.request.urlopen", self.fake_urlopen)

    def test_sign_in_sends_the_publishable_key_and_reads_the_session(self):
        with self.run_with(session_json()):
            signed = self.client.sign_in("mira@example.com", "secret123")
        request = self.requests[0]
        self.assertEqual(request.full_url, "https://example.supabase.co/auth/v1/token?grant_type=password")
        self.assertEqual(request.get_header("Apikey"), "sb_publishable_test")
        self.assertEqual(json.loads(request.data), {"email": "mira@example.com", "password": "secret123"})
        self.assertEqual(signed.account, Account("u1", "mira@example.com", "mira"))
        self.assertEqual(signed.refresh_token, "r1")
        self.assertGreater(signed.expires_at, time.time() + 3000)

    def test_wrong_password_and_offline(self):
        with self.run_with(http_error(400, {"error_code": "invalid_credentials", "msg": "Invalid login credentials"})):
            with self.assertRaisesRegex(AuthError, "incorrect"):
                self.client.sign_in("mira@example.com", "nope12345")
        with self.run_with(urllib.error.URLError("offline")):
            with self.assertRaises(NetworkError):
                self.client.sign_in("mira@example.com", "nope12345")

    def test_sign_up_with_username_and_email_confirmation(self):
        confirm_needed = {"id": "u1", "email": "mira@example.com", "identities": [{"id": "i"}]}
        with self.run_with(True, confirm_needed):
            self.assertIsNone(self.client.sign_up("mira@example.com", "secret123", "mira"))
        self.assertTrue(self.requests[0].full_url.endswith("/rest/v1/rpc/username_available"))
        body = json.loads(self.requests[1].data)
        self.assertEqual(body["data"], {"username": "mira"})

    def test_sign_up_refuses_a_taken_username_and_a_known_email(self):
        with self.run_with(False):
            with self.assertRaisesRegex(AuthError, "taken"):
                self.client.sign_up("mira@example.com", "secret123", "mira")
        with self.run_with(http_error(404, {}), {"id": "u1", "identities": []}):  # no leaderboard tables yet
            with self.assertRaisesRegex(AuthError, "already an account"):
                self.client.sign_up("mira@example.com", "secret123", "mira")

    def test_set_username_uses_the_access_token(self):
        user = {"id": "u1", "email": "mira@example.com", "user_metadata": {"username": "new_name"}}
        with self.run_with(True, user):
            account = self.client.set_username("a1", "new_name")
        self.assertEqual(self.requests[1].get_header("Authorization"), "Bearer a1")
        self.assertEqual(self.requests[1].get_method(), "PUT")
        self.assertEqual(account.username, "new_name")


class StoreTest(unittest.TestCase):
    def test_remembers_the_account_without_secrets(self):
        folder = Path(tempfile.mkdtemp())
        store = AccountStore(folder / "account.json", FileTokens(folder / "token"))
        self.assertIsNone(store.load())
        store.save(SignedIn(Account("u1", "mira@example.com", "mira"), "access", "refresh-xyz", time.time()))
        self.assertEqual(store.load(), Account("u1", "mira@example.com", "mira"))
        self.assertNotIn("refresh-xyz", (folder / "account.json").read_text())
        self.assertNotIn("access", (folder / "account.json").read_text().replace("\"", " ").split())
        self.assertEqual(store.tokens.load(), "refresh-xyz")
        store.clear()
        self.assertIsNone(store.load())
        self.assertIsNone(store.tokens.load())

    @unittest.skipUnless(sys.platform == "darwin" and Path("/usr/bin/security").exists(), "macOS Keychain only")
    def test_keychain_round_trip_in_a_throwaway_keychain(self):
        folder = tempfile.mkdtemp()
        keychain = os.path.join(folder, "ocusense-test.keychain-db")
        subprocess.run(["/usr/bin/security", "create-keychain", "-p", "test", keychain], check=True,
                       capture_output=True)
        try:
            subprocess.run(["/usr/bin/security", "unlock-keychain", "-p", "test", keychain], check=True,
                           capture_output=True)
            tokens = KeychainTokens(keychain)
            self.assertTrue(tokens.save("abc123-XY_z.9"))
            self.assertEqual(tokens.load(), "abc123-XY_z.9")
            self.assertFalse(tokens.save('bad"token'))  # never risks the command
            tokens.clear()
            self.assertIsNone(tokens.load())
        finally:
            subprocess.run(["/usr/bin/security", "delete-keychain", keychain], capture_output=True)


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from ocusense.ui.account_page import AccountPage  # noqa: E402
from ocusense.ui.account_service import AccountService  # noqa: E402

app = QApplication.instance() or QApplication([])


class FakeClient:
    def __init__(self):
        self.calls = []
        self.fail = None
        self.confirm_email = False

    def _call(self, name, *args):
        self.calls.append((name, *args))
        if self.fail:
            raise self.fail

    def sign_in(self, email, password):
        self._call("sign_in", email, password)
        return SignedIn(Account("u1", email, "mira"), "a1", "r1", time.time() + 3600)

    def sign_up(self, email, password, username):
        self._call("sign_up", email, password, username)
        return None if self.confirm_email else SignedIn(Account("u1", email, username), "a1", "r1", time.time() + 3600)

    def refresh(self, token):
        self._call("refresh", token)
        return SignedIn(Account("u1", "mira@example.com", "mira"), "a2", "r2", time.time() + 3600)

    def request_reset(self, email):
        self._call("reset", email)

    def set_username(self, access, username):
        self._call("set_username", access, username)
        return Account("u1", "mira@example.com", username)

    def sign_out(self, access):
        self._call("sign_out", access)


class ServiceAndPageTest(unittest.TestCase):
    def setUp(self):
        folder = Path(tempfile.mkdtemp())
        self.store = AccountStore(folder / "account.json", FileTokens(folder / "token"))
        self.client = FakeClient()

    def service(self):
        return AccountService(self.client, self.store, synchronous=True)

    def test_log_in_then_out(self):
        service = self.service()
        page = AccountPage(service)
        seen = []
        service.changed.connect(seen.append)
        page.fields["email"].setText("Mira@Example.com ")
        page.fields["password"].setText("secret123")
        page.submit()
        self.assertEqual(self.client.calls[0], ("sign_in", "mira@example.com", "secret123"))
        self.assertEqual(seen[-1].username, "mira")
        self.assertTrue(page.signed_out.isHidden())
        self.assertFalse(page.signed_in.isHidden())
        self.assertEqual(page.hello.text(), "Hi, @mira!")
        self.assertEqual(page.fields["password"].text(), "")  # the password isn't kept around
        self.assertEqual(self.store.tokens.load(), "r1")
        page.logout_button.click()
        self.assertIsNone(service.account)
        self.assertIsNone(self.store.load())
        self.assertIn(("sign_out", "a1"), self.client.calls)
        self.assertFalse(page.signed_out.isHidden())

    def test_create_account_checks_fields_then_waits_for_the_email(self):
        self.client.confirm_email = True
        page = AccountPage(self.service())
        page.set_mode("create")
        page.fields["email"].setText("mira@example.com")
        page.fields["password"].setText("secret123")
        page.fields["confirm"].setText("different1")
        page.submit()
        self.assertEqual(self.client.calls, [])  # nothing sent with mistakes in the form
        self.assertIn("Use 3 to 20", page.field_errors["username"].text())
        self.assertIn("don’t match", page.field_errors["confirm"].text())
        page.fields["username"].setText("mira")
        page.fields["confirm"].setText("secret123")
        page.submit()
        self.assertEqual(self.client.calls[0], ("sign_up", "mira@example.com", "secret123", "mira"))
        self.assertEqual(page.mode, "login")
        self.assertIn("confirmation link", page.status.text())
        self.assertIsNone(page.service.account)

    def test_wrong_password_is_shown(self):
        self.client.fail = AuthError("Email or password is incorrect.")
        page = AccountPage(self.service())
        page.fields["email"].setText("mira@example.com")
        page.fields["password"].setText("nope")
        page.submit()
        self.assertEqual(page.status.text(), "Email or password is incorrect.")
        self.assertTrue(page.login_button.isEnabled())

    def test_restore_renews_or_forgets_or_waits_offline(self):
        self.store.save(SignedIn(Account("u1", "mira@example.com", "mira"), "a0", "r0", 0))
        service = self.service()
        service.restore()
        self.assertEqual(self.client.calls[-1], ("refresh", "r0"))
        self.assertEqual(self.store.tokens.load(), "r2")  # the rotated token is saved
        self.client.fail = NetworkError("offline")
        service = self.service()
        service.restore()
        self.assertTrue(service.offline)
        self.assertIsNotNone(service.account)
        self.client.fail = AuthError("Invalid Refresh Token")
        service = self.service()
        service.restore()
        self.assertIsNone(service.account)
        self.assertIsNone(self.store.load())

    def test_change_username(self):
        service = self.service()
        page = AccountPage(service)
        service.sign_in("mira@example.com", "secret123", lambda ok, value: None)
        page.username_field.setText("x")
        page.save_username()
        self.assertIn("Use 3 to 20", page.username_status.text())
        page.username_field.setText("blink_queen")
        page.save_username()
        self.assertEqual(self.client.calls[-1], ("set_username", "a1", "blink_queen"))
        self.assertEqual(self.store.load().username, "blink_queen")
        self.assertEqual(page.hello.text(), "Hi, @blink_queen!")

    def test_forgot_password_needs_an_email(self):
        page = AccountPage(self.service())
        page.forgot()
        self.assertEqual(self.client.calls, [])
        page.fields["email"].setText("mira@example.com")
        page.forgot()
        self.assertEqual(self.client.calls[-1], ("reset", "mira@example.com"))
        self.assertIn("If an account exists", page.status.text())


if __name__ == "__main__":
    unittest.main()


class FakeAdvapi:
    """Stands in for Windows' advapi32 Credential Manager calls (so this runs on any system)."""

    def __init__(self):
        self.store = {}
        self.freed = 0

    def CredWriteW(self, credential_ref, flags):
        import ctypes
        c = credential_ref._obj
        self.store[c.TargetName] = (ctypes.string_at(c.CredentialBlob, c.CredentialBlobSize), c.Type, c.Persist)
        return 1

    def CredReadW(self, target, kind, flags, pointer_ref):
        import ctypes
        if target not in self.store:
            return 0
        blob = self.store[target][0]
        self._keep = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
        pointer = pointer_ref._obj
        credential = pointer._type_()
        credential.CredentialBlobSize = len(blob)
        credential.CredentialBlob = ctypes.cast(self._keep, ctypes.POINTER(ctypes.c_ubyte))
        self._credential = credential
        pointer.contents = credential
        return 1

    def CredFree(self, pointer):
        self.freed += 1

    def CredDeleteW(self, target, kind, flags):
        self.store.pop(target, None)
        return 1


class WindowsCredentialTest(unittest.TestCase):
    def test_round_trip_through_the_credential_manager(self):
        from ocusense.accounts import WindowsCredentialTokens
        api = FakeAdvapi()
        tokens = WindowsCredentialTokens(api)
        self.assertIsNone(tokens.load())
        self.assertTrue(tokens.save("refresh-ünïcode-123"))
        blob, kind, persist = api.store[tokens.TARGET]
        self.assertEqual((kind, persist), (1, 2))  # generic credential, kept on this computer
        self.assertEqual(tokens.load(), "refresh-ünïcode-123")
        self.assertEqual(api.freed, 1)  # Windows' copy is always released
        tokens.clear()
        self.assertIsNone(tokens.load())

    def test_windows_uses_it(self):
        from ocusense import accounts
        folder = Path(tempfile.mkdtemp())
        clean = {k: v for k, v in os.environ.items() if k != "OCUSENSE_ACCOUNT_FILE"}
        with mock.patch.dict(os.environ, clean | {"OCUSENSE_DATA_DIR": str(folder)}, clear=True), \
                mock.patch.object(accounts, "IS_MAC", False), mock.patch.object(accounts, "IS_WINDOWS", True), \
                mock.patch.object(accounts, "WindowsCredentialTokens", lambda: "windows store"):
            self.assertEqual(accounts.AccountStore().tokens, "windows store")
