"""
markets/base.py
What the engine needs to know about an exchange: its time zone, session
hours, trading calendar, currency, and how its tickers are spelled.

A Market is pure metadata + calendar arithmetic. It never fetches data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Callable, Iterable
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Market:
    """
    Parameters
    ----------
    code : str
        Short identifier, e.g. "XETRA".
    name : str
        Human-readable name.
    tz : str
        IANA time zone of the exchange, e.g. "Europe/Berlin".
    open_time, close_time : time
        Continuous-trading session in exchange-local time.
    currency : str
        ISO currency code prices are quoted in.
    ticker_suffix : str
        Suffix used by common data vendors (e.g. ".DE" on Yahoo Finance).
    holidays : Callable[[int], set[date]]
        Returns the exchange's full-day closures for a given year.
    """
    code: str
    name: str
    tz: str
    open_time: time
    close_time: time
    currency: str
    ticker_suffix: str = ""
    holidays: Callable[[int], set[date]] = field(default=lambda year: set())

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.tz)

    # ── calendar ─────────────────────────────────────────────────────────
    def is_trading_day(self, d: date) -> bool:
        return d.weekday() < 5 and d not in self.holidays(d.year)

    def trading_days(self, start: date, end: date) -> Iterable[date]:
        """Every trading day in [start, end], inclusive."""
        d = start
        while d <= end:
            if self.is_trading_day(d):
                yield d
            d += timedelta(days=1)

    # ── session ──────────────────────────────────────────────────────────
    def local(self, when: datetime) -> datetime:
        """Convert an aware datetime (naive = UTC) to exchange-local time."""
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return when.astimezone(self.zone)

    def is_open(self, when: datetime | None = None) -> bool:
        """True during the continuous-trading session on a trading day."""
        loc = self.local(when or datetime.now(timezone.utc))
        return (self.is_trading_day(loc.date())
                and self.open_time <= loc.time() < self.close_time)

    def session_bounds(self, d: date) -> tuple[datetime, datetime]:
        """(open, close) of the session on local date `d`, as UTC datetimes."""
        o = datetime.combine(d, self.open_time, tzinfo=self.zone)
        c = datetime.combine(d, self.close_time, tzinfo=self.zone)
        return o.astimezone(timezone.utc), c.astimezone(timezone.utc)

    def symbol(self, root: str) -> str:
        """'SAP' -> 'SAP.DE' (idempotent)."""
        if self.ticker_suffix and not root.endswith(self.ticker_suffix):
            return root + self.ticker_suffix
        return root


def easter_sunday(year: int) -> date:
    """Gregorian Easter Sunday (anonymous Gregorian / Meeus algorithm)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)
