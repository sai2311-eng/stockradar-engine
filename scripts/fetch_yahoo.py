"""
scripts/fetch_yahoo.py
Download daily OHLCV bars from Yahoo Finance's public chart endpoint into
CSV files that data/csv_feed.py reads. Standard library only.

    python scripts/fetch_yahoo.py --universe @DAX40 --range 10y --out data/csv
    python scripts/fetch_yahoo.py --universe SAP.DE,^GDAXI --range 5y

Caveats — read before relying on the numbers:
  * This is an unofficial, undocumented endpoint. It can rate-limit, change,
    or disappear without notice, and Yahoo's terms restrict redistribution.
    Don't commit the downloaded files to a public repo.
  * Prices are NOT adjusted for dividends. German companies mostly pay one
    annual dividend (often 2–5 % for DAX names), so unadjusted closes show a
    gap on the ex-date. Splits ARE adjusted by Yahoo.
  * For production use a licensed source (Deutsche Börse, your broker's API).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import _parse_universe  # noqa: E402

URL = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?{qs}"


def fetch(symbol: str, rng: str) -> list[list]:
    qs = urllib.parse.urlencode({"range": rng, "interval": "1d", "events": "split"})
    req = urllib.request.Request(URL.format(sym=urllib.parse.quote(symbol), qs=qs),
                                 headers={"User-Agent": "Mozilla/5.0 stockradar-engine"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    res = (payload.get("chart") or {}).get("result") or []
    if not res:
        raise RuntimeError((payload.get("chart") or {}).get("error") or "empty result")
    res = res[0]
    tz = ZoneInfo(res["meta"].get("exchangeTimezoneName") or "UTC")
    q = res["indicators"]["quote"][0]
    rows = []
    for i, ts in enumerate(res.get("timestamp") or []):
        o, h, l, c, v = (q[k][i] for k in ("open", "high", "low", "close", "volume"))
        if c is None:
            continue
        day = datetime.fromtimestamp(ts, timezone.utc).astimezone(tz).date()
        rows.append([day.isoformat(), o, h, l, c, v or 0])
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Download Yahoo daily bars to CSV.")
    ap.add_argument("--universe", required=True, help="comma list or @DAX40")
    ap.add_argument("--range", default="5y", help="1y, 5y, 10y, max, ...")
    ap.add_argument("--out", default="data/csv")
    ap.add_argument("--pause", type=float, default=0.5, help="seconds between requests")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    failed = []
    for sym in _parse_universe(args.universe):
        try:
            rows = fetch(sym, args.range)
        except (urllib.error.URLError, RuntimeError, KeyError, ValueError) as exc:
            print(f"  {sym}: FAILED ({exc})", file=sys.stderr)
            failed.append(sym)
            continue
        path = out / f"{sym}_1d.csv"
        with open(path, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["Date", "Open", "High", "Low", "Close", "Volume"])
            w.writerows(rows)
        print(f"  {sym}: {len(rows)} bars → {path}")
        time.sleep(args.pause)
    if failed:
        print(f"{len(failed)} symbol(s) failed: {', '.join(failed)}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
