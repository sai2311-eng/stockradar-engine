"""
data/csv_feed.py
A DataFeed backed by a directory of OHLCV CSV files.

File lookup, for symbol "SAP.DE" and interval "1d":
    <directory>/SAP.DE_1d.csv   (preferred)
    <directory>/SAP.DE.csv      (fallback, any interval)

Both international and German exports are understood:

    Date,Open,High,Low,Close,Volume              ← Yahoo / scripts/fetch_yahoo.py
    2024-01-02,186.10,188.50,185.90,187.40,1234567

    Datum;Eröffnung;Hoch;Tief;Schlusskurs;Volumen  ← onvista / Börse Frankfurt style
    02.01.2024;186,10;188,50;185,90;187,40;1.234.567

The delimiter is sniffed from the header line and the decimal separator from
the first data rows (a ';' file may use "187,40" or "187.40" — both occur in
the wild), unless `decimal` is passed explicitly. Naive timestamps are read
as exchange-local time (`tz`) and stored as UTC.

Timestamp convention: a daily bar's `ts` is the session CLOSE (17:30 local for
Xetra by default), because that is the earliest moment its close is known.
This is what keeps the backtester free of look-ahead.
"""

from __future__ import annotations

import csv
import logging
import re
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Optional, Sequence
from zoneinfo import ZoneInfo

from data.feed import Candle, DataFeed

logger = logging.getLogger(__name__)

# Lower-cased header aliases → canonical column
_COLUMNS = {
    "ts": ("date", "datetime", "timestamp", "time", "datum", "zeit"),
    "open": ("open", "eröffnung", "eroeffnung", "erster", "erster kurs", "start"),
    "high": ("high", "hoch", "tageshoch"),
    "low": ("low", "tief", "tagestief"),
    "close": ("close", "adj close", "schluss", "schlusskurs", "letzter",
              "letzter kurs", "kurs"),
    "volume": ("volume", "volumen", "stücke", "stuecke", "umsatz in stück"),
}

_DEC_COMMA = re.compile(r"-?\d{1,3}(\.\d{3})*,\d{1,4}|-?\d+,\d{1,4}")
_DEC_DOT = re.compile(r"-?\d{1,3}(,\d{3})*\.\d{1,4}|-?\d+\.\d{1,4}")

_DATE_FORMATS = ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
                 "%Y-%m-%dT%H:%M:%S", "%d.%m.%Y", "%d.%m.%Y %H:%M:%S",
                 "%d.%m.%Y %H:%M", "%d.%m.%y")


def parse_number(raw: str, decimal: str = ".") -> float:
    """'1.234,56' (decimal=',') or '1,234.56' (decimal='.') -> 1234.56."""
    s = raw.strip().replace(" ", "").replace(" ", "")
    if not s or s in ("-", "null", "NaN", "nan"):
        return float("nan")
    if decimal == ",":
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    return float(s)


def parse_timestamp(raw: str, zone: ZoneInfo, daily_time: time) -> datetime:
    """Parse a date/datetime string; date-only values get `daily_time`."""
    s = raw.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:  # ISO 8601, possibly with offset
        dt = datetime.fromisoformat(s)
    except ValueError:
        for fmt in _DATE_FORMATS:
            try:
                dt = datetime.strptime(s, fmt)
                break
            except ValueError:
                continue
        else:
            raise ValueError(f"Unrecognised date format: {raw!r}")
    if dt.tzinfo is None:
        if len(s) <= 10:  # date only → stamp at session close
            dt = datetime.combine(dt.date(), daily_time)
        dt = dt.replace(tzinfo=zone)
    return dt.astimezone(timezone.utc)


def sniff_decimal(samples: list[str], delimiter: str) -> str:
    """
    Guess the decimal separator from sample price strings. A comma followed by
    1–4 trailing digits ("187,40", "1.234,5") means decimal comma; a dot
    followed by 1–4 digits with no comma means decimal dot. With ',' as the
    field delimiter, decimals can only be dots.
    """
    if delimiter == ",":
        return "."
    comma = dot = 0
    for raw in samples:
        v = raw.strip()
        if _DEC_COMMA.fullmatch(v):
            comma += 1
        elif _DEC_DOT.fullmatch(v):
            dot += 1
    return "." if dot > comma else ","


def _map_header(header: list[str]) -> dict[str, int]:
    norm = [h.strip().strip('"').lower() for h in header]
    idx: dict[str, int] = {}
    for col, aliases in _COLUMNS.items():
        for alias in aliases:
            if alias in norm:
                idx[col] = norm.index(alias)
                break
    missing = [c for c in ("ts", "close") if c not in idx]
    if missing:
        raise ValueError(f"CSV header {header!r} lacks required column(s) {missing}")
    return idx


def read_candles(path: Path, tz: str = "UTC", daily_time: time = time(0, 0),
                 decimal: Optional[str] = None) -> list[Candle]:
    """Load one CSV file into Candles, oldest first. Bad rows are skipped."""
    zone = ZoneInfo(tz)
    with open(path, newline="", encoding="utf-8-sig") as fh:
        first = fh.readline()
        delim = ";" if first.count(";") > first.count(",") else ","
        fh.seek(0)
        rows = list(csv.reader(fh, delimiter=delim))
        idx = _map_header(rows[0])
        rows = rows[1:]
        dec = decimal or sniff_decimal(
            [r[idx["close"]] for r in rows[:50] if len(r) > idx["close"]], delim)
        out: list[Candle] = []
        skipped = 0
        for row in rows:
            if not row or not any(cell.strip() for cell in row):
                continue
            try:
                close = parse_number(row[idx["close"]], dec)
                get = lambda c: parse_number(row[idx[c]], dec) if c in idx else close
                vol = parse_number(row[idx["volume"]], dec) if "volume" in idx else 0.0
                candle = Candle(
                    ts=parse_timestamp(row[idx["ts"]], zone, daily_time),
                    open=get("open"), high=get("high"), low=get("low"),
                    close=close, volume=0.0 if vol != vol else vol,
                )
            except (ValueError, IndexError):
                skipped += 1
                continue
            if candle.close != candle.close:  # NaN close (holiday rows etc.)
                skipped += 1
                continue
            out.append(candle)
    if skipped:
        logger.debug("%s: skipped %d unparsable row(s)", path.name, skipped)
    out.sort(key=lambda c: c.ts)
    # Drop duplicate timestamps, keeping the last occurrence.
    dedup: dict[datetime, Candle] = {c.ts: c for c in out}
    return list(dedup.values())


class CSVDataFeed(DataFeed):
    """
    Parameters
    ----------
    directory : str | Path
        Folder holding the CSV files.
    tz : str
        Time zone for naive timestamps in the files (e.g. "Europe/Berlin").
    daily_time : time
        Local time assigned to date-only rows — use the session close.
    decimal : str | None
        Force "," or "."; None sniffs from the delimiter.
    """

    def __init__(self, directory: str | Path, tz: str = "UTC",
                 daily_time: time = time(0, 0),
                 decimal: Optional[str] = None) -> None:
        self.directory = Path(directory)
        self.tz = tz
        self.daily_time = daily_time
        self.decimal = decimal
        self._cache: dict[tuple[str, str], tuple[int, list[Candle]]] = {}
        self._missing: set[tuple[str, str]] = set()

    @classmethod
    def for_market(cls, directory: str | Path, market, **kw) -> "CSVDataFeed":
        """Feed configured with a Market's time zone and closing time."""
        return cls(directory, tz=market.tz, daily_time=market.close_time, **kw)

    def _path(self, symbol: str, interval: str) -> Optional[Path]:
        for name in (f"{symbol}_{interval}.csv", f"{symbol}.csv"):
            p = self.directory / name
            if p.is_file():
                return p
        return None

    def history(self, symbol: str, interval: str = "1d") -> list[Candle]:
        """
        All candles for `symbol`, oldest first. Cached, and reloaded when the
        file changes on disk — so a live loop picks up freshly appended rows.
        """
        key = (symbol, interval)
        path = self._path(symbol, interval)
        if path is None:
            if key not in self._missing:
                logger.warning("No CSV for %s (%s) in %s", symbol, interval, self.directory)
                self._missing.add(key)
            return []
        mtime = path.stat().st_mtime_ns
        cached = self._cache.get(key)
        if cached is None or cached[0] != mtime:
            self._cache[key] = (mtime, read_candles(path, self.tz, self.daily_time,
                                                    self.decimal))
            self._missing.discard(key)
        return self._cache[key][1]

    def symbols(self) -> list[str]:
        """Symbols that have at least one CSV in the directory."""
        names = set()
        for p in self.directory.glob("*.csv"):
            stem = p.stem
            head, sep, tail = stem.rpartition("_")
            names.add(head if sep and tail[:1].isdigit() else stem)
        return sorted(names)

    # ── DataFeed interface ───────────────────────────────────────────────
    def last_price(self, symbol: str) -> Optional[float]:
        bars = self.history(symbol, "1d")
        return bars[-1].close if bars else None

    def candles(self, symbol: str, interval: str = "1d",
                lookback: int = 100) -> Sequence[Candle]:
        bars = self.history(symbol, interval)
        return bars[-lookback:] if lookback > 0 else []
