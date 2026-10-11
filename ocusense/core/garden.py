"""Garden economy and absolute growth deadlines; no camera or UI dependencies."""
from dataclasses import dataclass, field
import math
from .library import PAINTINGS, RETIRED, SLOTS, LEGACY_SLOTS


@dataclass(frozen=True)
class Plant:
    name: str
    seconds: int
    reward: int
    seed_price: int
    color: str


PLANTS = {
    'strawberry': Plant('Strawberries', 7200, 25, 3, '#D2381F'),
    'carrot': Plant('Carrots', 180, 10, 2, '#E77B26'),
    'tomato': Plant('Tomatoes', 300, 35, 4, '#D2381F'),
    'lettuce': Plant('Lettuce', 2700, 8, 1, '#2E7A4D'),
    'blueberry': Plant('Blueberries', 14400, 50, 5, '#1F43B8'),
    'pumpkin': Plant('Pumpkins', 21600, 80, 8, '#E77B26'),
}
SHOP = {'flowers': ('Wildflower border', 20), 'can': ('Cobalt watering can', 30),
        'mobile': ('Constellation mobile', 40), 'plot': ('Extra garden bed', 60)}


@dataclass
class Plot:
    plant: str | None = None
    watered_at: float | None = None
    ready_at: float | None = None
    exercising: bool = False  # transient; never restored after restart

    def state(self, now):
        if self.plant is None:
            return 'EMPTY'
        if self.ready_at is not None:
            return 'READY_TO_HARVEST' if now >= self.ready_at else 'GROWING'
        return 'EXERCISING' if self.exercising else 'NEEDS_WATER'

    def growth(self, now):
        if self.ready_at is None or self.watered_at is None:
            return 0.0
        return max(0.0, min(1.0, (now - self.watered_at) / (self.ready_at - self.watered_at)))


@dataclass
class Garden:
    coins: int = 25  # welcome balance for a new local save
    plots: list = field(default_factory=lambda: [Plot(key) for key in PLANTS])
    seeds: dict = field(default_factory=lambda: {key: 1 for key in PLANTS})
    decorations: list = field(default_factory=list)
    reminders: bool = False
    reminder_minutes: int = 20

    paintings: list = field(default_factory=list)
    painting_slots: dict = field(default_factory=dict)

    def buy_painting(self, key):
        if key not in PAINTINGS or key in self.paintings or self.coins < PAINTINGS[key].price:
            return False
        self.coins -= PAINTINGS[key].price
        self.paintings.append(key)
        return True

    def place_painting(self, key, slot):
        if key not in self.paintings or (slot is not None and slot not in SLOTS):
            return False
        self.painting_slots = {s: k for s, k in self.painting_slots.items() if k != key}
        if slot is not None:
            self.painting_slots[slot] = key
        return True

    def plant(self, index, key):
        plot = self.plots[index]
        if plot.plant is not None or key not in PLANTS or self.seeds.get(key, 0) < 1:
            return False
        self.seeds[key] -= 1
        self.plots[index] = Plot(key)
        return True

    def begin(self, index, now):
        if self.plots[index].state(now) != 'NEEDS_WATER':
            return False
        self.plots[index].exercising = True
        return True

    def cancel(self, index):
        self.plots[index].exercising = False

    def water(self, index, now):
        plot = self.plots[index]
        if not plot.exercising or plot.ready_at is not None:
            return False
        plot.exercising = False
        plot.watered_at = now
        plot.ready_at = now + PLANTS[plot.plant].seconds
        return True

    def harvest(self, index, now):
        plot = self.plots[index]
        if plot.state(now) != 'READY_TO_HARVEST':
            return 0
        reward = PLANTS[plot.plant].reward
        self.coins += reward
        self.plots[index] = Plot()
        return reward

    def buy(self, item):
        if item in PLANTS:
            cost = PLANTS[item].seed_price
        elif item in SHOP:
            if (item == 'plot' and len(self.plots) >= 9) or item in self.decorations:
                return False
            cost = SHOP[item][1]
        else:
            return False
        if self.coins < cost:
            return False
        self.coins -= cost
        if item in PLANTS:
            self.seeds[item] = self.seeds.get(item, 0) + 1
        elif item == 'plot':
            self.plots.append(Plot())
        else:
            self.decorations.append(item)
        return True

    def to_dict(self):
        return dict(version=1, paintings=self.paintings, painting_slots=self.painting_slots, coins=self.coins, seeds=self.seeds, decorations=self.decorations,
                    reminders=self.reminders, reminder_minutes=self.reminder_minutes,
                    plots=[dict(plant=p.plant, watered_at=p.watered_at, ready_at=p.ready_at) for p in self.plots])

    @classmethod
    def from_dict(cls, data):
        def integer(value):
            return type(value) is int and value >= 0
        if not isinstance(data, dict) or data.get('version') != 1:
            raise ValueError('Unknown garden format')
        if not integer(data.get('coins')) or not isinstance(data.get('seeds'), dict):
            raise ValueError('Invalid coins or seeds')
        seeds = {key: data['seeds'].get(key, 0) for key in PLANTS}
        if not all(integer(n) for n in seeds.values()):
            raise ValueError('Invalid seeds')
        raw = data.get('plots')
        if not isinstance(raw, list) or not 6 <= len(raw) <= 9:
            raise ValueError('Invalid plots')
        plots = []
        for item in raw:
            if not isinstance(item, dict):
                raise ValueError('Invalid plot')
            key, start, end = item.get('plant'), item.get('watered_at'), item.get('ready_at')
            if key is not None and key not in PLANTS:
                raise ValueError('Unknown plant')
            if start is not None or end is not None:
                if key is None or not all(type(v) in (int, float) and math.isfinite(v) and v >= 0 for v in (start, end)) or end <= start:
                    raise ValueError('Invalid growth time')
            # Upgrade carrots watered under the original one-hour rule.
            if key == 'carrot' and start is not None and end - start == 3600:
                end = start + PLANTS['carrot'].seconds
            # Upgrade tomatoes watered under the original three-hour rule.
            if key == 'tomato' and start is not None and end - start == 10800:
                end = start + PLANTS['tomato'].seconds
            plots.append(Plot(key, start, end))
        decorations = data.get('decorations', [])
        if not isinstance(decorations, list) or any(x not in ('flowers', 'can', 'mobile') for x in decorations):
            raise ValueError('Invalid decorations')
        minutes = data.get('reminder_minutes', 20)
        if type(minutes) is not int or not 5 <= minutes <= 120:
            raise ValueError('Invalid reminder interval')
        paintings = data.get('paintings', [])
        slots = data.get('painting_slots', {})
        refund = 0
        if isinstance(paintings, list) and isinstance(slots, dict):  # retired paintings: price back, taken down
            refund = sum(RETIRED[k] for k in set(paintings) if isinstance(k, str) and k in RETIRED)
            paintings = [k for k in paintings if k not in RETIRED]
            slots = {s: k for s, k in slots.items() if k not in RETIRED}
        if (not isinstance(paintings, list) or any(not isinstance(k, str) or k not in PAINTINGS for k in paintings)
                or len(set(paintings)) != len(paintings)):
            raise ValueError('Invalid painting collection')
        if (not isinstance(slots, dict) or any(s not in SLOTS + LEGACY_SLOTS or k not in paintings for s, k in slots.items())
                or len(set(slots.values())) != len(slots)):
            raise ValueError('Invalid painting placement')
        # Keep at most two old decorations on the new sidebar; all purchases remain owned.
        if any(s in LEGACY_SLOTS for s in slots):
            keys = list(dict.fromkeys(slots.values()))[:2]
            slots = dict(zip(SLOTS, keys))
        return cls(data['coins'] + refund, plots, seeds, list(set(decorations)), data.get('reminders') is True, minutes,
                   list(paintings), dict(slots))
