# Gallery paintings: sources and rights

The Gallery (sidebar) is bought with garden coins. It holds two kinds of pictures.

## The supplied artwork

`painting_01` to `painting_05` are the supplied pictures from the garden feature.
Their display names describe the images; they are not authenticated titles.
**Their source and rights aren't recorded here.** They look very much like Joan Miró's
work, which is still under copyright, so check where they came from before the app is
shared publicly.

## Famous paintings by other artists

Eighteen oil paintings by eighteen artists, all from **The Metropolitan Museum of Art,
New York**.

- **Rights check:** each one was checked through The Met Collection API on the date
  shown. The API marks every one `isPublicDomain = true`, and The Met releases its
  Open Access images under **CC0 1.0**
  (https://creativecommons.org/publicdomain/zero/1.0/). CC0 doesn't require credit,
  but every card names the artist and links to the object page at The Met.
- **Images:** taken from each object's `primaryImage` and resized to 1000 px on the
  long side (JPEG). Nothing was generated or retouched; the gold frames are drawn by
  the app.
- **Dates:** the cards write the museum dates out in words, e.g. "1890 to 1892" for
  "1890–92".

| id | Title (museum) | Artist | Date (museum) | Medium | Price | Met object | Checked |
|---|---|---|---|---|---|---|---|
| `met_435868` | The Card Players | Paul Cézanne | 1890–92 | Oil on canvas | 60 | [61.101.1](https://www.metmuseum.org/art/collection/search/435868) | 2026-10-11 |
| `met_437926` | Mezzetin | Antoine Watteau | ca. 1718–20 | Oil on canvas | 70 | [34.138](https://www.metmuseum.org/art/collection/search/437926) | 2026-10-11 |
| `met_438817` | The Dance Class | Edgar Degas | 1874 | Oil on canvas | 80 | [1987.47.1](https://www.metmuseum.org/art/collection/search/438817) | 2026-10-11 |
| `met_437869` | Juan de Pareja (ca. 1608–1670) | Velázquez (Diego Rodríguez de Silva y Velázquez) | 1650 | Oil on canvas | 90 | [1971.86](https://www.metmuseum.org/art/collection/search/437869) | 2026-10-11 |
| `met_436965` | The Monet Family in Their Garden at Argenteuil | Edouard Manet | 1874 | Oil on canvas | 100 | [1976.201.14](https://www.metmuseum.org/art/collection/search/436965) | 2026-10-11 |
| `met_437903` | Marie Joséphine Charlotte du Val d'Ognes (1786–1868) | Marie Denise Villers | 1801 | Oil on canvas | 110 | [17.120.204](https://www.metmuseum.org/art/collection/search/437903) | 2026-10-11 |
| `met_436840` | Self-Portrait with Two Pupils, Marie Gabrielle Capet (1761–1818) and Marie Marguerite Carraux de Rosemond (1765–1788) | Adélaïde Labille-Guiard | 1785 | Oil on canvas | 120 | [53.225.5](https://www.metmuseum.org/art/collection/search/436840) | 2026-10-11 |
| `met_437310` | The Boulevard Montmartre on a Winter Morning | Camille Pissarro | 1897 | Oil on canvas | 130 | [60.174](https://www.metmuseum.org/art/collection/search/437310) | 2026-10-11 |
| `met_11417` | Washington Crossing the Delaware | Emanuel Leutze | 1851 | Oil on canvas | 140 | [97.34](https://www.metmuseum.org/art/collection/search/11417) | 2026-10-11 |
| `met_12127` | Madame X (Virginie Amélie Avegno Gautreau) | John Singer Sargent | 1883–84 | Oil on canvas | 150 | [16.53](https://www.metmuseum.org/art/collection/search/12127) | 2026-10-11 |
| `met_438821` | Ia Orana Maria (Hail Mary) | Paul Gauguin | 1891 | Oil on canvas | 160 | [51.112.2](https://www.metmuseum.org/art/collection/search/438821) | 2026-10-11 |
| `met_435702` | The Horse Fair | Rosa Bonheur | 1852–55 | Oil on canvas | 170 | [87.25](https://www.metmuseum.org/art/collection/search/435702) | 2026-10-11 |
| `met_437881` | Young Woman with a Water Pitcher | Johannes Vermeer | ca. 1662 | Oil on canvas | 180 | [89.15.21](https://www.metmuseum.org/art/collection/search/437881) | 2026-10-11 |
| `met_435809` | The Harvesters | Pieter Bruegel the Elder | 1565 | Oil on oak | 200 | [19.164](https://www.metmuseum.org/art/collection/search/435809) | 2026-10-11 |
| `met_10481` | Heart of the Andes | Frederic Edwin Church | 1859 | Oil on canvas | 210 | [09.95](https://www.metmuseum.org/art/collection/search/10481) | 2026-10-11 |
| `met_437394` | Aristotle with a Bust of Homer | Rembrandt (Rembrandt van Rijn) | 1653 | Oil on canvas | 220 | [61.198](https://www.metmuseum.org/art/collection/search/437394) | 2026-10-11 |
| `met_436105` | The Death of Socrates | Jacques Louis David | 1787 | Oil on canvas | 230 | [31.45](https://www.metmuseum.org/art/collection/search/436105) | 2026-10-11 |
| `met_436535` | Wheat Field with Cypresses | Vincent van Gogh | 1889 | Oil on canvas | 250 | [1993.132](https://www.metmuseum.org/art/collection/search/436535) | 2026-10-11 |

**Left out:**
- Monet's *Bouquet of Sunflowers* and *Haystacks*, and his *Garden at
  Sainte-Adresse*: The Met doesn't mark them public domain.
- Courbet's *The Woman in the Waves*: a nude.
- *The Great Wave*: a print, not a painting.

**Adding a painting:**
1. Check its rights record yourself.
2. Add the resized image to `ocusense/assets/paintings/`.
3. Add an entry to `ocusense/core/library.py` with its artist, year and source link.

`tests/test_library.py` checks every museum entry has these.
