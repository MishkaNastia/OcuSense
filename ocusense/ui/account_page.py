"""Account: log in or create an OcuSense account (the same account as on the website).

Optional — monitoring, Statistics and the games all work without one. An account
gives you a username on the online game leaderboards and lets you add friends
(friends_panel.py). Eye data never leaves this Mac; an account holds only an email
address, a username, game scores and friends.

Three views: not set up (this copy has no Supabase project, see docs/accounts.md),
signed out (Log in / Create account), and signed in.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from ocusense.accounts import (
    Account, validate_confirm, validate_email, validate_password, validate_username,
)
from ocusense.system import COMPUTER

from . import theme
from .account_service import AccountService
from .friends_panel import FriendsPanel
from .widgets.common import button, label
from .widgets.page import Page, paragraph
from .widgets.segmented import Segmented

MODES = (("login", "Log in"), ("create", "Create account"))


def _field(placeholder: str, accessible: str, password: bool = False) -> QLineEdit:
    field = QLineEdit()
    field.setPlaceholderText(placeholder)
    field.setAccessibleName(accessible)
    field.setMaximumWidth(420)
    if password:
        field.setEchoMode(QLineEdit.EchoMode.Password)
    return field


def _message(role: str = "error"):
    widget = paragraph("", 13)
    widget.setProperty("role", role)
    widget.setVisible(False)
    return widget


def _show(widget, text: str, role: str = "error") -> None:
    widget.setText(text)
    widget.setProperty("role", role)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.setVisible(bool(text))


class AccountPage(Page):
    def __init__(self, service: AccountService | None = None, parent=None):
        super().__init__("Account", "Your account")
        self.service = service or AccountService()
        self.mode = "login"

        # ---- not set up
        self.unconfigured = QWidget()
        box = QVBoxLayout(self.unconfigured)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(12)
        box.addWidget(label("Accounts aren’t set up in this copy of OcuSense.",
                            font=theme.ui_font(22, QFont.Weight.Bold), wrap=True))
        box.addWidget(paragraph(
            f"You don’t need an account: calibration, monitoring, Statistics and the games all work on this {COMPUTER} "
            "without one, and nothing is sent anywhere."))
        box.addWidget(paragraph(
            "For developers: connect the app to the website’s Supabase project as described in docs/accounts.md.",
            13, secondary=True))

        # ---- signed out
        self.signed_out = QWidget()
        box = QVBoxLayout(self.signed_out)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(10)
        box.addWidget(paragraph(
            "An account is optional. It puts your game scores on the online leaderboards and lets you compare "
            "them with friends, and the same account works on the OcuSense website. Your eye data never leaves "
            f"this {COMPUTER}."))
        box.addSpacing(4)
        self.mode_switch = Segmented(MODES, self.mode, "Log in or create an account")
        self.mode_switch.changed.connect(self.set_mode)
        box.addWidget(self.mode_switch, 0, Qt.AlignmentFlag.AlignLeft)
        box.addSpacing(4)
        self.fields = {
            "username": _field("Username (shown on leaderboards)", "Username"),
            "email": _field("Email", "Email"),
            "password": _field("Password (at least 8 characters)", "Password", password=True),
            "confirm": _field("Repeat the password", "Repeat the password", password=True),
        }
        self.field_errors = {}
        for name, field in self.fields.items():
            box.addWidget(field)
            self.field_errors[name] = _message()
            box.addWidget(self.field_errors[name])
            field.returnPressed.connect(self.submit)
        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.login_button = button("Log in", "primary")
        self.login_button.clicked.connect(self.submit)
        self.forgot_button = button("Forgot password?", "quiet")
        self.forgot_button.clicked.connect(self.forgot)
        actions.addWidget(self.login_button)
        actions.addWidget(self.forgot_button)
        actions.addStretch(1)
        box.addSpacing(4)
        box.addLayout(actions)
        self.status = _message()
        box.addWidget(self.status)

        # ---- signed in
        self.signed_in = QWidget()
        box = QVBoxLayout(self.signed_in)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(10)
        self.hello = label("", font=theme.ui_font(26, QFont.Weight.Bold), wrap=True)
        box.addWidget(self.hello)
        self.email_label = label("", "secondary", theme.ui_font(15), wrap=True)
        box.addWidget(self.email_label)
        self.offline_note = _message("secondary")
        box.addWidget(self.offline_note)
        self.section("Leaderboard name", box)
        box.addWidget(paragraph("Shown next to your scores on the game leaderboards. 3 to 20 letters, numbers or "
                                "underscores.", 13, secondary=True))
        row = QHBoxLayout()
        row.setSpacing(10)
        self.username_field = _field("Username", "Username")
        self.username_field.setMinimumWidth(280)
        self.username_field.returnPressed.connect(self.save_username)
        self.save_username_button = button("Save", "secondary")
        self.save_username_button.clicked.connect(self.save_username)
        row.addWidget(self.username_field)
        row.addWidget(self.save_username_button)
        row.addStretch(1)
        box.addLayout(row)
        self.username_status = _message()
        box.addWidget(self.username_status)
        self.section("Friends", box)
        self.friends = FriendsPanel(self.service)
        box.addWidget(self.friends)
        box.addWidget(paragraph(
            "The leaderboards are in Games. Only your username and game scores are shared, never eye "
            "measurements, recordings or calibration.", 13, secondary=True))
        box.addSpacing(8)
        self.logout_button = button("Log out", "secondary")
        self.logout_button.clicked.connect(self.service.sign_out)
        box.addWidget(self.logout_button, 0, Qt.AlignmentFlag.AlignLeft)

        for panel in (self.unconfigured, self.signed_out, self.signed_in):
            self.body.addWidget(panel)
        self.finish()
        self.service.changed.connect(lambda _account: (self.refresh(), self.friends.load()))
        self.set_mode(self.mode)
        self.refresh()

    # ------------------------------------------------------------ display
    def refresh(self) -> None:
        account = self.service.account
        configured = self.service.configured
        self.unconfigured.setVisible(not configured)
        self.signed_out.setVisible(configured and account is None)
        self.signed_in.setVisible(configured and account is not None)
        if not configured:
            self.set_tag("Not set up", "This copy of OcuSense isn’t connected to OcuSense accounts.")
        elif account is None:
            self.set_tag("")
        else:
            self._show_account(account)
        self._busy(self.service.busy)
        self.fit_height()

    def _show_account(self, account: Account) -> None:
        name = f"@{account.username}" if account.username else "there"
        self.hello.setText(f"Hi, {name}!")
        self.email_label.setText(f"Signed in as {account.email}")
        if not self.username_field.hasFocus():
            self.username_field.setText(account.username)
        _show(self.offline_note, f"Offline for now. You’re still signed in on this {COMPUTER}, and OcuSense reconnects next time."
              if self.service.offline else "", "secondary")
        self.set_tag("Offline" if self.service.offline else "Signed in")
        if not account.username:
            _show(self.username_status, "Choose a username so you can appear on leaderboards.", "secondary")

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self.mode_switch.set_current(mode)
        creating = mode == "create"
        for name in ("username", "confirm"):
            self.fields[name].setVisible(creating)
            self.field_errors[name].setVisible(False)
        self.forgot_button.setVisible(not creating)
        self.login_button.setText("Create account" if creating else "Log in")
        _show(self.status, "")
        self.fit_height()

    def _busy(self, busy: bool, text: str = "") -> None:
        for widget in (*self.fields.values(), self.mode_switch, self.forgot_button, self.username_field,
                       self.save_username_button, self.logout_button):
            widget.setEnabled(not busy)
        self.login_button.setEnabled(not busy)
        if busy and text:
            self.login_button.setText(text)
        elif not busy:
            self.login_button.setText("Create account" if self.mode == "create" else "Log in")

    # ------------------------------------------------------------ actions
    def _values(self) -> dict[str, str]:
        values = {name: field.text() for name, field in self.fields.items()}
        values["email"] = values["email"].strip().lower()
        values["username"] = values["username"].strip()
        return values

    def submit(self) -> None:
        if self.service.busy or not self.service.configured:
            return
        v = self._values()
        creating = self.mode == "create"
        errors = {"email": validate_email(v["email"])}
        if creating:
            errors.update(username=validate_username(v["username"]), password=validate_password(v["password"]),
                          confirm=validate_confirm(v["password"], v["confirm"]))
        else:
            errors["password"] = None if v["password"] else "Enter your password."
        for name, widget in self.field_errors.items():
            _show(widget, errors.get(name) or "")
        if any(errors.values()):
            _show(self.status, "Please check the highlighted fields.")
            first = next(name for name in self.fields if errors.get(name))
            self.fields[first].setFocus()
            return
        _show(self.status, "")
        if creating:
            self._busy(True, "Creating account…")
            self.service.sign_up(v["email"], v["password"], v["username"], self._signed_up)
        else:
            self._busy(True, "Logging in…")
            self.service.sign_in(v["email"], v["password"], self._logged_in)

    def _clear_passwords(self) -> None:
        self.fields["password"].clear()
        self.fields["confirm"].clear()

    def _logged_in(self, ok: bool, value) -> None:
        self._busy(False)
        if ok:
            self._clear_passwords()
        else:
            _show(self.status, str(value))
        self.refresh()

    def _signed_up(self, ok: bool, value) -> None:
        self._busy(False)
        if not ok:
            _show(self.status, str(value))
        elif value is None:  # a confirmation email is on its way
            email = self.fields["email"].text().strip()
            self._clear_passwords()
            self.set_mode("login")
            self.fields["email"].setText(email)
            _show(self.status, "Almost there! We’ve sent a confirmation link to that address. Open it to activate "
                  "your account, then log in here.", "secondary")
        else:
            self._clear_passwords()
        self.refresh()

    def forgot(self) -> None:
        email = self._values()["email"]
        error = validate_email(email)
        _show(self.field_errors["email"], error or "")
        if error:
            _show(self.status, "Enter your email above, then choose “Forgot password?” again.")
            return
        self._busy(True)

        def done(ok, value):
            self._busy(False)
            # The same answer whether or not an account exists, so nobody can probe which emails are registered.
            _show(self.status, "If an account exists for that address, we’ve sent a link to choose a new password."
                  if ok else str(value), "secondary" if ok else "error")
        self.service.request_reset(email, done)

    def save_username(self) -> None:
        username = self.username_field.text().strip()
        error = validate_username(username)
        if error:
            _show(self.username_status, error)
            return
        if self.service.account and username == self.service.account.username:
            _show(self.username_status, "That’s already your username.", "secondary")
            return
        self._busy(True)

        def done(ok, value):
            self._busy(False)
            _show(self.username_status, "Saved." if ok else str(value), "secondary" if ok else "error")
            self.refresh()
        self.service.set_username(username, done)

    @staticmethod
    def sidebar_label(account: Account | None = None) -> str:
        return "Account" if account is not None else "Log in"
