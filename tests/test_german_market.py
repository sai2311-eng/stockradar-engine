"""
Tests for the German-market pieces: Xetra calendar/session, CSV parsing
(including German number/date formats), the point-in-time ReplayFeed, and the
Backtester's fills, costs and no-look-ahead guarantee.
"""

import tempfile
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from config.settings import _parse_universe
from data.csv_feed import CSVDataFeed, parse_number, read_candles
from data.feed import Candle, DataFeed
from engine import Backtester, BaseStrategy, ReplayFeed, Side, Signal
from markets import DAX40, XETRA, easter_sunday

BERLIN = ZoneInfo("Europe/Berlin")


# ── calendar & session ───────────────────────────────────────────────────
def test_easter():
    assert easter_sunday(2024) == date(2024, 3, 31)
    assert easter_sunday(2025) == date(2025, 4, 20)
    assert easter_sunday(2026) == date(2026, 4, 5)


def test_xetra_holidays():
    closed = [date(2024, 1, 1), date(2024, 3, 29), date(2024, 4, 1),
              date(2024, 5, 1), date(2024, 12, 24), date(2024, 12, 25),
              date(2024, 12, 26), date(2024, 12, 31), date(2024, 6, 15)]  # last: Saturday
    for d in closed:
        assert not XETRA.is_trading_day(d), d
    # Xetra trades on these German public holidays.
    for d in (date(2024, 5, 20), date(2024, 10, 3), date(2024, 5, 9)):
        assert XETRA.is_trading_day(d), d


def test_xetra_session_handles_cet_and_cest():
    def at(y, m, d, hh, mm):
        return datetime(y, m, d, hh, mm, tzinfo=BERLIN).astimezone(timezone.utc)
    assert XETRA.is_open(at(2024, 1, 15, 9, 0))        # winter, CET
    assert not XETRA.is_open(at(2024, 1, 15, 8, 59))
    assert XETRA.is_open(at(2024, 7, 15, 17, 29))      # summer, CEST
    assert not XETRA.is_open(at(2024, 7, 15, 17, 30))
    assert not XETRA.is_open(at(2024, 12, 24, 11, 0))  # Heiligabend
    o, c = XETRA.session_bounds(date(2024, 7, 15))
    assert (o.hour, c.hour, c.minute) == (7, 15, 30)   # UTC


def test_symbol_suffix_and_dax_universe():
    assert XETRA.symbol("SAP") == "SAP.DE" == XETRA.symbol("SAP.DE")
    assert len(DAX40) == 40 == len(set(DAX40))
    assert all(s.endswith(".DE") for s in DAX40)
    assert _parse_universe("@dax40, SAP.DE, ^GDAXI") == DAX40 + ["^GDAXI"]


# ── CSV parsing ──────────────────────────────────────────────────────────
def test_parse_number_formats():
    assert parse_number("1.234,56", ",") == 1234.56
    assert parse_number("1,234.56", ".") == 1234.56
    assert parse_number("187,4", ",") == 187.4


def test_german_csv_export():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "SAP.DE_1d.csv"
        p.write_text(
            "Datum;Eröffnung;Hoch;Tief;Schlusskurs;Volumen\n"
            "03.01.2024;187,00;189,10;186,20;188,50;2.100.000\n"
            "02.01.2024;186,10;188,50;185,90;187,40;1.234.567\n"
            "04.01.2024;;;;-;\n",                       # junk row is skipped
            encoding="utf-8")
        bars = read_candles(p, tz="Europe/Berlin", daily_time=time(17, 30))
    assert [b.close for b in bars] == [187.4, 188.5]    # sorted oldest first
    assert bars[0].volume == 1_234_567
    # Date-only rows are stamped at the Xetra close, 17:30 Berlin = 16:30 UTC in winter.
    assert bars[0].ts == datetime(2024, 1, 2, 16, 30, tzinfo=timezone.utc)


def test_csv_feed_international_and_reload():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "SIE.DE_1d.csv"
        p.write_text("Date,Open,High,Low,Close,Volume\n2024-01-02,170,172,169,171.5,1000\n")
        feed = CSVDataFeed.for_market(d, XETRA)
        assert feed.last_price("SIE.DE") == 171.5
        assert feed.symbols() == ["SIE.DE"]
        assert feed.last_price("NOPE.DE") is None
        import os
        with open(p, "a") as fh:
            fh.write("2024-01-03,171,175,170,174.0,1200\n")
        st = p.stat()
        os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
        assert feed.last_price("SIE.DE") == 174.0     # picked up the new row


# ── backtesting ──────────────────────────────────────────────────────────
class ListFeed(DataFeed):
    def __init__(self, bars):
        self.bars = bars
    def last_price(self, symbol):
        return self.bars[symbol][-1].close if self.bars.get(symbol) else None
    def candles(self, symbol, interval="1d", lookback=100):
        return self.bars.get(symbol, [])[-lookback:]


def _rising(start: date, n: int):
    """n Xetra trading days of steadily rising prices: open = close - 0.5."""
    out, d, i = [], start, 0
    while len(out) < n:
        if XETRA.is_trading_day(d):
            ts = datetime.combine(d, time(17, 30), tzinfo=BERLIN).astimezone(timezone.utc)
            c = 100.0 + i
            out.append(Candle(ts, c - 0.5, c + 1, c - 1, c, 1000))
            i += 1
        d += timedelta(days=1)
    return out


def test_replay_feed_hides_future():
    bars = _rising(date(2024, 1, 2), 5)
    replay = ReplayFeed(ListFeed({"X": bars}), now=bars[2].ts)
    assert [b.close for b in replay.candles("X", lookback=10)] == [100, 101, 102]
    assert replay.last_price("X") == 102
    replay.now = bars[0].ts - timedelta(seconds=1)
    assert replay.candles("X") == [] and replay.last_price("X") is None


def test_backtest_no_lookahead_fills_and_costs():
    bars = _rising(date(2024, 1, 2), 12)
    seen_future = []

    class FirstBarLong(BaseStrategy):
        name = "first_bar_long"
        def generate(self, ctx):
            visible = ctx.candles("X", lookback=1000)
            if visible and visible[-1].ts > ctx.now:
                seen_future.append(ctx.now)
            if len(visible) == 1:
                return [Signal(self.name, "X", Side.LONG, score=1.0)]
            return []

    res = Backtester(ListFeed({"X": bars}), ["X"], {"first_bar_long": FirstBarLong},
                     horizon=2, entry="next_open", cost_bps=10).run()
    assert not seen_future
    assert res.steps == 12
    (o,) = res.outcomes
    assert o.at == bars[0].ts == o.signal.created_at
    assert (o.entry, o.exit) == (100.5, 102.0)          # next open → close 2 bars on
    assert abs(o.ret - (102.0 / 100.5 - 1 - 0.002)) < 1e-12
    s = res.summary()["first_bar_long"]
    assert s["scored"] == 1 and s["hit_rate"] == 1.0
    assert "first_bar_long" in res.report()


def test_backtest_skips_closed_days_and_unscoreable_signals():
    bars = _rising(date(2024, 3, 25), 4)
    good_friday = datetime(2024, 3, 29, 16, 30, tzinfo=timezone.utc)
    bars.insert(4, Candle(good_friday, 1, 1, 1, 1, 0))   # bogus bar on a holiday
    bars.sort(key=lambda b: b.ts)

    class AlwaysShort(BaseStrategy):
        name = "always_short"
        def generate(self, ctx):
            return [Signal(self.name, "X", Side.SHORT)]

    res = Backtester(ListFeed({"X": bars}), ["X"], {"always_short": AlwaysShort},
                     horizon=1, entry="close", cost_bps=0, market=XETRA).run()
    assert good_friday not in [o.at for o in res.outcomes]
    assert res.steps == 4
    s = res.summary()["always_short"]
    # 4 real bars, horizon 1: the last signal has no exit bar; the holiday bar
    # must never serve as an exit price (its close of 1.0 would fake a +99% short).
    assert s["signals"] == 4 and s["scored"] == 3
    assert all(o.exit != 1.0 for o in res.outcomes)


def test_backtest_survives_broken_strategy():
    class Broken(BaseStrategy):
        name = "broken"
        def generate(self, ctx):
            raise RuntimeError("boom")

    res = Backtester(ListFeed({"X": _rising(date(2024, 1, 2), 3)}), ["X"],
                     {"broken": Broken}).run()
    assert res.outcomes == [] and len(res.failures) == 3


def test_semicolon_csv_with_dot_decimals():
    # Some exports use ';' but dot decimals; must not be read as 18740.
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "BMW.DE_1d.csv"
        p.write_text("Datum;Eröffnung;Hoch;Tief;Schlusskurs;Volumen\n"
                     "02.01.2024;100.10;101.00;99.50;100.75;50000\n")
        (bar,) = read_candles(p, tz="Europe/Berlin")
    assert bar.close == 100.75 and bar.open == 100.10
