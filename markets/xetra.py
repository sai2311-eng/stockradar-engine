"""
markets/xetra.py
The German cash equity market as traded on Xetra (Deutsche Börse, Frankfurt).

Session : continuous trading 09:00–17:30 Europe/Berlin (CET/CEST). The opening
          auction runs just before 09:00 and the closing auction just after
          17:30; daily closing prices come out of that closing auction.
Calendar: weekends plus Xetra's full-day closures. Note that Xetra TRADES on
          several German public holidays (e.g. Whit Monday, 3 October), so a
          national holiday list is the wrong calendar to use here.
Currency: EUR. Yahoo Finance tickers carry the ".DE" suffix (SAP -> SAP.DE).

Always confirm the current year's calendar against Deutsche Börse's published
trading calendar; exchanges occasionally add or drop closure days.
"""

from __future__ import annotations

from datetime import date, time, timedelta
from functools import lru_cache

from markets.base import Market, easter_sunday


@lru_cache(maxsize=64)
def _xetra_holidays(year: int) -> frozenset[date]:
    easter = easter_sunday(year)
    return frozenset({
        date(year, 1, 1),              # Neujahr
        easter - timedelta(days=2),    # Karfreitag (Good Friday)
        easter + timedelta(days=1),    # Ostermontag (Easter Monday)
        date(year, 5, 1),              # Tag der Arbeit
        date(year, 12, 24),            # Heiligabend
        date(year, 12, 25),            # 1. Weihnachtstag
        date(year, 12, 26),            # 2. Weihnachtstag
        date(year, 12, 31),            # Silvester
    })


def xetra_holidays(year: int) -> set[date]:
    return set(_xetra_holidays(year))


XETRA = Market(
    code="XETRA",
    name="Xetra (Deutsche Börse)",
    tz="Europe/Berlin",
    open_time=time(9, 0),
    close_time=time(17, 30),
    currency="EUR",
    ticker_suffix=".DE",
    holidays=xetra_holidays,
)


# ── Index universes ──────────────────────────────────────────────────────
# DAX 40 constituents in Yahoo Finance notation. SNAPSHOT ONLY: the index is
# reviewed quarterly (March/June/September/December) and members change.
# Verify against Deutsche Börse / STOXX before relying on it, and override via
# UNIVERSE in .env when it drifts. Backtesting today's members over past years
# also introduces survivorship bias — see README.
DAX40 = [
    "ADS.DE",   # adidas
    "AIR.DE",   # Airbus
    "ALV.DE",   # Allianz
    "BAS.DE",   # BASF
    "BAYN.DE",  # Bayer
    "BEI.DE",   # Beiersdorf
    "BMW.DE",   # BMW
    "BNR.DE",   # Brenntag
    "CBK.DE",   # Commerzbank
    "CON.DE",   # Continental
    "DB1.DE",   # Deutsche Börse
    "DBK.DE",   # Deutsche Bank
    "DHL.DE",   # DHL Group
    "DTE.DE",   # Deutsche Telekom
    "DTG.DE",   # Daimler Truck
    "ENR.DE",   # Siemens Energy
    "EOAN.DE",  # E.ON
    "FME.DE",   # Fresenius Medical Care
    "FRE.DE",   # Fresenius
    "G24.DE",   # Scout24
    "HEI.DE",   # Heidelberg Materials
    "HEN3.DE",  # Henkel (Vz.)
    "HNR1.DE",  # Hannover Rück
    "IFX.DE",   # Infineon
    "MBG.DE",   # Mercedes-Benz Group
    "MRK.DE",   # Merck KGaA
    "MTX.DE",   # MTU Aero Engines
    "MUV2.DE",  # Münchener Rück
    "P911.DE",  # Porsche AG
    "PAH3.DE",  # Porsche SE
    "QIA.DE",   # Qiagen
    "RHM.DE",   # Rheinmetall
    "RWE.DE",   # RWE
    "SAP.DE",   # SAP
    "SHL.DE",   # Siemens Healthineers
    "SIE.DE",   # Siemens
    "SY1.DE",   # Symrise
    "VNA.DE",   # Vonovia
    "VOW3.DE",  # Volkswagen (Vz.)
    "ZAL.DE",   # Zalando
]

# The DAX performance index itself (useful as a benchmark series).
DAX_INDEX = "^GDAXI"
