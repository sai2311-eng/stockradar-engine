"""
main.py
Entry point for the StockRadar engine.

It does three things and nothing more:
  1. configure logging
  2. discover every strategy under strategies/
  3. run them on a simple loop

There is no broker, no database, and no strategy logic here. Configure via .env:

  MARKET=XETRA          only tick during Xetra hours (09:00–17:30 Berlin)
  DATA_DIR=data/csv     read prices from CSV files (see data/csv_feed.py)
  UNIVERSE=@DAX40       which symbols strategies see

With none of these set it runs with a NullDataFeed so you can confirm the
plumbing works. For historical replay use backtest.py instead.

Usage:
    python main.py
"""

from __future__ import annotations

import logging
import sys

from config import settings
from engine import discover, MarketContext, Runner
from data.feed import DataFeed, NullDataFeed


def _configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def _market():
    if not settings.MARKET:
        return None
    from markets import get_market
    return get_market(settings.MARKET)


def build_feed(market=None) -> DataFeed:
    """CSVDataFeed if DATA_DIR is set, else NullDataFeed. Swap in your own."""
    if settings.DATA_DIR:
        from data.csv_feed import CSVDataFeed
        if market is not None:
            return CSVDataFeed.for_market(settings.DATA_DIR, market)
        return CSVDataFeed(settings.DATA_DIR)
    return NullDataFeed()


def main() -> None:
    _configure_logging()
    log = logging.getLogger("main")

    discover("strategies")          # import everything in strategies/

    market = _market()
    feed = build_feed(market)       # built once so CSV caches survive ticks
    extras = {"market": market} if market else {}

    def build_context() -> MarketContext:
        """The per-tick snapshot handed to strategies."""
        return MarketContext(feed=feed, universe=settings.UNIVERSE, extras=extras)

    runner = Runner(context_factory=build_context)
    if not runner.strategies:
        log.warning("No strategies found. Add one under strategies/ and rerun.")
    if market:
        log.info("Market %s (%s, %s–%s %s)", market.code, market.currency,
                 market.open_time.strftime("%H:%M"), market.close_time.strftime("%H:%M"),
                 market.tz)
    runner.run_forever(interval_sec=settings.TICK_INTERVAL_SEC,
                       gate=market.is_open if market else None)


if __name__ == "__main__":
    main()
