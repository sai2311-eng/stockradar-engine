"""
engine/context.py
The read-only snapshot of the world handed to a strategy on each run.

The engine ships a stub MarketContext backed by a pluggable DataFeed
(see data/feed.py). Strategies only ever READ from the context — they never
fetch data themselves, which keeps them testable and broker-agnostic.

Wire a real feed (your broker SDK, a CSV, a database) by passing any object
that implements the DataFeed protocol to MarketContext.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from data.feed import DataFeed, NullDataFeed


@dataclass
class MarketContext:
    """
    Everything a strategy is allowed to see for a single evaluation.

    Parameters
    ----------
    feed : DataFeed
        Source of market data. Defaults to NullDataFeed (returns nothing),
        so the engine runs end-to-end before you have any data wired.
    now : datetime
        Evaluation time (UTC). Defaults to wall-clock; override in backtests.
    universe : list[str]
        Symbols the strategies should consider this run.
    extras : dict
        Anything else the host app wants to expose (config, regime flags, ...).
    """
    feed: DataFeed = None  # type: ignore[assignment]
    now: datetime = None   # type: ignore[assignment]
    universe: list[str] = None  # type: ignore[assignment]
    extras: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.feed is None:
            self.feed = NullDataFeed()
        if self.now is None:
            self.now = datetime.now(timezone.utc)
        if self.universe is None:
            self.universe = []
        if self.extras is None:
            self.extras = {}

    # ── convenience pass-throughs to the feed ────────────────────────────
    def last_price(self, symbol: str) -> Optional[float]:
        return self.feed.last_price(symbol)

    def candles(self, symbol: str, interval: str = "1d", lookback: int = 100):
        return self.feed.candles(symbol, interval=interval, lookback=lookback)

    def get(self, key: str, default: Any = None) -> Any:
        return self.extras.get(key, default)
