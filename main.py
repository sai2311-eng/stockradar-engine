"""
main.py
Entry point for the StockRadar engine.

It does three things and nothing more:
  1. configure logging
  2. discover every strategy under strategies/
  3. run them on a simple loop

There is no broker, no database, and no strategy logic here — wire those in by
providing a real DataFeed (data/feed.py) and a real signal sink. Out of the box
it runs with a NullDataFeed so you can confirm the plumbing works.

Usage:
    python main.py
"""

from __future__ import annotations

import logging
import sys

from config import settings
from engine import discover, MarketContext, Runner
from data.feed import NullDataFeed


def _configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def build_context() -> MarketContext:
    """
    Construct the per-tick snapshot. Replace NullDataFeed with your own
    DataFeed implementation to feed real prices to strategies.
    """
    return MarketContext(
        feed=NullDataFeed(),
        universe=settings.UNIVERSE,
    )


def main() -> None:
    _configure_logging()
    log = logging.getLogger("main")

    discover("strategies")          # import everything in strategies/

    runner = Runner(context_factory=build_context)
    if not runner.strategies:
        log.warning("No strategies found. Add one under strategies/ and rerun.")
    runner.run_forever(interval_sec=settings.TICK_INTERVAL_SEC)


if __name__ == "__main__":
    main()
