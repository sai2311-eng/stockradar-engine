"""
backtest.py
Replay CSV history through every strategy in strategies/ and print a report.

Examples:
    # DAX 40 on Xetra, daily bars from data/csv, 5-day horizon
    python backtest.py --data data/csv --market XETRA --universe @DAX40

    # A few names, a window, stricter costs
    python backtest.py --data data/csv --market XETRA \\
        --universe SAP.DE,SIE.DE,ALV.DE --start 2020-01-01 --end 2024-12-31 \\
        --horizon 10 --cost-bps 10

Get data first with scripts/fetch_yahoo.py, or drop in your own CSV exports
(German ';' / decimal-comma files work as-is — see data/csv_feed.py).
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, time, timezone

from config import settings
from data.csv_feed import CSVDataFeed
from engine import Backtester, discover


def _date(s: str, end: bool = False) -> datetime:
    d = datetime.strptime(s, "%Y-%m-%d").date()
    return datetime.combine(d, time.max if end else time.min, tzinfo=timezone.utc)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--data", default=settings.DATA_DIR or "data/csv",
                    help="directory of CSV files (default: DATA_DIR or data/csv)")
    ap.add_argument("--market", default=settings.MARKET,
                    help="exchange calendar/time zone, e.g. XETRA")
    ap.add_argument("--universe", default=None,
                    help="comma list or @DAX40 (default: UNIVERSE, else every CSV)")
    ap.add_argument("--interval", default="1d")
    ap.add_argument("--horizon", type=int, default=5, help="bars to hold each signal")
    ap.add_argument("--entry", choices=("next_open", "close"), default="next_open")
    ap.add_argument("--cost-bps", type=float, default=5.0, help="cost per side, bps")
    ap.add_argument("--start", type=_date)
    ap.add_argument("--end", type=lambda s: _date(s, end=True))
    ap.add_argument("--log-level", default="WARNING")
    args = ap.parse_args(argv)

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.WARNING),
                        format="%(levelname)s %(name)s — %(message)s")

    market = None
    if args.market:
        from markets import get_market
        market = get_market(args.market)
        feed = CSVDataFeed.for_market(args.data, market)
    else:
        feed = CSVDataFeed(args.data)

    if args.universe:
        universe = settings._parse_universe(args.universe)
    else:
        universe = settings.UNIVERSE or feed.symbols()
    if not universe:
        print(f"No symbols: pass --universe or put CSV files in {args.data}", file=sys.stderr)
        return 2

    strategies = discover("strategies")
    if not strategies:
        print("No strategies found in strategies/.", file=sys.stderr)
        return 2

    result = Backtester(
        feed=feed, universe=universe, strategies=strategies,
        interval=args.interval, horizon=args.horizon, entry=args.entry,
        cost_bps=args.cost_bps, start=args.start, end=args.end, market=market,
    ).run()

    missing = [s for s in universe if not feed.history(s, args.interval)]
    if missing:
        print(f"Note: no data for {len(missing)} symbol(s): {', '.join(missing[:10])}"
              + (" …" if len(missing) > 10 else ""), file=sys.stderr)
    if market:
        print(f"Market: {market.name}, prices in {market.currency}")
    print(f"Universe: {len(universe)} symbol(s), strategies: {', '.join(strategies)}")
    print(result.report())
    return 0


if __name__ == "__main__":
    sys.exit(main())
