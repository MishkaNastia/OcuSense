"""Time log: subjects and projects, the one-at-a-time timer, totals, the saved file and the page."""

import json
import os
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from ocusense.core.timelog import TimeLog, day_start, period_bounds
from ocusense.timelog_store import TimeLogStore

HOUR = 3600
MON = datetime(2026, 10, 5, 9, 0).timestamp()  # Monday 5 October 2026, 09:00


class TimerTest(unittest.TestCase):
    def setUp(self):
        self.log = TimeLog()
        self.bio = self.log.add_subject("Systems Biology")
        self.ocu = self.log.add_subject("OcuSense", "project")

    def test_one_timer_at_a_time(self):
        self.log.start(self.bio.id, MON)
        self.log.start(self.ocu.id, MON + HOUR)  # starting another stops the first
        running = [e for e in self.log.entries if e.running]
        self.assertEqual([e.subject_id for e in running], [self.ocu.id])
        self.assertEqual(self.log.entries[0].end, MON + HOUR)

    def test_toggle_stops_the_running_subject(self):
        self.log.toggle(self.bio.id, MON)
        self.assertIsNone(self.log.toggle(self.bio.id, MON + 90))
        self.assertIsNone(self.log.running())
        self.assertEqual(self.log.total(MON, MON + HOUR, MON + HOUR, self.bio.id), 90)

    def test_running_entry_counts_up_to_now(self):
        self.log.start(self.bio.id, MON)
        self.assertEqual(self.log.total(MON - HOUR, MON + 10 * HOUR, MON + 600), 600)

    def test_entry_across_midnight_counts_on_both_days(self):
        late = datetime(2026, 10, 5, 23, 0).timestamp()
        self.log.add_entry(self.bio.id, late, late + 2 * HOUR)
        monday, tuesday = period_bounds("today", date(2026, 10, 5)), period_bounds("today", date(2026, 10, 6))
        self.assertEqual(self.log.total(*monday, late + 3 * HOUR), HOUR)
        self.assertEqual(self.log.total(*tuesday, late + 3 * HOUR), HOUR)

    def test_week_runs_monday_to_sunday(self):
        a, b = period_bounds("week", date(2026, 10, 11))  # a Sunday
        self.assertEqual(a, day_start(date(2026, 10, 5)))
        self.assertEqual(b, day_start(date(2026, 10, 12)))

    def test_totals_by_subject_most_time_first(self):
        self.log.add_entry(self.bio.id, MON, MON + HOUR)
        self.log.add_entry(self.ocu.id, MON + HOUR, MON + 3 * HOUR)
        rows = self.log.totals_by_subject(*period_bounds("all", date.today()), MON + 5 * HOUR)
        self.assertEqual([(s.name, sec) for s, sec in rows], [("OcuSense", 2 * HOUR), ("Systems Biology", HOUR)])

    def test_edit_rejects_an_end_before_the_start(self):
        entry = self.log.add_entry(self.bio.id, MON, MON + HOUR)
        with self.assertRaises(ValueError):
            self.log.edit_entry(entry.id, end=MON - 1)
        with self.assertRaises(ValueError):
            self.log.add_entry(self.bio.id, MON, MON)

    def test_deleting_a_subject_deletes_its_entries(self):
        self.log.add_entry(self.bio.id, MON, MON + HOUR)
        self.log.add_entry(self.ocu.id, MON, MON + HOUR)
        self.log.remove_subject(self.bio.id)
        self.assertEqual({e.subject_id for e in self.log.entries}, {self.ocu.id})

    def test_round_trip_and_damaged_rows(self):
        self.log.add_entry(self.bio.id, MON, MON + HOUR, "chapter 3")
        data = self.log.to_dict()
        data["entries"].append({"id": "x", "subject_id": "nobody", "start": 1, "end": 2})  # unknown subject
        data["entries"].append({"id": "y", "subject_id": self.bio.id, "start": 5, "end": 1})  # ends before it starts
        data["subjects"].append({"id": "", "name": "no id"})
        again = TimeLog.from_dict(json.loads(json.dumps(data)))
        self.assertEqual([s.name for s in again.subjects], ["Systems Biology", "OcuSense"])
        self.assertEqual([(e.note, e.end - e.start) for e in again.entries], [("chapter 3", HOUR)])


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / "timelog.json"

    def tearDown(self):
        self.folder.cleanup()

    def test_changes_are_saved_and_a_running_timer_survives_a_restart(self):
        store = TimeLogStore(self.path)
        subject = store.change(lambda log: log.add_subject("Genomics"))
        store.change(lambda log: log.start(subject.id, MON))
        again = TimeLogStore(self.path)
        self.assertEqual(again.log.running().subject_id, subject.id)

    def test_a_damaged_file_is_kept_and_not_overwritten(self):
        self.path.write_text("{ not json")
        store = TimeLogStore(self.path)
        self.assertTrue(store.read_only)
        self.assertIsNone(store.change(lambda log: log.add_subject("Genomics")))
        self.assertEqual(self.path.read_text(), "{ not json")

    def test_sits_next_to_the_preferences_in_tests(self):
        from ocusense import timelog_store
        old = dict(os.environ)
        try:
            os.environ.pop("OCUSENSE_TIMELOG_FILE", None)
            os.environ["OCUSENSE_PREFERENCES_FILE"] = str(Path(self.folder.name) / "preferences.json")
            self.assertEqual(timelog_store.default_path(), Path(self.folder.name) / "timelog.json")
        finally:
            os.environ.clear()
            os.environ.update(old)


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])


class PageTest(unittest.TestCase):
    def setUp(self):
        from ocusense.ui.time_log_page import TimeLogPage
        self.folder = tempfile.TemporaryDirectory()
        self.store = TimeLogStore(Path(self.folder.name) / "timelog.json")
        self.page = TimeLogPage(self.store)
        self.clock = [MON]
        self.page.now = lambda: self.clock[0]
        self.page.ticker.stop()
        self.statuses = []
        self.page.status_text.connect(self.statuses.append)

    def tearDown(self):
        self.page.deleteLater()
        self.folder.cleanup()

    def add(self, name, kind="subject"):
        return self.store.change(lambda log: log.add_subject(name, kind))

    def test_cards_have_no_start_button(self):
        bio = self.add("Systems Biology")
        self.page.refresh()
        from PySide6.QtWidgets import QPushButton
        texts = [b.text() for b in self.page.cards[bio.id].findChildren(QPushButton)]
        self.assertNotIn("Start", texts)

    def test_click_a_cards_mark_to_change_its_colour(self):
        from PySide6.QtCore import QPoint
        from PySide6.QtTest import QTest
        bio = self.add("Systems Biology")
        self.page.refresh()
        QTest.mouseClick(self.page.cards[bio.id].mark, Qt.MouseButton.LeftButton)
        swatch = self.page.colour_popup.choice.buttons["violet"]
        QTest.mouseClick(swatch, Qt.MouseButton.LeftButton, pos=QPoint(17, 17))
        self.assertEqual(self.store.log.subject(bio.id).colour, "violet")

    def test_dialogs_have_no_title_bar_and_delete_asks_inside(self):
        from ocusense.ui.time_log_page import SubjectDialog
        bio = self.add("Systems Biology")
        dialog = SubjectDialog(bio, 0)
        self.assertTrue(dialog.windowFlags() & Qt.WindowType.FramelessWindowHint)
        dialog.delete_button.click()
        self.assertTrue(dialog.confirm.isVisibleTo(dialog))
        self.assertFalse(dialog.button_row.isVisibleTo(dialog))
        dialog.really_delete.click()
        self.assertTrue(dialog.deleted)
        self.assertEqual(dialog.result(), dialog.DialogCode.Accepted)

    def test_swatches_in_the_dialog_respond_to_clicks(self):
        from PySide6.QtCore import QPoint
        from PySide6.QtTest import QTest
        from ocusense.ui.time_log_page import SubjectDialog
        dialog = SubjectDialog()
        QTest.mouseClick(dialog.colour.buttons["teal"], Qt.MouseButton.LeftButton, pos=QPoint(17, 17))
        self.assertEqual(dialog.colour.current(), "teal")

    def test_start_and_stop_from_the_timer(self):
        bio = self.add("Systems Biology")
        self.page.refresh()
        self.page.choose_subject(bio.id)
        self.page.main_button.click()
        self.assertEqual(self.store.log.running().subject_id, bio.id)
        self.clock[0] += 125
        self.page.tick()
        self.assertEqual(self.page.clock_label.text(), "0:02:05")
        self.assertEqual(self.statuses[-1], "0:02:05")
        self.assertIn("0:02:05", self.page.cards[bio.id].live_label.text())
        self.page.main_button.click()  # Stop in the timer bar
        self.assertIsNone(self.store.log.running())
        self.assertEqual(self.statuses[-1], "")

    def test_choosing_a_subject_while_running_gives_it_to_the_running_entry(self):
        bio, ocu = self.add("Systems Biology"), self.add("OcuSense", "project")
        self.page.refresh()
        self.page.toggle(bio.id)
        self.clock[0] += 600
        self.page.open_picker().rows[[r.text() for r in self.page.picker.rows].index("OcuSense")].click()
        self.assertEqual(len(self.store.log.entries), 1)  # the same entry, now for OcuSense (as in Toggl)
        self.assertEqual(self.store.log.running().subject_id, ocu.id)
        self.assertEqual(self.store.log.total(MON, MON + HOUR, MON + 600, ocu.id), 600)

    def test_add_a_subject_through_the_dialog(self):
        def accept(dialog):
            dialog.name.setText("Applied Data Analysis")
            return True
        self.page._dialog = accept
        self.page.add_card.button.click()
        self.assertEqual([s.name for s in self.store.log.subjects], ["Applied Data Analysis"])
        self.assertEqual(len(self.page.cards), 1)

    def test_new_subject_typed_in_the_picker_is_made_without_a_window(self):
        def no_window(dialog):
            raise AssertionError("no window")
        self.page._dialog = no_window
        self.assertEqual(self.page.chip.text(), "Project or subject")
        picker = self.page.open_picker()
        self.assertEqual([r.text() for r in picker.rows], ["No project"])
        picker.search.setText("Machine Learning")
        picker.create_project.click()
        subject = self.store.log.subjects[0]
        self.assertEqual((subject.name, subject.kind), ("Machine Learning", "project"))
        self.assertEqual(self.page.chip.text(), "Machine Learning")  # chosen for the timer
        self.page.main_button.click()
        self.assertEqual(self.store.log.running().subject_id, subject.id)

    def test_picker_search_filters_and_groups(self):
        self.add("Systems Biology")
        self.add("Machine Learning", "project")
        self.add("Mathematics of Data")
        picker = self.page.open_picker()
        self.assertEqual([r.text() for r in picker.rows],
                         ["No project", "Systems Biology", "Mathematics of Data", "Machine Learning"])
        picker.search.setText("ma")
        self.assertEqual([r.text() for r in picker.rows], ["Mathematics of Data", "Machine Learning"])
        picker.rows[1].click()
        self.assertEqual(self.page.chip.text(), "Machine Learning")

    def test_start_records_at_once_without_any_window(self):
        def no_window(dialog):
            raise AssertionError("Start must not open a window")
        self.page._dialog = no_window
        self.page.main_button.click()
        running = self.store.log.running()
        self.assertEqual(running.subject_id, "")  # no project yet
        self.clock[0] += 300
        self.page.refresh()
        self.assertEqual(self.page.calendar.items[0][4], "No project")
        rows = self.store.log.totals_by_subject(MON, MON + HOUR, self.clock[0])
        self.assertEqual([(s.name, sec) for s, sec in rows], [("No project", 300)])
        ocu = self.add("OcuSense", "project")  # give it a subject later, while it runs
        self.page.refresh()
        self.page.open_picker().rows[[r.text() for r in self.page.picker.rows].index("OcuSense")].click()
        self.assertEqual(self.store.log.running().subject_id, ocu.id)

    def test_every_colour_has_a_swatch(self):
        from ocusense.core.timelog import COLOURS
        from ocusense.ui.time_log_page import HEX, SubjectDialog
        self.assertGreaterEqual(len(COLOURS), 18)
        self.assertEqual(set(SubjectDialog().colour.buttons), set(COLOURS))
        self.assertTrue(set(COLOURS) <= set(HEX))

    def test_add_a_past_entry_through_the_dialog(self):
        bio = self.add("Systems Biology")
        self.page.refresh()
        from PySide6.QtCore import QTime

        def accept(dialog):
            dialog.start.setTime(QTime(8, 0))
            dialog.end.setTime(QTime(8, 45))
            dialog.note.setText("lecture 4")
            return True
        self.page._dialog = accept
        self.page.add_entry(bio.id)
        entry = self.store.log.entries[0]
        self.assertEqual((entry.end - entry.start, entry.note), (45 * 60, "lecture 4"))
        self.assertEqual(len(self.page.calendar.items), 1)

    def test_typing_a_duration_moves_the_end(self):
        from PySide6.QtCore import QTime
        from ocusense.ui.time_log_page import EntryDialog, parse_duration
        self.assertEqual([parse_duration(t) for t in ("1:30", "45m", "2h", "1h 15m", "90", "x")],
                         [5400, 2700, 7200, 4500, 5400, None])
        bio = self.add("Systems Biology")
        entry = self.store.change(lambda log: log.add_entry(bio.id, MON, MON + HOUR))
        dialog = EntryDialog(self.store.log, entry, now=MON + 5 * HOUR)
        dialog.duration.setText("1:45")
        dialog._duration_typed()
        self.assertEqual(dialog.end.time(), QTime(10, 45))
        _, start, end, _ = dialog.values()
        self.assertEqual(end - start, 105 * 60)
        dialog.end.setTime(QTime(8, 0))  # before the start: ran past midnight
        self.assertTrue(dialog.next_day.isVisibleTo(dialog))
        self.assertEqual(dialog.values()[2] - dialog.values()[1], 23 * HOUR)

    def test_continue_a_logged_entry(self):
        bio = self.add("Systems Biology")
        entry = self.store.change(lambda log: log.add_entry(bio.id, MON - 2 * HOUR, MON - HOUR, "chapter 3"))
        self.page.refresh()

        def press_continue(dialog):
            dialog.continue_button.click()
            return dialog.result() == dialog.DialogCode.Accepted
        self.page._dialog = press_continue
        self.page.edit_entry(entry.id)
        running = self.store.log.running()
        self.assertEqual((running.subject_id, running.note, running.start), (bio.id, "chapter 3", MON))

    def test_running_changed_is_emitted_when_a_timer_starts_and_stops(self):
        changes = []
        self.page.running_changed.connect(changes.append)
        self.page.main_button.click()
        self.clock[0] += 60
        self.page.main_button.click()
        self.assertEqual(changes, [True, False])

    def test_a_timer_left_running_at_launch_starts_nothing(self):
        from ocusense.ui.time_log_page import TimeLogPage
        self.store.change(lambda log: log.start("", MON))
        changes = []
        page = TimeLogPage(self.store)
        page.running_changed.connect(changes.append)
        page.ticker.stop()
        page.refresh()
        self.assertEqual(changes, [])
        page.deleteLater()

    def test_main_window_has_the_page(self):
        from ocusense.ui.sidebar import Sidebar
        bar = Sidebar()
        self.assertIn("time_log", bar.items)
        bar.set_time_log_status("0:01:00")
        self.assertEqual(bar.items["time_log"].text(), "Time log · 0:01:00")


if __name__ == "__main__":
    unittest.main()
