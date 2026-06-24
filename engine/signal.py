"""
engine/signal.py
The structured result a strategy emits when it finds something worth acting on.

A Signal is intentionally minimal and broker-agnostic. It says *what* the
strategy saw, not *how* to place the order — translating a Signal into a
concrete order is the job of whatever execution layer you bolt on.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


class Side(str, enum.Enum):
    """Direction of a signal."""
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"      # close / no-position
    NEUTRAL = "NEUTRAL"  # non-directional (e.g. a volatility signal)


@dataclass
class Signal:
    """
    What a strategy returns from `generate()`.

    Attributes
    ----------
    strategy : str
        Name of the strategy that produced the signal.
    symbol : str
        Instrument the signal is about (e.g. "AAPL", "NIFTY").
    side : Side
        Direction (LONG / SHORT / FLAT / NEUTRAL).
    score : float
        Strategy-defined conviction, 0.0–1.0. The runner can rank/threshold on it.
    price : float | None
        Reference price at signal time, if known.
    reason : str
        Short human-readable explanation, for logs and alerts.
    meta : dict
        Free-form bag for anything strategy-specific (target, stop, expiry, ...).
    created_at : datetime
        UTC timestamp, set automatically.
    """
    strategy: str
    symbol: str
    side: Side = Side.NEUTRAL
    score: float = 0.0
    price: Optional[float] = None
    reason: str = ""
    meta: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __str__(self) -> str:
        px = f" @ {self.price}" if self.price is not None else ""
        return (f"[{self.strategy}] {self.symbol} {self.side.value} "
                f"score={self.score:.2f}{px} — {self.reason}")
