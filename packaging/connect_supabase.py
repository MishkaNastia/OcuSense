"""Connect OcuSense to a Supabase project, so log-in works for everyone who gets the app.

    .venv/bin/python packaging/connect_supabase.py https://YOUR-PROJECT.supabase.co sb_publishable_…
    .venv/bin/python packaging/connect_supabase.py URL KEY --build     # also rebuild OcuSense.app

1. Checks the values: an https project URL and the PUBLISHABLE (anon) key — a secret /
   service-role key is refused, because everything in the app can be read by its users.
2. Asks the project whether sign-in works and whether supabase/schema.sql has been run
   (usernames, scores, friends, leaderboards), and whether new accounts need an email
   confirmation.
3. Saves ocusense/supabase.json (bundled into the app by packaging/OcuSense.spec) and, if
   there's none yet, website/.env.local, so the app and the website share one project.
   Both files are git-ignored.
4. With --build: runs packaging/build_mac.sh, so the new OcuSense.app has accounts switched on.

See docs/accounts.md for creating the project.
"""

import argparse
import base64
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ocusense.accounts import _ssl_context  # noqa: E402

APP_CONFIG = ROOT / "ocusense" / "supabase.json"
WEBSITE_ENV = ROOT / "website" / ".env.local"


def jwt_role(key: str) -> str:
    """The role inside a legacy JWT key ("anon" or "service_role"), or "" for other keys."""
    parts = key.split(".")
    if len(parts) != 3:
        return ""
    try:
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        return str(json.loads(base64.urlsafe_b64decode(payload)).get("role", ""))
    except (ValueError, AttributeError):
        return ""


def check_values(url: str, key: str) -> list[str]:
    problems = []
    if not url.startswith("https://") or "/" in url[len("https://"):] or " " in url:
        problems.append("The URL should look like https://abcdefghijklmnop.supabase.co (no path at the end).")
    examples = ("YOUR-PROJECT", "ABCDEFGHIJKLMNOP")  # the placeholders used in the docs
    if any(e in url.upper() for e in examples) or "…" in key or "..." in key or key == "sb_publishable_":
        problems.append("Those are the example values. Replace them with your project's own URL and publishable "
                        "key (Supabase › Project Settings › API Keys).")
        return problems
    if not key.isascii() or not url.isascii():
        problems.append("The URL or key contains an unexpected character. Copy them again with the copy buttons "
                        "in Supabase › Project Settings › API Keys.")
        return problems
    if key.startswith("sb_secret_") or jwt_role(key) == "service_role":
        problems.append("That's the SECRET key. Use the publishable key (sb_publishable_…) or the legacy anon key.")
    elif not key or " " in key:
        problems.append("The key is empty or has spaces in it.")
    return problems


def ask(url: str, key: str, method: str, path: str, body=None):
    """(HTTP status, parsed JSON or text) — never raises for HTTP errors."""
    request = urllib.request.Request(url + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"apikey": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=15, context=_ssl_context()) as response:
            text = response.read().decode()
            status = response.status
    except urllib.error.HTTPError as error:
        text, status = error.read().decode(), error.code
        error.close()
    try:
        return status, json.loads(text or "null")
    except ValueError:
        return status, text


def check_project(url: str, key: str) -> tuple[list[str], list[str]]:
    """(problems that stop log-in, notes) from asking the project."""
    problems, notes = [], []
    try:
        status, settings = ask(url, key, "GET", "/auth/v1/settings")
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return [f"Couldn't reach {url}: {error}. Check the URL and your connection."], notes
    if status in (401, 403):
        return ["The project refused that key. Copy the publishable key again (Project Settings › API Keys)."], notes
    if status != 200 or not isinstance(settings, dict):
        return [f"{url} didn't answer like a Supabase project (HTTP {status})."], notes
    if not (settings.get("external") or {}).get("email", True):
        problems.append("Email sign-in is switched off: Authentication › Sign In / Providers › Email › enable it.")
    if settings.get("disable_signup"):
        problems.append("New sign-ups are switched off: Authentication › Sign In / Providers › allow new users.")
    if settings.get("mailer_autoconfirm"):
        notes.append("New accounts work straight away (email confirmation is off).")
    else:
        notes.append("New accounts must open the confirmation email first. Its link goes to the Site URL in "
                     "Authentication › URL Configuration — set that to the website's address, or switch "
                     "'Confirm email' off (Authentication › Sign In / Providers › Email) so accounts work at once.")
    status, _ = ask(url, key, "POST", "/rest/v1/rpc/game_leaderboard", {"game_name": "eye_runner"})
    if status == 404:
        problems.append("The database isn't set up yet: Supabase › SQL Editor › paste supabase/schema.sql › Run, "
                        "then run this script again.")
    elif status != 200:
        problems.append(f"The leaderboard function answered HTTP {status}: run supabase/schema.sql again.")
    else:
        status, answer = ask(url, key, "POST", "/rest/v1/rpc/username_available", {"name": "ocusense_check"})
        if status != 200 or not isinstance(answer, bool):
            problems.append("Usernames aren't set up: run supabase/schema.sql again.")
        else:
            notes.append("The database is set up: usernames, scores, friends and leaderboards.")
    return problems, notes


def save(url: str, key: str) -> list[str]:
    APP_CONFIG.write_text(json.dumps({"url": url, "publishable_key": key}, indent=2) + "\n")
    saved = [str(APP_CONFIG.relative_to(ROOT))]
    if not WEBSITE_ENV.exists() and WEBSITE_ENV.parent.exists():
        WEBSITE_ENV.write_text(f"NEXT_PUBLIC_SUPABASE_URL={url}\nNEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY={key}\n"
                               "NEXT_PUBLIC_SITE_URL=\n")
        saved.append(str(WEBSITE_ENV.relative_to(ROOT)))
    return saved


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("url", help="Project URL, e.g. https://abcdefghijklmnop.supabase.co")
    parser.add_argument("key", help="The publishable key (sb_publishable_…) or legacy anon key")
    parser.add_argument("--build", action="store_true", help="rebuild OcuSense.app afterwards")
    parser.add_argument("--skip-check", action="store_true", help="save without asking the project (offline)")
    args = parser.parse_args(argv)
    url, key = args.url.strip().rstrip("/"), args.key.strip()

    problems = check_values(url, key)
    notes = []
    if not problems and not args.skip_check:
        problems, notes = check_project(url, key)
    for note in notes:
        print("·", note)
    if problems:
        for problem in problems:
            print("✗", problem)
        print("Nothing was saved.")
        return 1
    for path in save(url, key):
        print("✓ saved", path)
    if args.build:
        return subprocess.run([str(ROOT / "packaging" / "build_mac.sh")], cwd=ROOT).returncode
    print("Next: ./packaging/build_mac.sh  (the new OcuSense.app has accounts switched on for everyone)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
