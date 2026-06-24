"""
data/feed.py
The market-data boundary.

Strategies never call a broker or read a file directly — they go through a
DataFeed. That keeps strategies pure and testable, and lets you back the same
strategy with live ticks in production and canned candles in a backtest.

This module ships only:
  - DataFeed     : the abstract interface (Protocol-style ABC)
  - NullDataFeed : a do-nothing implementation so the engine runs out of the box

Bring your own feed by subclassing DataFeed and implementing the two methods.
A real implementation might wrap a broker SDK, a CSV directory, a database,
or a websocket cache — none of which belongs in the open engine.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Sequence


@dataclass
class Candle:
    """A single OHLCV bar."""
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class DataFeed(abc.ABC):
    """Implement this to plug real market data into the engine."""

    @abc.abstractmethod
    def last_price(self, symbol: str) -> Optional[float]:
        """Most recent traded price for `symbol`, or None if unknown."""
        raise NotImplementedError

    @abc.abstractmethod
    def candles(
        self,
        symbol: str,
        interval: str = "1d",
        lookback: int = 100,
    ) -> Sequence[Candle]:
        """
        Return up to `lookback` recent candles for `symbol` at `interval`
        ("1m", "5m", "1h", "1d", ...). Oldest first. Empty sequence if none.
        """
        raise NotImplementedError


class NullDataFeed(DataFeed):
    """
    A feed that knows nothing. Lets you run the engine, write strategies, and
    test the plumbing before any real data source exists. Every method returns
    an empty / None result.
    """

    def last_price(self, symbol: str) -> Optional[float]:
        return None

    def candles(self, symbol: str, interval: str = "1d",
                lookback: int = 100) -> Sequence[Candle]:
        return []
