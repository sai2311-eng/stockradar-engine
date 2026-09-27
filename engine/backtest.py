"""
engine/backtest.py
Replay historical candles through the same strategies the live Runner uses.

How it works
------------
1. Build a timeline from every bar timestamp in the universe (optionally
   restricted to a Market's trading days and a start/end window).
2. At each step, strategies receive a MarketContext whose feed is a
   ReplayFeed — a point-in-time view that hides every bar after `now`.
   Strategies cannot see the future even by accident.
3. Every LONG/SHORT signal is scored by its forward return over `horizon`
   bars, entered at the NEXT bar's open (default) and exited at the close
   `horizon` bars after the signal bar, minus round-trip costs.
4. Results are compared against a baseline: the average forward return of
   entering the same side on EVERY bar of the same symbols. A strategy only
   shows skill if it beats that baseline — raw returns in a rising market
   mostly measure the market, not the strategy.

What this is NOT: a portfolio simulator. Signals are scored independently,
so a strategy that fires every day produces overlapping, highly correlated
samples. Treat hit-rate and mean return as a first filter, not as P&L.
"""

from __future__ import annotations

import bisect
import logging
import statistics
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional, Sequence, Type

from data.feed import Candle, DataFeed
from engine.context import MarketContext
from engine.registry import get_registry
from engine.runner import Runner
from engine.signal import Side, Signal
from engine.strategy import BaseStrategy

logger = logging.getLogger(__name__)


class ReplayFeed(DataFeed):
    """
    Point-in-time view over another feed: only bars with ts <= now exist.
    `bar_filter` drops bars entirely (e.g. rows a vendor emitted on exchange
    holidays), for strategies and scoring alike.
    """

    def __init__(self, source: DataFeed, now: Optional[datetime] = None,
                 bar_filter: Optional[Callable[[Candle], bool]] = None) -> None:
        self.source = source
        self.now = now
        self.bar_filter = bar_filter
        self._bars: dict[tuple[str, str], list[Candle]] = {}
        self._ts: dict[tuple[str, str], list[datetime]] = {}

    def history(self, symbol: str, interval: str = "1d") -> list[Candle]:
        """Full, unclipped history — for the backtester only, never strategies."""
        key = (symbol, interval)
        if key not in self._bars:
            if hasattr(self.source, "history"):
                bars = list(self.source.history(symbol, interval))
            else:
                bars = list(self.source.candles(symbol, interval, lookback=sys.maxsize))
            if self.bar_filter is not None:
                bars = [b for b in bars if self.bar_filter(b)]
            self._bars[key] = bars
            self._ts[key] = [b.ts for b in bars]
        return self._bars[key]

    def _cut(self, symbol: str, interval: str) -> int:
        """Number of bars visible at `now`."""
        bars = self.history(symbol, interval)
        if self.now is None:
            return len(bars)
        return bisect.bisect_right(self._ts[(symbol, interval)], self.now)

    def last_price(self, symbol: str) -> Optional[float]:
        n = self._cut(symbol, "1d")
        return self.history(symbol, "1d")[n - 1].close if n else None

    def candles(self, symbol: str, interval: str = "1d",
                lookback: int = 100) -> Sequence[Candle]:
        n = self._cut(symbol, interval)
        if lookback <= 0:
            return []
        return self.history(symbol, interval)[max(0, n - lookback):n]


@dataclass
class SignalOutcome:
    """One signal plus what happened afterwards."""
    signal: Signal
    at: datetime
    entry: Optional[float] = None
    exit: Optional[float] = None
    ret: Optional[float] = None   # net of costs, side-adjusted; None = unscored

    @property
    def scored(self) -> bool:
        return self.ret is not None


@dataclass
class BacktestResult:
    outcomes: list[SignalOutcome]
    horizon: int
    entry: str
    cost_bps: float
    baseline_long: Optional[float]   # mean gross forward return, every bar
    steps: int
    start: Optional[datetime]
    end: Optional[datetime]
    failures: list[str] = field(default_factory=list)

    @property
    def signals(self) -> list[Signal]:
        return [o.signal for o in self.outcomes]

    def summary(self) -> dict[str, dict[str, Any]]:
        """Per-strategy stats over scored LONG/SHORT signals."""
        cost = 2 * self.cost_bps / 10_000
        out: dict[str, dict[str, Any]] = {}
        by_strat: dict[str, list[SignalOutcome]] = {}
        for o in self.outcomes:
            by_strat.setdefault(o.signal.strategy, []).append(o)
        for name, outs in sorted(by_strat.items()):
            scored = [o for o in outs if o.scored]
            rets = [o.ret for o in scored]
            excess = None
            if scored and self.baseline_long is not None:
                # Same-side random entry, same costs, as the benchmark.
                bench = [(self.baseline_long if o.signal.side is Side.LONG
                          else -self.baseline_long) - cost for o in scored]
                excess = statistics.fmean(rets) - statistics.fmean(bench)
            out[name] = {
                "signals": len(outs),
                "scored": len(scored),
                "long": sum(o.signal.side is Side.LONG for o in scored),
                "short": sum(o.signal.side is Side.SHORT for o in scored),
                "hit_rate": (sum(r > 0 for r in rets) / len(rets)) if rets else None,
                "mean_ret": statistics.fmean(rets) if rets else None,
                "median_ret": statistics.median(rets) if rets else None,
                "excess_vs_baseline": excess,
            }
        return out

    def report(self) -> str:
        pct = lambda x: "—" if x is None else f"{x * 100:+.2f}%"
        lines = [
            f"Backtest: {self.steps} steps"
            + (f", {self.start:%Y-%m-%d} → {self.end:%Y-%m-%d}" if self.start and self.end else ""),
            f"Horizon {self.horizon} bars, entry={self.entry}, "
            f"cost {self.cost_bps:g} bps/side, baseline LONG {pct(self.baseline_long)} (gross)",
            "",
            f"{'strategy':<28}{'signals':>8}{'scored':>8}{'hit':>8}"
            f"{'mean':>10}{'median':>10}{'vs base':>10}",
        ]
        summ = self.summary()
        for name, s in summ.items():
            hit = "—" if s["hit_rate"] is None else f"{s['hit_rate'] * 100:.0f}%"
            lines.append(f"{name[:27]:<28}{s['signals']:>8}{s['scored']:>8}{hit:>8}"
                         f"{pct(s['mean_ret']):>10}{pct(s['median_ret']):>10}"
                         f"{pct(s['excess_vs_baseline']):>10}")
        if not summ:
            lines.append("(no signals)")
        if self.failures:
            lines += ["", f"{len(self.failures)} strategy error(s); first: {self.failures[0]}"]
        return "\n".join(lines)


class Backtester:
    """
    Parameters
    ----------
    feed : DataFeed
        Historical source (e.g. CSVDataFeed). Wrapped in a ReplayFeed.
    universe : list[str]
        Symbols to replay and expose via ctx.universe.
    strategies : dict[str, type] | None
        Strategy classes; defaults to the registry.
    interval : str
        Bar interval driving the timeline.
    horizon : int
        Bars to hold each signal when scoring it.
    entry : "next_open" | "close"
        Fill at the next bar's open (realistic) or the signal bar's close
        (optimistic — assumes you trade in the closing auction you just saw).
    cost_bps : float
        Cost per side in basis points (commission + half-spread + slippage).
    start, end : datetime | None
        Timeline window (UTC, inclusive). Earlier bars stay visible as history.
    market : Market | None
        If given, bars dated on non-trading days are dropped (strategies never
        see them, scoring never fills on them), and the market is exposed to
        strategies as ctx.get("market").
    extras : dict | None
        Passed through to MarketContext.extras.
    """

    def __init__(
        self,
        feed: DataFeed,
        universe: list[str],
        strategies: Optional[dict[str, Type[BaseStrategy]]] = None,
        interval: str = "1d",
        horizon: int = 5,
        entry: str = "next_open",
        cost_bps: float = 5.0,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        market=None,
        extras: Optional[dict[str, Any]] = None,
    ) -> None:
        if entry not in ("next_open", "close"):
            raise ValueError("entry must be 'next_open' or 'close'")
        if horizon < 1:
            raise ValueError("horizon must be >= 1")
        on_calendar = None
        if market is not None:
            on_calendar = lambda b: market.is_trading_day(market.local(b.ts).date())
        self.replay = ReplayFeed(feed, bar_filter=on_calendar)
        self.universe = list(universe)
        self.strategies = strategies if strategies is not None else get_registry()
        self.interval = interval
        self.horizon = horizon
        self.entry = entry
        self.cost_bps = cost_bps
        self.start = start
        self.end = end
        self.market = market
        self.extras = dict(extras or {})
        if market is not None:
            self.extras.setdefault("market", market)

    # ── timeline ─────────────────────────────────────────────────────────
    def _in_window(self, ts: datetime) -> bool:
        if self.start and ts < self.start:
            return False
        if self.end and ts > self.end:
            return False
        if self.market is not None and not self.market.is_trading_day(
                self.market.local(ts).date()):
            return False
        return True

    def timeline(self) -> list[datetime]:
        stamps = set()
        for sym in self.universe:
            stamps.update(b.ts for b in self.replay.history(sym, self.interval))
        return sorted(ts for ts in stamps if self._in_window(ts))

    # ── scoring ──────────────────────────────────────────────────────────
    def _fill(self, bars: list[Candle], i: int) -> Optional[tuple[float, float]]:
        """(entry, exit) prices for a signal on bar i, or None if not enough data."""
        j = i + self.horizon
        if j >= len(bars):
            return None
        entry = bars[i + 1].open if self.entry == "next_open" else bars[i].close
        if not entry or entry != entry:
            return None
        return entry, bars[j].close

    def _score(self, sig: Signal, at: datetime) -> SignalOutcome:
        out = SignalOutcome(signal=sig, at=at)
        if sig.side not in (Side.LONG, Side.SHORT):
            return out
        bars = self.replay.history(sig.symbol, self.interval)
        ts = self.replay._ts.get((sig.symbol, self.interval), [])
        i = bisect.bisect_right(ts, at) - 1
        if i < 0:
            return out
        fill = self._fill(bars, i)
        if fill is None:
            return out
        out.entry, out.exit = fill
        gross = out.exit / out.entry - 1
        if sig.side is Side.SHORT:
            gross = -gross
        out.ret = gross - 2 * self.cost_bps / 10_000
        return out

    def _baseline(self, steps: list[datetime]) -> Optional[float]:
        """Mean gross LONG forward return from entering on every in-window bar."""
        if not steps:
            return None
        lo, hi = steps[0], steps[-1]
        rets = []
        for sym in self.universe:
            bars = self.replay.history(sym, self.interval)
            for i, b in enumerate(bars):
                if lo <= b.ts <= hi and self._in_window(b.ts):
                    fill = self._fill(bars, i)
                    if fill:
                        rets.append(fill[1] / fill[0] - 1)
        return statistics.fmean(rets) if rets else None

    # ── main loop ────────────────────────────────────────────────────────
    def run(self) -> BacktestResult:
        steps = self.timeline()
        collected: list[tuple[datetime, Signal]] = []
        failures: list[str] = []
        now_ref: list[datetime] = []

        def context() -> MarketContext:
            return MarketContext(feed=self.replay, now=now_ref[0],
                                 universe=self.universe, extras=dict(self.extras))

        def sink(sig: Signal) -> None:
            sig.created_at = now_ref[0]          # simulated, not wall-clock, time
            collected.append((now_ref[0], sig))

        def on_error(strategy: BaseStrategy, stage: str, exc: Exception) -> None:
            when = f" @ {now_ref[0]:%Y-%m-%d}" if now_ref else ""
            failures.append(f"{strategy.name}.{stage}{when}: {exc}")

        runner = Runner(context_factory=context, sink=sink,
                        strategies=self.strategies, on_error=on_error)
        try:
            runner.setup()
            for ts in steps:
                now_ref[:] = [ts]
                self.replay.now = ts
                runner.tick()
        finally:
            runner.teardown()
            self.replay.now = None

        logger.info("Backtest: %d steps, %d signals", len(steps), len(collected))
        return BacktestResult(
            outcomes=[self._score(sig, at) for at, sig in collected],
            horizon=self.horizon,
            entry=self.entry,
            cost_bps=self.cost_bps,
            baseline_long=self._baseline(steps),
            steps=len(steps),
            start=steps[0] if steps else None,
            end=steps[-1] if steps else None,
            failures=failures,
        )
