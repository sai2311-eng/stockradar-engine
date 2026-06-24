"""
engine/strategy.py
The one interface every strategy implements.

A strategy is a small, self-contained unit that looks at a MarketContext and
returns zero or more Signals. It owns its own logic and parameters; the engine
owns scheduling, discovery, and dispatch.

Minimal example
---------------
    from engine import BaseStrategy, Signal, Side, register

    @register
    class MyStrategy(BaseStrategy):
        name = "my_strategy"
        interval = "5m"          # how often the runner should call it

        def generate(self, ctx):
            px = ctx.last_price("ACME")
            if px and px > 100:
                return [Signal(self.name, "ACME", Side.LONG, score=0.7,
                               price=px, reason="above 100")]
            return []
"""

from __future__ import annotations

import abc
import logging
from typing import Iterable

from engine.context import MarketContext
from engine.signal import Signal


class BaseStrategy(abc.ABC):
    """
    Subclass this and implement `generate()`.

    Class attributes
    ----------------
    name : str
        Unique identifier. Defaults to the class name if left blank.
    interval : str
        Desired cadence ("10s", "1m", "5m", "1h", "1d"). The runner reads this;
        it is advisory — the runner decides how to honour it.
    enabled : bool
        Set False to keep a strategy in the tree but skip it at runtime.
    """

    name: str = ""
    interval: str = "1d"
    enabled: bool = True

    def __init__(self, **params) -> None:
        # Strategy-specific parameters arrive as kwargs and are stored as-is.
        self.params = params
        if not self.name:
            self.name = self.__class__.__name__
        self.log = logging.getLogger(f"strategy.{self.name}")

    # ── lifecycle hooks (optional to override) ───────────────────────────
    def setup(self) -> None:
        """Called once before the first run. Load models, warm caches, etc."""

    def teardown(self) -> None:
        """Called once on shutdown. Release resources."""

    # ── the only required method ─────────────────────────────────────────
    @abc.abstractmethod
    def generate(self, ctx: MarketContext) -> Iterable[Signal]:
        """
        Evaluate the current context and return an iterable of Signals
        (return an empty list when there is nothing to do).
        """
        raise NotImplementedError

    def __repr__(self) -> str:
        state = "on" if self.enabled else "off"
        return f"<{self.__class__.__name__} name={self.name!r} {self.interval} {state}>"
