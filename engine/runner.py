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
ErrorHook = Callable[[BaseStrategy, str, Exception], None]


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
    on_error : Callable[[strategy, stage, exc], None] | None
        Called (after logging) whenever a strategy's setup/generate/teardown
        or the sink raises. stage is "setup", "generate", "teardown" or "sink".
    """

    def __init__(
        self,
        context_factory: Optional[Callable[[], MarketContext]] = None,
        sink: SignalSink = _default_sink,
        strategies: Optional[dict[str, Type[BaseStrategy]]] = None,
        on_error: Optional[ErrorHook] = None,
    ) -> None:
        self.context_factory = context_factory or (lambda: MarketContext())
        self.sink = sink
        classes = strategies if strategies is not None else get_registry()
        self.strategies: list[BaseStrategy] = [cls() for cls in classes.values()]
        self.on_error = on_error

    def _failed(self, s: BaseStrategy, stage: str, exc: Exception, detail: str = "") -> None:
        logger.error("%s() failed for %s%s: %s", stage, s.name, detail, exc)
        if self.on_error is not None:
            self.on_error(s, stage, exc)

    # ── lifecycle ────────────────────────────────────────────────────────
    def setup(self) -> None:
        for s in self.strategies:
            try:
                s.setup()
            except Exception as exc:
                self._failed(s, "setup", exc)

    def teardown(self) -> None:
        for s in self.strategies:
            try:
                s.teardown()
            except Exception as exc:
                self._failed(s, "teardown", exc)

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
                self._failed(s, "generate", exc)
                continue
            for sig in result:
                emitted.append(sig)
                try:
                    self.sink(sig)
                except Exception as exc:
                    self._failed(s, "sink", exc, f" (signal {sig})")
        return emitted

    # ── the simple built-in loop ─────────────────────────────────────────
    def run_forever(self, interval_sec: float = 60.0,
                    gate: Optional[Callable[[], bool]] = None) -> None:
        """
        Tick every `interval_sec` until interrupted. If `gate` is given, a tick
        only runs while gate() is True (e.g. ``market.is_open`` to stay quiet
        outside exchange hours).
        """
        if not self.strategies:
            logger.warning("No strategies registered — nothing to run. "
                           "Add one to strategies/ and call discover().")
        self.setup()
        logger.info("Runner started with %d strategy(ies). Ctrl+C to stop.",
                    len(self.strategies))
        try:
            was_open: Optional[bool] = None
            while True:
                is_open = gate() if gate is not None else True
                if is_open != was_open and gate is not None:
                    logger.info("Market %s.", "open — ticking" if is_open else "closed — idling")
                    was_open = is_open
                if is_open:
                    self.tick()
                time.sleep(interval_sec)
        except (KeyboardInterrupt, SystemExit):
            logger.info("Runner stopping.")
        finally:
            self.teardown()
