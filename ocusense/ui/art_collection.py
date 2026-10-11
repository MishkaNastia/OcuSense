"""The one place the window talks to for coins and paintings (Art shop, Your gallery, game rewards).

It wraps the catalogue (ocusense/art/catalogue.py) and the wallet database
(ocusense/art/wallet.py), and emits `changed` after every purchase or reward so both
pages show the new balance and ownership right away. Problems with storage are
reported as messages, never as crashes; when the database can't be opened at all,
the shop still shows the paintings but nothing can be bought or earned.

demo=True (the --demo-wallet option or OCUSENSE_DEMO_WALLET=1) uses a separate
database with 1000 test coins, for trying purchases. It never touches the real
collection, and both pages say clearly that it is a demo.
"""

from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal

from ocusense.art import rewards
from ocusense.art.catalogue import Artwork, CatalogueError, load_catalogue
from ocusense.art.wallet import AlreadyOwned, Award, NotEnoughCoins, StoreError, Wallet


@dataclass(frozen=True)
class PurchaseResult:
    ok: bool
    message: str
    balance: int | None = None


class ArtCollection(QObject):
    changed = Signal()

    def __init__(self, demo: bool = False, wallet: Wallet | None = None, catalogue: list[Artwork] | None = None,
                 parent=None):
        super().__init__(parent)
        self.demo = demo
        self.problem = ""  # shown on both pages when something is wrong
        if catalogue is None:
            try:
                catalogue = load_catalogue()
            except CatalogueError as error:
                catalogue, self.problem = [], str(error)
        self.catalogue = catalogue
        self.by_id = {a.id: a for a in catalogue}
        if wallet is None:
            try:
                wallet = Wallet(demo=demo)
            except StoreError as error:
                wallet, self.problem = None, f"{error} Purchases and coins are unavailable for now."
        self.wallet = wallet
        self._balance = 0
        self._owned: dict[str, str] = {}
        self.reload()

    @property
    def available(self) -> bool:
        return self.wallet is not None

    # ------------------------------------------------------------ reading
    def reload(self) -> None:
        if self.wallet is None:
            return
        try:
            self._balance = self.wallet.balance()
            self._owned = self.wallet.owned()
        except StoreError as error:
            self.problem = str(error)

    def balance(self) -> int:
        return self._balance

    def owned(self) -> dict[str, str]:
        """artwork id → acquired time, oldest first; only ids that are still in the catalogue."""
        return {k: v for k, v in self._owned.items() if k in self.by_id}

    def is_owned(self, artwork_id: str) -> bool:
        return artwork_id in self._owned

    # ------------------------------------------------------------ changing
    def buy(self, artwork: Artwork) -> PurchaseResult:
        if self.wallet is None:
            return PurchaseResult(False, self.problem or "Purchases are unavailable right now.")
        try:
            balance = self.wallet.buy(artwork.id, artwork.price)
        except AlreadyOwned:
            result = PurchaseResult(False, "This painting is already in your gallery.")
        except NotEnoughCoins as error:
            result = PurchaseResult(False, f"You need {error.price - error.balance} more coins for this painting.",
                                    error.balance)
        except StoreError as error:
            result = PurchaseResult(False, str(error))
        else:
            result = PurchaseResult(True, "Added to your gallery", balance)
        self.reload()
        self.changed.emit()
        return result

    def award_game(self, event_id: str, source: str, coins: int, note: str = "") -> Award | None:
        """Coins for one finished game round (see ocusense/art/rewards.py). None if storage failed."""
        if self.wallet is None or coins <= 0:
            return None
        try:
            award = self.wallet.award(event_id, coins, source, note, daily_limit=rewards.DAILY_GAME_COIN_LIMIT)
        except StoreError:
            return None
        self.reload()
        self.changed.emit()
        return award


def award_text(award: Award | None) -> str:
    """A short line for the games: "+18 coins for the Art shop" or why nothing was added."""
    if award is None:
        return ""
    if award.coins > 0:
        extra = " (today’s coin limit reached)" if award.limited else ""
        return f"+{award.coins} coins for the Art shop{extra}"
    if award.limited:
        return f"Today’s {rewards.DAILY_GAME_COIN_LIMIT} coins are collected — more tomorrow."
    return ""
