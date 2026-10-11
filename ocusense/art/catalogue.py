"""The Art shop's paintings: ocusense/assets/artworks/catalogue.json plus one JPEG each.

Every painting is a public-domain work whose image The Met released under CC0 through
its Open Access program; each entry records where it came from and its rights
statement (docs/art-shop.md). Artwork ids are stable ("met-<object id>") and are what
the collection database stores — never titles.

A missing or damaged image never breaks the shop: `image_path` is None and the
interface shows a clearly marked placeholder instead.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from ocusense.config import resource_path

FOLDER = resource_path(Path("ocusense") / "assets" / "artworks")
REQUIRED = ("id", "title", "artist", "date", "institution", "source_url", "rights", "license_url", "image", "price")


@dataclass(frozen=True)
class Artwork:
    id: str
    title: str
    full_title: str
    artist: str
    artist_bio: str
    date: str  # as the museum gives it, e.g. "1890–92" or "ca. 1662"
    medium: str
    dimensions: str
    institution: str
    accession_number: str
    credit_line: str
    source_url: str
    image_source_url: str
    rights: str
    license_url: str
    rights_checked: str
    image: str
    price: int  # game coins, not a real value
    image_path: Path | None  # None when the file is missing


class CatalogueError(Exception):
    pass


def load_catalogue(folder: Path = FOLDER) -> list[Artwork]:
    """The paintings, cheapest first. Raises CatalogueError if catalogue.json itself is unusable."""
    try:
        data = json.loads((folder / "catalogue.json").read_text(encoding="utf-8"))
        items = data["artworks"]
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise CatalogueError(f"The art catalogue couldn’t be read ({type(error).__name__}).") from error
    artworks, seen = [], set()
    for item in items:
        if not isinstance(item, dict) or any(not item.get(key) for key in REQUIRED):
            continue  # an incomplete entry is skipped, never shown half-done
        price = item["price"]
        if not isinstance(price, int) or isinstance(price, bool) or price <= 0 or item["id"] in seen:
            continue
        seen.add(item["id"])
        image = folder / item["image"]
        artworks.append(Artwork(
            id=item["id"], title=item["title"], full_title=item.get("full_title", item["title"]),
            artist=item["artist"], artist_bio=item.get("artist_bio", ""), date=item["date"],
            medium=item.get("medium", ""), dimensions=item.get("dimensions", ""),
            institution=item["institution"], accession_number=item.get("accession_number", ""),
            credit_line=item.get("credit_line", ""), source_url=item["source_url"],
            image_source_url=item.get("image_source_url", ""), rights=item["rights"],
            license_url=item["license_url"], rights_checked=item.get("rights_checked", ""),
            image=item["image"], price=price, image_path=image if image.is_file() else None))
    return sorted(artworks, key=lambda a: (a.price, a.title))
