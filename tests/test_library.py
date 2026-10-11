import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from ocusense.core.garden import Garden
from ocusense.core.library import PAINTINGS
from ocusense.garden_store import GardenStore


class LibraryTest(unittest.TestCase):
    def test_every_painting_has_its_picture(self):
        from ocusense.config import resource_path
        for key, painting in PAINTINGS.items():
            with self.subTest(key=key):
                self.assertTrue(resource_path('ocusense/assets/paintings/' + painting.filename).exists())

    def test_retired_paintings_are_refunded_and_taken_down(self):
        data = Garden(coins=10).to_dict()
        data['paintings'] = ['painting_01', 'painting_07', 'painting_12']
        data['painting_slots'] = {'sidebar:0': 'painting_07', 'sidebar:1': 'painting_01'}
        g = Garden.from_dict(data)
        self.assertEqual(g.paintings, ['painting_01'])
        self.assertEqual(g.painting_slots, {'sidebar:1': 'painting_01'})
        self.assertEqual(g.coins, 10 + 85 + 135)

    def test_purchase_and_placement(self):
        g = Garden(coins=100)
        self.assertFalse(g.place_painting('painting_01', 'sidebar:0'))
        self.assertTrue(g.buy_painting('painting_01'))
        self.assertEqual(g.coins, 75)
        self.assertFalse(g.buy_painting('painting_01'))
        self.assertFalse(g.buy_painting('painting_05'))  # 135 coins: not enough
        self.assertTrue(g.place_painting('painting_01', 'sidebar:0'))
        self.assertTrue(g.place_painting('painting_01', 'sidebar:1'))
        self.assertEqual(g.painting_slots, {'sidebar:1': 'painting_01'})
        self.assertTrue(g.buy_painting('painting_02'))
        g.place_painting('painting_02', 'sidebar:1')
        self.assertIn('painting_01', g.paintings)
        self.assertEqual(g.painting_slots, {'sidebar:1': 'painting_02'})
        self.assertFalse(g.place_painting('painting_02', 'invalid'))
        g.place_painting('painting_02', None)
        self.assertEqual(g.painting_slots, {})

    def test_save_reload_migration_and_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'garden.json'
            store = GardenStore(path)
            store.garden.coins = 100
            self.assertTrue(store.change(lambda g: g.buy_painting('painting_01')))
            self.assertTrue(store.change(lambda g: g.place_painting('painting_01', 'sidebar:1')))
            restored = GardenStore(path).garden
            self.assertEqual(restored.coins, 75)
            self.assertEqual(restored.painting_slots, {'sidebar:1': 'painting_01'})
            with patch.object(Path, 'write_text', side_effect=OSError('disk full')):
                self.assertFalse(store.change(lambda g: g.buy_painting('painting_02')))
            self.assertEqual(store.garden.coins, 75)
            self.assertNotIn('painting_02', store.garden.paintings)
        old = Garden().to_dict()
        del old['paintings'], old['painting_slots']
        self.assertEqual(Garden.from_dict(old).paintings, [])
        old['painting_slots'] = {'sidebar:0': 'painting_01'}
        with self.assertRaises(ValueError):
            Garden.from_dict(old)

    def test_page_purchase_and_assets(self):
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QPixmap
        from ocusense.config import resource_path
        from ocusense.ui.library_page import LibraryPage
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp:
            store = GardenStore(Path(tmp) / 'garden.json')
            page = LibraryPage(store)
            self.assertTrue(page.cards['painting_01'][1].isEnabled())
            self.assertFalse(page.cards['painting_02'][1].isEnabled())
            store.garden.coins = 100
            page.refresh()
            page.cards['painting_01'][1].click()
            page.place('painting_01', 'sidebar:1')
            self.assertEqual(store.garden.coins, 75)
            self.assertEqual(store.garden.painting_slots, {'sidebar:1': 'painting_01'})
            for painting in PAINTINGS.values():
                self.assertFalse(QPixmap(str(resource_path('ocusense/assets/paintings/' + painting.filename))).isNull())
            page.close()


class MuseumPaintingsTest(unittest.TestCase):
    def test_many_artists_each_with_source_and_no_retired_ids(self):
        from ocusense.config import resource_path
        from ocusense.core.library import RETIRED
        museum = {k: p for k, p in PAINTINGS.items() if p.artist}
        self.assertGreaterEqual(len(museum), 12)
        self.assertEqual(len({p.artist for p in museum.values()}), len(museum))  # all different painters
        for key, p in museum.items():
            self.assertTrue(key.startswith("met_"), key)
            self.assertNotIn(key, RETIRED)  # retired ids are refunded, never reused
            self.assertTrue(p.source_url.startswith("https://www.metmuseum.org/art/collection/search/"), key)
            self.assertTrue(p.year and p.price > 0, key)
            self.assertNotIn("–", p.year)  # dates written out, no dashes
            self.assertTrue(resource_path('ocusense/assets/paintings/' + p.filename).exists(), key)
        self.assertIn("painting_01", PAINTINGS)  # the supplied pictures are still there
