"""
markets — exchange metadata (time zone, session, calendar, currency, tickers).

    from markets import get_market
    xetra = get_market("XETRA")
    xetra.is_open()            # is continuous trading running right now?
"""

from markets.base import Market, easter_sunday
from markets.xetra import XETRA, DAX40, DAX_INDEX

_MARKETS: dict[str, Market] = {m.code: m for m in (XETRA,)}

# Named universes selectable via UNIVERSE=@DAX40 in .env
UNIVERSES: dict[str, list[str]] = {"DAX40": DAX40}


def get_market(code: str) -> Market:
    try:
        return _MARKETS[code.upper()]
    except KeyError:
        raise ValueError(f"Unknown market {code!r}. Known: {', '.join(_MARKETS)}") from None


__all__ = ["Market", "easter_sunday", "XETRA", "DAX40", "DAX_INDEX",
           "get_market", "UNIVERSES"]
