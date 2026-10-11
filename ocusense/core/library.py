"""Painting catalogue.

The first five are the supplied artwork: their display names describe them, they are
not authenticated titles. The others are public domain paintings by different artists,
with images from The Met's Open Access program (CC0); each links to its museum page.
Sources and rights: docs/gallery-paintings.md.
"""
from dataclasses import dataclass

MET_RIGHTS = "Public domain. Image: The Metropolitan Museum of Art, Open Access (CC0)."


@dataclass(frozen=True)
class Painting:
    name: str
    price: int
    filename: str
    artist: str = ""  # empty for the supplied artwork
    year: str = ""
    source_url: str = ""

PAINTINGS = {
    'painting_01': Painting('Green Crescent', 25, 'gallery_01.png'),
    'painting_02': Painting('Red Sun on Blue', 45, 'gallery_02.png'),
    'painting_03': Painting('Green Arc', 70, 'gallery_03.png'),
    'painting_04': Painting('Constellation of Eyes', 100, 'gallery_04.png'),
    'painting_05': Painting('Birds in Gold', 135, 'gallery_05.png'),
    # Famous paintings by other artists (public domain, The Met Open Access)
    'met_435868': Painting('The Card Players', 60, 'met_435868.jpg', 'Paul Cézanne', '1890 to 1892',
                         'https://www.metmuseum.org/art/collection/search/435868'),
    'met_437926': Painting('Mezzetin', 70, 'met_437926.jpg', 'Antoine Watteau', 'about 1718 to 1720',
                         'https://www.metmuseum.org/art/collection/search/437926'),
    'met_438817': Painting('The Dance Class', 80, 'met_438817.jpg', 'Edgar Degas', '1874',
                         'https://www.metmuseum.org/art/collection/search/438817'),
    'met_437869': Painting('Juan de Pareja', 90, 'met_437869.jpg', 'Diego Velázquez', '1650',
                         'https://www.metmuseum.org/art/collection/search/437869'),
    'met_436965': Painting('The Monet Family in Their Garden at Argenteuil', 100, 'met_436965.jpg', 'Édouard Manet', '1874',
                         'https://www.metmuseum.org/art/collection/search/436965'),
    'met_437903': Painting('Charlotte du Val d’Ognes', 110, 'met_437903.jpg', 'Marie Denise Villers', '1801',
                         'https://www.metmuseum.org/art/collection/search/437903'),
    'met_436840': Painting('Self-Portrait with Two Pupils', 120, 'met_436840.jpg', 'Adélaïde Labille-Guiard', '1785',
                         'https://www.metmuseum.org/art/collection/search/436840'),
    'met_437310': Painting('The Boulevard Montmartre on a Winter Morning', 130, 'met_437310.jpg', 'Camille Pissarro', '1897',
                         'https://www.metmuseum.org/art/collection/search/437310'),
    'met_11417': Painting('Washington Crossing the Delaware', 140, 'met_11417.jpg', 'Emanuel Leutze', '1851',
                         'https://www.metmuseum.org/art/collection/search/11417'),
    'met_12127': Painting('Madame X', 150, 'met_12127.jpg', 'John Singer Sargent', '1883 to 1884',
                         'https://www.metmuseum.org/art/collection/search/12127'),
    'met_438821': Painting('Ia Orana Maria (Hail Mary)', 160, 'met_438821.jpg', 'Paul Gauguin', '1891',
                         'https://www.metmuseum.org/art/collection/search/438821'),
    'met_435702': Painting('The Horse Fair', 170, 'met_435702.jpg', 'Rosa Bonheur', '1852 to 1855',
                         'https://www.metmuseum.org/art/collection/search/435702'),
    'met_437881': Painting('Young Woman with a Water Pitcher', 180, 'met_437881.jpg', 'Johannes Vermeer', 'about 1662',
                         'https://www.metmuseum.org/art/collection/search/437881'),
    'met_435809': Painting('The Harvesters', 200, 'met_435809.jpg', 'Pieter Bruegel the Elder', '1565',
                         'https://www.metmuseum.org/art/collection/search/435809'),
    'met_10481': Painting('Heart of the Andes', 210, 'met_10481.jpg', 'Frederic Edwin Church', '1859',
                         'https://www.metmuseum.org/art/collection/search/10481'),
    'met_437394': Painting('Aristotle with a Bust of Homer', 220, 'met_437394.jpg', 'Rembrandt', '1653',
                         'https://www.metmuseum.org/art/collection/search/437394'),
    'met_436105': Painting('The Death of Socrates', 230, 'met_436105.jpg', 'Jacques Louis David', '1787',
                         'https://www.metmuseum.org/art/collection/search/436105'),
    'met_436535': Painting('Wheat Field with Cypresses', 250, 'met_436535.jpg', 'Vincent van Gogh', '1889',
                         'https://www.metmuseum.org/art/collection/search/436535'),
}
# Paintings from the earlier, larger catalogue: anyone who bought one gets its price back
# (ocusense/core/garden.py, when the garden is read), so no coins are lost.
RETIRED = {'painting_06': 75, 'painting_07': 85, 'painting_08': 95, 'painting_09': 105,
           'painting_10': 115, 'painting_11': 125, 'painting_12': 135}
SLOTS = ('sidebar:0', 'sidebar:1')
SLOT_LABELS = ('Sidebar · upper left', 'Sidebar · lower right')
LEGACY_SLOTS = tuple(f'{page}:{position}' for page in ('library', 'study', 'pomodoro') for position in range(3))
