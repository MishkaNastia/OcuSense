"""The coin wallet and the painting collection, in one small SQLite database.

    <OcuSense data folder>/collection.sqlite3        the real collection
    <OcuSense data folder>/collection-demo.sqlite3   developer demo wallet (--demo-wallet), kept apart
    OCUSENSE_COLLECTION_FILE                         overrides the real file (tests)

Two tables:
    ledger  every change of the balance, one row each: rewards (+), purchases (−) and,
            in the demo wallet only, demo coins. The balance is the sum, so it is always
            explainable. Each row has a unique event_id ("purchase:met-12127",
            "game:eye_game:<run id>"), so the same purchase or the same finished game
            can never be counted twice — even after a double click or a crash.
    owned   the paintings in the gallery, keyed by stable artwork id, each pointing
            at the ledger row that paid for it.

A purchase checks ownership and balance, writes the charge and the painting in one
transaction (BEGIN IMMEDIATE … COMMIT): either both are saved or neither is.
Nothing here is synchronised anywhere; the collection lives on this computer only.
"""

import os
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from ocusense.system import user_data_dir

SCHEMA_VERSION = 1
SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL CHECK (kind IN ('reward', 'purchase', 'demo')),
    amount INTEGER NOT NULL,
    source TEXT NOT NULL,
    artwork_id TEXT,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    day TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS owned (
    artwork_id TEXT PRIMARY KEY,
    acquired_at TEXT NOT NULL,
    price INTEGER NOT NULL,
    ledger_id INTEGER NOT NULL UNIQUE REFERENCES ledger (id)
);
"""
DEMO_START_COINS = 1000


class StoreError(Exception):
    """The collection couldn't be read or saved. Nothing was half-done."""


class NotEnoughCoins(Exception):
    def __init__(self, balance: int, price: int):
        super().__init__(f"{price - balance} more coins needed")
        self.balance, self.price = balance, price


class AlreadyOwned(Exception):
    pass


@dataclass(frozen=True)
class LedgerEntry:
    id: int
    event_id: str
    kind: str
    amount: int
    source: str
    artwork_id: str | None
    note: str
    created_at: str


@dataclass(frozen=True)
class Award:
    coins: int  # actually added (0 if a duplicate or the daily limit was reached)
    duplicate: bool = False
    limited: bool = False  # the daily limit cut it down or to nothing


def default_path(demo: bool = False) -> Path:
    if demo:
        return user_data_dir() / "collection-demo.sqlite3"
    override = os.environ.get("OCUSENSE_COLLECTION_FILE")
    return Path(override) if override else user_data_dir() / "collection.sqlite3"


class Wallet:
    def __init__(self, path: Path | None = None, demo: bool = False, now=datetime.now):
        self.demo = demo
        self.path = path or default_path(demo)
        self.now = now  # injectable clock (tests)
        self._prepare()

    # ------------------------------------------------------------ plumbing
    def _connect(self) -> sqlite3.Connection:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path, timeout=5, isolation_level=None)  # we BEGIN/COMMIT ourselves
            connection.execute("PRAGMA foreign_keys = ON")
            return connection
        except (sqlite3.Error, OSError) as error:
            raise StoreError("Your collection couldn’t be opened.") from error

    def _prepare(self) -> None:
        connection = self._connect()
        try:
            connection.executescript(SCHEMA)
            mode = "demo" if self.demo else "real"
            connection.execute("BEGIN IMMEDIATE")
            stored = dict(connection.execute("SELECT key, value FROM meta").fetchall())
            if stored.get("mode", mode) != mode:
                connection.execute("ROLLBACK")
                raise StoreError(f"{self.path.name} is a {stored['mode']} collection, not a {mode} one.")
            connection.execute("INSERT OR IGNORE INTO meta VALUES ('mode', ?)", (mode,))
            connection.execute("INSERT OR IGNORE INTO meta VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
            if self.demo:  # test coins, only ever in the separate demo file
                self._insert(connection, "demo:starting-coins", "demo", DEMO_START_COINS, "demo",
                             note="Developer demo coins (not real rewards)", ignore=True)
            connection.execute("COMMIT")
        except sqlite3.Error as error:
            raise StoreError("Your collection couldn’t be prepared.") from error
        finally:
            connection.close()

    def _insert(self, connection, event_id, kind, amount, source, artwork_id=None, note="", ignore=False) -> int | None:
        now = self.now()
        cursor = connection.execute(
            f"INSERT {'OR IGNORE ' if ignore else ''}INTO ledger "
            "(event_id, kind, amount, source, artwork_id, note, created_at, day) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (event_id, kind, amount, source, artwork_id, note, now.isoformat(timespec="seconds"),
             now.date().isoformat()))
        return cursor.lastrowid if cursor.rowcount else None

    @staticmethod
    def _balance(connection) -> int:
        return int(connection.execute("SELECT COALESCE(SUM(amount), 0) FROM ledger").fetchone()[0])

    def _read(self, query: str, args=()):
        connection = self._connect()
        try:
            return connection.execute(query, args).fetchall()
        except sqlite3.Error as error:
            raise StoreError("Your collection couldn’t be read.") from error
        finally:
            connection.close()

    # ------------------------------------------------------------ reading
    def balance(self) -> int:
        return int(self._read("SELECT COALESCE(SUM(amount), 0) FROM ledger")[0][0])

    def owned(self) -> dict[str, str]:
        """artwork id → when it was acquired (ISO time), oldest first."""
        return dict(self._read("SELECT artwork_id, acquired_at FROM owned ORDER BY acquired_at, ledger_id"))

    def earned_on(self, day: date, kind: str = "reward") -> int:
        rows = self._read("SELECT COALESCE(SUM(amount), 0) FROM ledger WHERE kind = ? AND day = ?",
                          (kind, day.isoformat()))
        return int(rows[0][0])

    def history(self) -> list[LedgerEntry]:
        rows = self._read("SELECT id, event_id, kind, amount, source, artwork_id, note, created_at "
                          "FROM ledger ORDER BY id")
        return [LedgerEntry(*row) for row in rows]

    # ------------------------------------------------------------ changing
    def award(self, event_id: str, coins: int, source: str, note: str = "", daily_limit: int | None = None) -> Award:
        """Add coins for one finished thing (a game round). The same event_id never pays twice.

        daily_limit caps all rewards earned today (checked inside the transaction).
        """
        if coins <= 0:
            return Award(0)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute("SELECT 1 FROM ledger WHERE event_id = ?", (event_id,)).fetchone():
                connection.execute("ROLLBACK")
                return Award(0, duplicate=True)
            limited = False
            if daily_limit is not None:
                today = connection.execute("SELECT COALESCE(SUM(amount), 0) FROM ledger WHERE kind = 'reward' "
                                           "AND day = ?", (self.now().date().isoformat(),)).fetchone()[0]
                allowed = max(0, daily_limit - int(today))
                limited = coins > allowed
                coins = min(coins, allowed)
            if coins <= 0:
                connection.execute("ROLLBACK")
                return Award(0, limited=True)
            self._insert(connection, event_id, "reward", coins, source, note=note)
            connection.execute("COMMIT")
            return Award(coins, limited=limited)
        except sqlite3.Error as error:
            _rollback(connection)
            raise StoreError("Your coins couldn’t be saved.") from error
        finally:
            connection.close()

    def buy(self, artwork_id: str, price: int) -> int:
        """Charge price and add the painting, together. Returns the new balance.

        Raises AlreadyOwned, NotEnoughCoins (nothing changes) or StoreError (nothing changes).
        """
        if price <= 0:
            raise ValueError("price must be positive")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")  # one writer at a time: no double charge, even from two windows
            if connection.execute("SELECT 1 FROM owned WHERE artwork_id = ?", (artwork_id,)).fetchone():
                connection.execute("ROLLBACK")
                raise AlreadyOwned(artwork_id)
            balance = self._balance(connection)
            if balance < price:
                connection.execute("ROLLBACK")
                raise NotEnoughCoins(balance, price)
            ledger_id = self._insert(connection, f"purchase:{artwork_id}", "purchase", -price, "art_shop",
                                     artwork_id=artwork_id)
            connection.execute("INSERT INTO owned (artwork_id, acquired_at, price, ledger_id) VALUES (?, ?, ?, ?)",
                               (artwork_id, self.now().isoformat(timespec="seconds"), price, ledger_id))
            connection.execute("COMMIT")
            return balance - price
        except sqlite3.IntegrityError as error:
            _rollback(connection)
            try:  # bought in another window a moment ago? Only then say so.
                owned = connection.execute("SELECT 1 FROM owned WHERE artwork_id = ?", (artwork_id,)).fetchone()
            except sqlite3.Error:
                owned = None
            if owned:
                raise AlreadyOwned(artwork_id) from error
            raise StoreError("The purchase couldn’t be saved, so no coins were taken.") from error
        except sqlite3.Error as error:
            _rollback(connection)
            raise StoreError("The purchase couldn’t be saved, so no coins were taken.") from error
        finally:
            connection.close()


def _rollback(connection) -> None:
    try:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
    except sqlite3.Error:
        pass
