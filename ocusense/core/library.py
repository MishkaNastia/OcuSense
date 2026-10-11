"""Painting catalogue. Display names describe the supplied artwork, not authenticated titles."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Painting:
    name: str
    price: int
    filename: str

PAINTINGS = {
    'painting_01': Painting('Green Crescent', 25, 'gallery_01.png'),
    'painting_02': Painting('Red Sun on Blue', 45, 'gallery_02.png'),
    'painting_03': Painting('Green Arc', 70, 'gallery_03.png'),
    'painting_04': Painting('Constellation of Eyes', 100, 'gallery_04.png'),
    'painting_05': Painting('Birds in Gold', 135, 'gallery_05.png'),
}
# Paintings from the earlier, larger catalogue: anyone who bought one gets its price back
# (ocusense/core/garden.py, when the garden is read), so no coins are lost.
RETIRED = {'painting_06': 75, 'painting_07': 85, 'painting_08': 95, 'painting_09': 105,
           'painting_10': 115, 'painting_11': 125, 'painting_12': 135}
SLOTS = ('sidebar:0', 'sidebar:1')
SLOT_LABELS = ('Sidebar · upper left', 'Sidebar · lower right')
LEGACY_SLOTS = tuple(f'{page}:{position}' for page in ('library', 'study', 'pomodoro') for position in range(3))
