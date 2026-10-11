"""packaging/connect_supabase.py: refuses secret keys, and asks a (fake, local) Supabase project what's missing."""

import base64
import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "packaging"))
import connect_supabase as connect  # noqa: E402

STATE = {"schema": False, "autoconfirm": False}


class FakeProject(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.headers.get("apikey") != "sb_publishable_ok":
            self.reply(401, {"message": "Invalid API key"})
            return
        self.reply(200, {"external": {"email": True}, "disable_signup": False,
                         "mailer_autoconfirm": STATE["autoconfirm"]})

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if not STATE["schema"]:
            self.reply(404, {"code": "PGRST202"})
            return
        self.reply(200, [] if "leaderboard" in self.path else True)


def jwt(role):
    return "h." + base64.urlsafe_b64encode(json.dumps({"role": role}).encode()).decode().rstrip("=") + ".s"


class ConnectTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), FakeProject)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_values(self):
        good = "https://qwertyuiopasdfgh.supabase.co"
        self.assertEqual(connect.check_values(good, "sb_publishable_x"), [])
        self.assertEqual(connect.check_values(good, jwt("anon")), [])
        for secret in ("sb_secret_x", jwt("service_role")):
            self.assertIn("SECRET", connect.check_values(good, secret)[0])
        self.assertIn("example values", connect.check_values("https://YOUR-PROJECT.supabase.co", "sb_publishable_…")[0])
        self.assertIn("example values", connect.check_values("https://abcdefghijklmnop.supabase.co",
                                                             "sb_publishable_AbC123...")[0])
        self.assertIn("unexpected character", connect.check_values(good, "sb_publishable_abc“")[0])
        self.assertTrue(connect.check_values("http://p.supabase.co", "k"))
        self.assertTrue(connect.check_values("https://p.supabase.co/rest/v1", "k"))

    def test_asks_the_project_what_is_missing(self):
        STATE.update(schema=False, autoconfirm=False)
        problems, _ = connect.check_project(self.url, "wrong")
        self.assertIn("refused that key", problems[0])
        problems, notes = connect.check_project(self.url, "sb_publishable_ok")
        self.assertIn("schema.sql", problems[0])
        self.assertIn("confirmation email", notes[0])
        STATE.update(schema=True, autoconfirm=True)
        problems, notes = connect.check_project(self.url, "sb_publishable_ok")
        self.assertEqual(problems, [])
        self.assertIn("straight away", notes[0])
        problems, _ = connect.check_project("http://127.0.0.1:1", "k")
        self.assertIn("Couldn't reach", problems[0])


if __name__ == "__main__":
    unittest.main()
