"""
engine/runner.py
The loop that drives strategies.

The Runner builds one instance of each registered strategy, calls setup(),
then on every tick asks each enabled strategy to generate() against a fresh
MarketContext. Emitted Signals are passed to a sink callback (log by default).

This is deliberately simple — a single in-process loop. Swap it for APScheduler,
Celery, asyncio, or a cloud queue without touching any strategy: the BaseStrategy
contract is all the rest of the system depends on.
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Iterable, Optional, Type

from engine.context import MarketContext
from engine.signal import Signal
from engine.strategy import BaseStrategy
from engine.registry import get_registry

logger = logging.getLogger(__name__)

SignalSink = Callable[[Signal], None]


def _default_sink(sig: Signal) -> None:
    logger.info("SIGNAL %s", sig)


class Runner:
    """
    Parameters
    ----------
    context_factory : Callable[[], MarketContext]
        Called once per tick to build the snapshot handed to strategies.
        Defaults to an empty MarketContext (NullDataFeed) so the engine runs
        before any data source is wired.
    sink : Callable[[Signal], None]
        Receives every emitted signal. Default logs it. Replace to route
        signals to a queue, a database, Telegram, an order executor, etc.
    strategies : dict[str, type] | None
        Registry to use. Defaults to whatever discover()/register() populated.
    """

    def __init__(
        self,
        context_factory: Optional[Callable[[], MarketContext]] = None,
        sink: SignalSink = _default_sink,
        strategies: Optional[dict[str, Type[BaseStrategy]]] = None,
    ) -> None:
        self.context_factory = context_factory or (lambda: MarketContext())
        self.sink = sink
        classes = strategies if strategies is not None else get_registry()
        self.strategies: list[BaseStrategy] = [cls() for cls in classes.values()]

    # ── lifecycle ────────────────────────────────────────────────────────
    def setup(self) -> None:
        for s in self.strategies:
            try:
                s.setup()
            except Exception as exc:
                logger.error("setup() failed for %s: %s", s.name, exc)

    def teardown(self) -> None:
        for s in self.strategies:
            try:
                s.teardown()
            except Exception as exc:
                logger.error("teardown() failed for %s: %s", s.name, exc)

    # ── one pass over all strategies ─────────────────────────────────────
    def tick(self) -> list[Signal]:
        """Run every enabled strategy once; return all signals emitted."""
        ctx = self.context_factory()
        emitted: list[Signal] = []
        for s in self.strategies:
            if not s.enabled:
                continue
            try:
                result: Iterable[Signal] = s.generate(ctx) or []
            except Exception as exc:
                logger.error("generate() failed for %s: %s", s.name, exc)
                continue
            for sig in result:
                emitted.append(sig)
                try:
                    self.sink(sig)
                except Exception as exc:
                    logger.error("sink failed for signal %s: %s", sig, exc)
        return emitted

    # ── the simple built-in loop ─────────────────────────────────────────
    def run_forever(self, interval_sec: float = 60.0) -> None:
        """Tick every `interval_sec` until interrupted."""
        if not self.strategies:
            logger.warning("No strategies registered — nothing to run. "
                           "Add one to strategies/ and call discover().")
        self.setup()
        logger.info("Runner started with %d strategy(ies). Ctrl+C to stop.",
                    len(self.strategies))
        try:
            while True:
                self.tick()
                time.sleep(interval_sec)
        except (KeyboardInterrupt, SystemExit):
            logger.info("Runner stopping.")
        finally:
            self.teardown()
