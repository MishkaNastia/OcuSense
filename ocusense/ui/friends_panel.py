"""Friends on the Account page: add a player by username, answer requests, unfriend.

Friends see each other on the Friends leaderboard in Games. A request needs the
other player's OK; either of you can remove the friendship later. Everything goes
through AccountService (ocusense/leaderboards.py, supabase/schema.sql).
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from ocusense.accounts import validate_username
from ocusense.leaderboards import FRIEND_REPLIES, Friend

from . import theme
from .account_service import AccountService
from .widgets.common import button, label
from .widgets.page import paragraph

GROUPS = (("incoming", "Asking to be your friend"), ("friend", "Friends"), ("outgoing", "Waiting for an answer"))


class FriendsPanel(QWidget):
    def __init__(self, service: AccountService, parent=None):
        super().__init__(parent)
        self.service = service
        self.friends: list[Friend] = []
        self.loaded = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(paragraph(
            "Add friends by their username to compare scores on the Friends leaderboard in Games. They see your "
            "username and game scores only.", 13, secondary=True))
        row = QHBoxLayout()
        row.setSpacing(10)
        self.name_field = QLineEdit()
        self.name_field.setPlaceholderText("Friend’s username")
        self.name_field.setAccessibleName("Friend’s username")
        self.name_field.setMinimumWidth(280)
        self.name_field.setMaximumWidth(420)
        self.name_field.returnPressed.connect(self.add)
        self.add_button = button("Add friend", "secondary")
        self.add_button.clicked.connect(self.add)
        row.addWidget(self.name_field)
        row.addWidget(self.add_button)
        row.addStretch(1)
        layout.addLayout(row)
        self.status = label("", "secondary", theme.ui_font(13), wrap=True)
        layout.addWidget(self.status)
        self.list = QWidget()
        self.list_layout = QVBoxLayout(self.list)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(6)
        layout.addWidget(self.list)

    # ------------------------------------------------------------ loading
    def load(self) -> None:
        if not self.service.signed_in:
            self.friends, self.loaded = [], False
            self._render()
            return

        def done(ok, value):
            if ok:
                self.friends, self.loaded = value, True
            else:
                self.status.setText(str(value))
            self._render()
        self.service.friends(done)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.load()

    # ------------------------------------------------------------ display
    def _render(self) -> None:
        while self.list_layout.count():
            widget = self.list_layout.takeAt(0).widget()
            if widget is not None:
                widget.setParent(None)  # gone at once, not only once Qt gets round to deleting it
                widget.deleteLater()
        for status, title in GROUPS:
            people = [f for f in self.friends if f.status == status]
            if not people:
                continue
            self.list_layout.addWidget(label(f"{title} ({len(people)})", font=theme.ui_font(14, QFont.Weight.Bold)))
            for friend in people:
                self.list_layout.addWidget(self._row(friend))
        if self.loaded and not self.friends:
            self.list_layout.addWidget(label("No friends added yet.", "secondary", theme.ui_font(13)))
        has_name = bool(self.service.account and self.service.account.username)
        self.add_button.setEnabled(has_name)
        self.name_field.setEnabled(has_name)
        if not has_name and self.service.account is not None:
            self.status.setText("Choose a username above first — friends find you by it.")

    def _row(self, friend: Friend) -> QWidget:
        row = QWidget()
        box = QHBoxLayout(row)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(10)
        box.addWidget(label(f"@{friend.username}", font=theme.ui_font(15)))
        box.addStretch(1)
        actions = {"incoming": (("Accept", "primary", lambda: self.respond(friend, True)),
                                ("Decline", "quiet", lambda: self.respond(friend, False))),
                   "friend": (("Remove", "quiet", lambda: self.remove(friend)),),
                   "outgoing": (("Cancel request", "quiet", lambda: self.remove(friend)),)}[friend.status]
        for text, kind, handler in actions:
            action = button(text, kind)
            action.setAccessibleName(f"{text} @{friend.username}")
            action.clicked.connect(handler)
            box.addWidget(action, 0, Qt.AlignmentFlag.AlignRight)
        return row

    # ------------------------------------------------------------ actions
    def add(self) -> None:
        name = self.name_field.text().strip().lstrip("@")
        error = validate_username(name)
        if error:
            self.status.setText("Usernames are 3–20 letters, numbers or underscores.")
            return
        self.add_button.setEnabled(False)

        def done(ok, value):
            self.add_button.setEnabled(True)
            if ok:
                self.name_field.clear()
                self.status.setText(FRIEND_REPLIES[value].format(name=name))
                self.load()
            else:
                self.status.setText(str(value))
        self.service.request_friend(name, done)

    def respond(self, friend: Friend, accept: bool) -> None:
        def done(ok, value):
            if ok:
                self.status.setText(f"You and @{friend.username} are friends now." if accept and value == "accepted"
                                    else f"Declined @{friend.username}’s request." if not accept
                                    else "That request isn’t open any more.")
            else:
                self.status.setText(str(value))
            self.load()
        self.service.respond_friend(friend.user_id, accept, done)

    def remove(self, friend: Friend) -> None:
        def done(ok, value):
            self.status.setText((f"Removed @{friend.username}." if friend.status == "friend"
                                 else f"Cancelled your request to @{friend.username}.") if ok else str(value))
            self.load()
        self.service.remove_friend(friend.user_id, done)
