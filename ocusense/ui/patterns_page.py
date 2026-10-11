"""Statistics › Understanding your patterns: what each measurement means, in plain language.

Personal observations need both session history and the user's own check-ins.
The Mac app does not record check-ins yet, so no observations are drawn — the
page says so instead of inventing findings, scores or classifications.
"""

from PySide6.QtGui import QFont

from ocusense.config import CLOSE_BELOW, MIN_VALID_SECONDS_FOR_RATE, REOPEN_ABOVE, ROLLING_WINDOW_SECONDS
from ocusense.core.models import SessionSummary
from ocusense.core.stats import METRICS

from . import theme
from .widgets.common import label
from .widgets.page import Page, paragraph

PLACEHOLDER = "Your patterns will appear as you complete sessions."


class PatternsPage(Page):
    def __init__(self, parent=None):
        super().__init__("Statistics", "Understanding your patterns",
                         "What OcuSense measures, what the numbers mean, and what they can’t tell you.", parent)

        self.section("Your observations")
        self.observations = label(PLACEHOLDER, font=theme.ui_font(20, QFont.Weight.Bold), wrap=True)
        self.body.addWidget(self.observations)
        self.observations_detail = paragraph("", secondary=True)
        self.body.addWidget(self.observations_detail)

        self.section("Personal eye openness")
        self.body.addWidget(paragraph(
            "During calibration OcuSense records how your eyes look comfortably open and gently closed. "
            "100% means as open as during calibration, 0% means as closed. Everything is relative to you."))
        self.body.addWidget(paragraph(
            "<b>It is not a fatigue percentage</b> and not a literal measure of how far your eyelids are open. "
            "Lighting, camera angle, glasses and head position change it, so recalibrate when they change.", rich=True))

        for key in ("rate", "closure", "closed"):
            m = METRICS[key]
            self.section(f"{m['name']} · {m['unit']}")
            self.body.addWidget(paragraph(m["explain"]))
        self.body.addWidget(paragraph(
            f"A blink is counted when your personal eye openness falls below {CLOSE_BELOW:.0%} and rises above "
            f"{REOPEN_ABOVE:.0%} again. Two thresholds stop small wobbles from counting twice.", secondary=True))

        self.section("Tracking coverage and gaps")
        self.body.addWidget(paragraph(
            "Tracking coverage is the share of study time when both eyes were measured reliably. When your face "
            "isn’t visible, measurement pauses: that time is left out, never counted as zero blinks or closed eyes."))
        self.body.addWidget(paragraph(
            f"On the Study page, blink rate and closed time appear after {MIN_VALID_SECONDS_FOR_RATE:.0f} seconds of "
            f"tracking within the last {ROLLING_WINDOW_SECONDS:.0f} seconds, so a few blinks can’t produce a "
            "misleading number. This is an engineering choice, not a clinical standard.", secondary=True))

        self.section("What these numbers can’t tell you")
        self.body.addWidget(paragraph(
            "OcuSense is not a medical device. It doesn’t diagnose tiredness, dry eye or any other condition, and "
            "it doesn’t give health scores. Its numbers describe what the camera measured; how you feel is something "
            "only you can report. Compare your numbers with your own earlier sessions, not with other people."))
        self.finish()
        self.refresh([])

    def refresh(self, sessions: list[SessionSummary]) -> None:
        # Observations need check-ins to compare against; until the app records them, always the placeholder.
        self.observations.setText(PLACEHOLDER)
        count = len(sessions)
        self.observations_detail.setText(
            "OcuSense describes what it measures and doesn’t draw personal conclusions (it’s an app, not a fortune teller). "
            + (f"Your measured numbers from {count} session{'s' if count != 1 else ''} are under All time."
               if count else "Your measured numbers will be under All time after your first session."))
