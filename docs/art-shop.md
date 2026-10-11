# Art shop and Your gallery

The desktop app has two pages in the sidebar, **Art shop** and **Your gallery**. You
earn coins by finishing game rounds, spend them on famous paintings, and the paintings
hang in your own gallery. Coins are game rewards only: there is no real money, no
checkout, and no paid currency.

## Trying it

- **Real collection:** play a game round to the end in **Games**:
  - a 90-second Blink Code **challenge** with at least one word spelled, or
  - an EyeGame run of at least 50 points.

  The game shows "+N coins for the Art shop". Open **Art shop**, choose a painting,
  press **Buy**, confirm, then **View in gallery**.
- **Developer demo wallet:** start the app with `--demo-wallet`:
  - `python -m ocusense --demo-wallet`, or
  - `OCUSENSE_DEMO_WALLET=1 python -m ocusense`.

  It uses a *separate* file, `collection-demo.sqlite3`, starts with 1000 test coins, and
  both pages show a red **DEMO WALLET · test coins** tag. Nothing bought there appears in
  the real gallery, and real coins never appear in the demo.

## Earning coins (product settings: `ocusense/art/rewards.py`)

| Game | When it pays | Coins |
|---|---|---|
| Blink Code | a finished 90-second challenge with ≥ 1 word | 10 + 1 per 25 points, max 40 |
| EyeGame | a finished run with ≥ 50 points | 5 + 1 per 40 points, max 30 |
| All games | daily limit | 150 coins a day |

- **Once per round:** every finished round has its own id, and the wallet refuses a
  second payment for the same id. A double timer tick or a repeated "game over"
  can't pay twice.
- **Never paid:** camera use, blinking more, reporting symptoms or skipping breaks
  earn nothing. Keyboard play earns the same as eye play, and practice modes earn
  nothing.
- **Daily limit:** this keeps the shop from becoming a reason to stay at the screen.
  A few short breaks a day are enough, and playing longer earns no more.

Change these numbers in `rewards.py`, which is the one place they live.

## How it is stored (`ocusense/art/wallet.py`)

One small SQLite database in the OcuSense data folder:
- macOS: `~/Library/Application Support/OcuSense/collection.sqlite3`
- Windows: `%LOCALAPPDATA%\OcuSense\collection.sqlite3`

| Table | What it holds |
|---|---|
| `ledger` | every balance change, one row each: rewards (+), purchases (−), demo coins (demo file only). The balance is the sum, so it can always be explained. `event_id` is unique: `purchase:<artwork id>`, `game:eye_game:<run id>`, … |
| `owned` | paintings in the gallery, by stable artwork id (`met-<object id>`), each pointing at the ledger row that paid for it |
| `meta` | `mode` (real / demo) and schema version. A demo file can never be opened as the real collection. |

- **Purchases are atomic.** One `BEGIN IMMEDIATE … COMMIT` transaction checks
  ownership and balance, writes the charge and adds the painting. Either both happen
  or neither does, even with two windows open. Errors are shown as messages ("The
  purchase couldn't be saved, so no coins were taken").
- **Display names don't touch the collection.** The gallery name comes from the
  signed-in account's username, otherwise from an optional local name
  (`display_name` in `preferences.json`), otherwise it reads "Your gallery". Names are
  always shown as plain text. Changing the name never changes the collection.
- **No syncing.** There is no cloud sync and no cross-device ownership: the
  collection lives on one computer. Replacing or rebuilding the app keeps it, because
  it is outside the app folder.

## The paintings and their rights

All ten are **paintings** (oil on canvas or wood) from **The Metropolitan Museum of
Art, New York**. Each one was checked individually on 2026-10-11
through The Met Collection API (`isPublicDomain = true`).
- **Image licence:** The Met's API documentation says it gives access to images
  "that are in the public domain" through its Open Access program. The Met releases
  Open Access images under **Creative Commons Zero (CC0 1.0)**:
  https://creativecommons.org/publicdomain/zero/1.0/
- **Attribution:** CC0 doesn't require it, but the app gives it anyway: each detail
  view shows the institution, accession number, credit line, a link to the object page
  and the rights statement.
- **Images:** downloaded from the `primaryImage` URL the API gives for each object,
  then resized to 1000 px on the long side (JPEG, about 2 MB for all ten). No search
  engine thumbnails were used, and nothing was generated or retouched.

| id | Title | Artist | Date (museum) | Price | Met object | Checked |
|---|---|---|---|---|---|---|
| `met-437869` | Juan de Pareja | Diego Velázquez | 1650 | 100 | [1971.86](https://www.metmuseum.org/art/collection/search/437869) | 2026-10-11 |
| `met-435868` | The Card Players | Paul Cézanne | 1890–92 | 100 | [61.101.1](https://www.metmuseum.org/art/collection/search/435868) | 2026-10-11 |
| `met-438817` | The Dance Class | Edgar Degas | 1874 | 100 | [1987.47.1](https://www.metmuseum.org/art/collection/search/438817) | 2026-10-11 |
| `met-12127` | Madame X | John Singer Sargent | 1883–84 | 200 | [16.53](https://www.metmuseum.org/art/collection/search/12127) | 2026-10-11 |
| `met-11417` | Washington Crossing the Delaware | Emanuel Leutze | 1851 | 200 | [97.34](https://www.metmuseum.org/art/collection/search/11417) | 2026-10-11 |
| `met-435809` | The Harvesters | Pieter Bruegel the Elder | 1565 | 350 | [19.164](https://www.metmuseum.org/art/collection/search/435809) | 2026-10-11 |
| `met-437881` | Young Woman with a Water Pitcher | Johannes Vermeer | ca. 1662 | 350 | [89.15.21](https://www.metmuseum.org/art/collection/search/437881) | 2026-10-11 |
| `met-437394` | Aristotle with a Bust of Homer | Rembrandt van Rijn | 1653 | 500 | [61.198](https://www.metmuseum.org/art/collection/search/437394) | 2026-10-11 |
| `met-436105` | The Death of Socrates | Jacques Louis David | 1787 | 500 | [31.45](https://www.metmuseum.org/art/collection/search/436105) | 2026-10-11 |
| `met-436535` | Wheat Field with Cypresses | Vincent van Gogh | 1889 | 500 | [1993.132](https://www.metmuseum.org/art/collection/search/436535) | 2026-10-11 |

Full records, including the full title, artist dates, medium, dimensions, credit line,
image URL and rights text, are in `ocusense/assets/artworks/catalogue.json`.

**Considered but not used:**
- *American Gothic* (Grant Wood), *Nighthawks* (Edward Hopper) and Delvaux's *The
  Awakening of the Forest*: the Art Institute of Chicago marks them **not** public
  domain.
- *Bridge over a Pond of Water Lilies* (Monet): the Met marks it not public domain.
- *Garden at Sainte-Adresse* (Monet): the Met marks it not public domain and gives no
  image.
- Four Art Institute of Chicago paintings that **are** public domain: their image
  server blocked automated downloads (HTTP 403), and that protection wasn't bypassed.
- *The Great Wave* (Hokusai): CC0, but a woodblock print rather than a painting.
- **No Miró paintings:** they are still under copyright. The app's Miró-inspired look
  is our own drawing, and no Miró work is bundled.

**Adding a painting:**
1. Check its rights record yourself.
2. Add an entry with every field to `catalogue.json` and the resized JPEG next to it.
3. `tests/test_art.py` checks that every entry has its source, rights, licence and
   image.

A missing image is shown as a clearly marked "Image unavailable (placeholder)" frame,
never as a substitute.
