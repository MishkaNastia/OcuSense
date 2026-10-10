"""Account / Log in.

The Mac app has no sign-in yet (the website has optional accounts, but the app is
not connected to them). So this page shows the signed-out view with its buttons
disabled and says plainly that accounts aren't available — it never pretends a
sign-in worked. Monitoring works fully without an account.
"""

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QPushButton

from . import theme
from .widgets.common import label
from .widgets.page import Page, paragraph

AVAILABLE = False  # becomes True only when the app has real authentication


class AccountPage(Page):
    def __init__(self, parent=None):
        super().__init__("Account", "Log in")
        self.set_tag("Not available yet", "The Mac app isn’t connected to OcuSense accounts yet.")
        self.body.addWidget(label("Accounts aren’t available in the Mac app yet.",
                                  font=theme.ui_font(22, QFont.Weight.Bold), wrap=True))
        self.body.addWidget(paragraph(
            "You don’t need an account: calibration, monitoring and Statistics all work on this Mac without one, "
            "and nothing is sent anywhere."))
        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.login_button = QPushButton("Log in")
        self.login_button.setProperty("kind", "primary")
        self.create_button = QPushButton("Create account")
        self.create_button.setProperty("kind", "secondary")
        for widget in (self.login_button, self.create_button):
            widget.setEnabled(AVAILABLE)
            widget.setToolTip("Not available yet")
            actions.addWidget(widget)
        actions.addStretch(1)
        self.body.addSpacing(6)
        self.body.addLayout(actions)
        self.body.addSpacing(6)
        self.body.addWidget(paragraph(
            "When accounts arrive, signing in will be optional. This page will then show your account details "
            "and a Log out button.", secondary=True))
        self.finish()

    @staticmethod
    def sidebar_label() -> str:
        return "Log in"  # "Account" once a real sign-in exists and the person is signed in
