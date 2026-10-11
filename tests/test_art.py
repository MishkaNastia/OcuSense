"""Art shop and Your gallery: catalogue, wallet (purchases, rewards, ledger), and the two pages."""

import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from ocusense.art import rewards
from ocusense.art.catalogue import FOLDER, CatalogueError, load_catalogue
from ocusense.art.wallet import DEMO_START_COINS, AlreadyOwned, NotEnoughCoins, StoreError, Wallet
from ocusense.preferences import clean_display_name


def temp_dir() -> Path:
    return Path(tempfile.mkdtemp(prefix="ocusense-art-"))


class Clock:
    def __init__(self, start=datetime(2026, 10, 11, 9, 0)):
        self.t = start

    def __call__(self):
        self.t += timedelta(seconds=1)
        return self.t


class CatalogueTest(unittest.TestCase):
    def test_every_painting_has_its_source_rights_and_image(self):
        art = load_catalogue()
        self.assertGreaterEqual(len(art), 8)
        self.assertLessEqual(len(art), 12)
        self.assertEqual(len({a.id for a in art}), len(art))
        self.assertGreaterEqual(len({a.price for a in art}), 3)  # different prices
        for a in art:
            self.assertTrue(a.id.startswith("met-"), a.id)
            self.assertIsNotNone(a.image_path, a.id)
            self.assertLess(a.image_path.stat().st_size, 600_000, a.id)  # reasonable size
            self.assertIn("Public domain", a.rights)
            self.assertIn("CC0", a.rights)
            self.assertEqual(a.license_url, "https://creativecommons.org/publicdomain/zero/1.0/")
            self.assertTrue(a.source_url.startswith("https://www.metmuseum.org/art/collection/search/"))
            self.assertTrue(a.date and a.institution and a.rights_checked)

    def test_missing_image_and_broken_entries(self):
        folder = temp_dir()
        shutil.copy(FOLDER / "catalogue.json", folder / "catalogue.json")
        data = json.loads((folder / "catalogue.json").read_text())
        data["artworks"].append({"id": "broken", "title": "No rights recorded"})  # incomplete: skipped
        (folder / "catalogue.json").write_text(json.dumps(data))
        art = load_catalogue(folder)  # no images copied
        self.assertEqual(len(art), len(load_catalogue()))
        self.assertTrue(all(a.image_path is None for a in art))
        (folder / "catalogue.json").write_text("{not json")
        with self.assertRaises(CatalogueError):
            load_catalogue(folder)


class WalletTest(unittest.TestCase):
    def setUp(self):
        self.path = temp_dir() / "collection.sqlite3"
        self.wallet = Wallet(self.path, now=Clock())

    def test_reward_then_purchase(self):
        self.assertEqual(self.wallet.award("game:eye_game:1", 120, "eye_game").coins, 120)
        self.assertEqual(self.wallet.buy("met-1", 100), 20)
        self.assertEqual(self.wallet.balance(), 20)
        self.assertIn("met-1", self.wallet.owned())
        kinds = [(e.kind, e.amount) for e in self.wallet.history()]
        self.assertEqual(kinds, [("reward", 120), ("purchase", -100)])  # every change explainable

    def test_insufficient_balance_changes_nothing(self):
        self.wallet.award("game:x:1", 50, "eye_game")
        with self.assertRaises(NotEnoughCoins) as caught:
            self.wallet.buy("met-1", 100)
        self.assertEqual((caught.exception.balance, caught.exception.price), (50, 100))
        self.assertEqual(self.wallet.balance(), 50)
        self.assertEqual(self.wallet.owned(), {})

    def test_duplicate_purchase_is_never_charged_twice(self):
        self.wallet.award("game:x:1", 500, "eye_game")
        self.wallet.buy("met-1", 100)
        with self.assertRaises(AlreadyOwned):
            self.wallet.buy("met-1", 100)
        self.assertEqual(self.wallet.balance(), 400)
        other = Wallet(self.path)  # a second window / process
        with self.assertRaises(AlreadyOwned):
            other.buy("met-1", 100)
        self.assertEqual(other.balance(), 400)

    def test_duplicate_reward_event_pays_once(self):
        self.assertEqual(self.wallet.award("game:blink_code:abc", 30, "blink_code").coins, 30)
        again = self.wallet.award("game:blink_code:abc", 30, "blink_code")
        self.assertTrue(again.duplicate)
        self.assertEqual(self.wallet.balance(), 30)

    def test_daily_limit(self):
        self.assertEqual(self.wallet.award("a", 100, "g", daily_limit=150).coins, 100)
        cut = self.wallet.award("b", 100, "g", daily_limit=150)
        self.assertEqual((cut.coins, cut.limited), (50, True))
        none = self.wallet.award("c", 10, "g", daily_limit=150)
        self.assertEqual((none.coins, none.limited), (0, True))
        self.wallet.now = lambda: datetime(2026, 10, 12, 9, 0)  # the next day
        self.assertEqual(self.wallet.award("d", 10, "g", daily_limit=150).coins, 10)

    def test_purchase_is_atomic(self):
        self.wallet.award("game:x:1", 500, "eye_game")
        connection = sqlite3.connect(self.path)  # make adding the painting fail after the charge
        connection.execute("CREATE TRIGGER fail BEFORE INSERT ON owned BEGIN SELECT RAISE(ABORT, 'disk full'); END")
        connection.commit()
        connection.close()
        with self.assertRaises(StoreError):
            self.wallet.buy("met-1", 100)
        self.assertEqual(self.wallet.balance(), 500)  # the charge was rolled back too
        self.assertEqual(self.wallet.owned(), {})
        self.assertEqual(len(self.wallet.history()), 1)

    def test_persists_after_restart(self):
        self.wallet.award("game:x:1", 300, "eye_game")
        self.wallet.buy("met-2", 200)
        reopened = Wallet(self.path)
        self.assertEqual(reopened.balance(), 100)
        self.assertEqual(list(reopened.owned()), ["met-2"])

    def test_demo_wallet_is_separate(self):
        folder = temp_dir()
        os.environ["OCUSENSE_DATA_DIR"], previous = str(folder), os.environ.get("OCUSENSE_DATA_DIR")
        saved_collection = os.environ.pop("OCUSENSE_COLLECTION_FILE", None)
        try:
            demo = Wallet(demo=True)
            real = Wallet()
            self.assertNotEqual(demo.path, real.path)
            self.assertEqual(demo.balance(), DEMO_START_COINS)
            demo.buy("met-1", 100)
            self.assertEqual(real.balance(), 0)
            self.assertEqual(real.owned(), {})
            self.assertEqual(Wallet(demo=True).balance(), DEMO_START_COINS - 100)  # demo coins granted once
            with self.assertRaises(StoreError):
                Wallet(demo.path)  # a demo file can never be opened as the real collection
        finally:
            if previous is None:
                os.environ.pop("OCUSENSE_DATA_DIR", None)
            else:
                os.environ["OCUSENSE_DATA_DIR"] = previous
            if saved_collection is not None:
                os.environ["OCUSENSE_COLLECTION_FILE"] = saved_collection

    def test_storage_failure_is_reported(self):
        blocked = temp_dir() / "not-a-file"
        blocked.mkdir()
        with self.assertRaises(StoreError):
            Wallet(blocked)


class RewardRulesTest(unittest.TestCase):
    def test_rules(self):
        self.assertEqual(rewards.blink_code_coins(400, 0), 0)  # nothing spelled, nothing earned
        self.assertEqual(rewards.blink_code_coins(200, 2), 18)
        self.assertEqual(rewards.blink_code_coins(5000, 9), rewards.BLINK_CODE_MAX)
        self.assertEqual(rewards.eye_game_coins(49), 0)
        self.assertEqual(rewards.eye_game_coins(200), 10)
        self.assertEqual(rewards.eye_game_coins(10_000), rewards.EYE_GAME_MAX)

    def test_display_name_cleaning(self):
        self.assertEqual(clean_display_name("  Irem \n Uluc\t"), "Irem Uluc")
        self.assertEqual(len(clean_display_name("x" * 100)), 40)
        self.assertEqual(clean_display_name("<b>Bob</b>"), "<b>Bob</b>")  # kept as text, shown as plain text


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QObject, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from ocusense.accounts import Account  # noqa: E402

from ocusense.preferences import Preferences  # noqa: E402
from ocusense.ui.art_collection import ArtCollection  # noqa: E402
from ocusense.ui.gallery_page import GalleryPage, gallery_title  # noqa: E402
from ocusense.ui.shop_page import ShopPage  # noqa: E402

app = QApplication.instance() or QApplication([])


class FakeAccounts(QObject):
    changed = Signal(object)

    def __init__(self, username: str):
        super().__init__()
        self.account = Account("u1", "a@b.co", username)


class PagesTest(unittest.TestCase):
    def setUp(self):
        self.folder = temp_dir()
        self.wallet = Wallet(self.folder / "c.sqlite3", now=Clock())
        self.art = ArtCollection(wallet=self.wallet)
        self.prefs = Preferences()
        self.prefs.save = lambda path=None: True
        self.shop = ShopPage(self.art)
        self.gallery = GalleryPage(self.art, self.prefs)
        self.first = self.art.catalogue[0]  # a 100-coin painting

    def test_purchase_flow_updates_both_pages(self):
        self.wallet.award("game:x:1", 150, "eye_game")
        self.art.reload()
        self.art.changed.emit()
        self.assertEqual(self.shop.badge.text.text(), "150 coins")
        self.assertTrue(self.gallery.empty.isVisibleTo(self.gallery))
        asked = []
        self.shop.confirm = lambda artwork, balance: asked.append((artwork.id, balance)) or True
        self.shop.start_purchase(self.first.id)
        self.assertEqual(asked, [(self.first.id, 150)])
        self.assertIn("Added to your gallery", self.shop.notice_text.text())
        self.assertFalse(self.shop.notice_view.isHidden())
        self.assertEqual(self.shop.badge.text.text(), "50 coins")
        self.assertTrue(self.shop.footers[self.first.id].buy.isHidden())  # now "In your gallery"
        self.assertEqual(self.gallery.count.text(), "1 painting in your collection")
        self.assertEqual(self.gallery.badge.text.text(), "50 coins")
        self.assertEqual([c.artwork.id for c in self.gallery.grid.cards], [self.first.id])

    def test_cancel_insufficient_owned_and_double_click(self):
        self.wallet.award("game:x:1", 100, "eye_game")
        self.art.reload()
        self.shop.confirm = lambda artwork, balance: False  # cancelled
        self.shop.start_purchase(self.first.id)
        self.assertEqual(self.art.balance(), 100)
        self.assertFalse(self.art.is_owned(self.first.id))
        expensive = max(self.art.catalogue, key=lambda a: a.price)
        self.shop.start_purchase(expensive.id)
        self.assertIn("more coins", self.shop.notice_text.text())

        def click_again_while_confirming(artwork, balance):
            self.shop.start_purchase(self.first.id)  # a second click lands while the dialog is open
            return True
        self.shop.confirm = click_again_while_confirming
        self.shop.start_purchase(self.first.id)
        self.assertEqual(self.art.balance(), 0)  # charged once
        self.assertEqual(len([e for e in self.wallet.history() if e.kind == "purchase"]), 1)
        self.shop.start_purchase(self.first.id)
        self.assertIn("already in your gallery", self.shop.notice_text.text())

    def test_detail_view_and_missing_image_placeholder(self):
        self.shop.open_artwork(self.first.id)
        self.assertIsNotNone(self.shop.dialog.buy_button)
        self.assertFalse(self.shop.dialog.grab().isNull())
        from dataclasses import replace
        missing = replace(self.first, image_path=None)
        from ocusense.ui.widgets.art_frame import ArtCard
        card = ArtCard(missing)
        self.assertFalse(card.grab().isNull())  # drawn as a marked placeholder, no crash

    def test_gallery_name_fallbacks_and_plain_text(self):
        self.assertEqual(gallery_title(""), "Your gallery")
        self.assertEqual(self.gallery.title_label.text(), "Your gallery")
        self.gallery._edit_name()
        self.gallery.name_field.setText("  <i>Mira</i> ")
        self.gallery.save_name()
        self.assertEqual(self.gallery.title_label.text(), "<i>Mira</i>’s gallery")
        from PySide6.QtCore import Qt
        self.assertEqual(self.gallery.title_label.textFormat(), Qt.TextFormat.PlainText)
        signed_in = GalleryPage(self.art, self.prefs, FakeAccounts("blink_queen"))
        self.assertEqual(signed_in.title_label.text(), "blink_queen’s gallery")  # the account name wins
        self.assertTrue(signed_in.name_row.isHidden())
        no_username = GalleryPage(self.art, self.prefs, FakeAccounts(""))
        self.assertEqual(no_username.title_label.text(), "<i>Mira</i>’s gallery")

    def test_sorting_and_long_titles(self):
        self.wallet.award("game:x:1", 2000, "eye_game")
        for artwork in self.art.catalogue[:3]:
            self.wallet.buy(artwork.id, artwork.price)
        self.art.reload()
        self.art.changed.emit()
        bought = [a.id for a in self.art.catalogue[:3]]
        self.assertEqual(self.gallery.ordered(), bought[::-1])  # newest first
        self.gallery.set_sort("title")
        titles = [self.art.by_id[i].title for i in self.gallery.ordered()]
        self.assertEqual(titles, sorted(titles, key=str.casefold))
        self.gallery.set_sort("artist")
        artists = [self.art.by_id[i].artist for i in self.gallery.ordered()]
        self.assertEqual(artists, sorted(artists, key=str.casefold))
        for card in self.gallery.grid.cards:
            self.assertTrue(card.title.wordWrap())  # long titles wrap instead of being cut off


if __name__ == "__main__":
    unittest.main()
