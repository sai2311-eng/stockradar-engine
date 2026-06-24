"""
strategies/example_strategy.py
A minimal, intentionally naive example strategy.

It exists only to demonstrate the BaseStrategy contract end-to-end:
  - subclass BaseStrategy
  - decorate with @register so discovery picks it up
  - implement generate(ctx) -> Iterable[Signal]

It contains NO real edge. Replace it with your own logic.
"""

from __future__ import annotations

from typing import Iterable

from engine import BaseStrategy, Signal, Side, register
from engine.context import MarketContext


@register
class PriceThresholdExample(BaseStrategy):
    """
    Emits a LONG signal for any symbol in the universe whose last price is
    above a threshold. Purely illustrative.
    """

    name = "example_price_threshold"
    interval = "1m"

    def __init__(self, threshold: float = 100.0, **params) -> None:
        super().__init__(**params)
        self.threshold = threshold

    def generate(self, ctx: MarketContext) -> Iterable[Signal]:
        signals: list[Signal] = []
        for symbol in ctx.universe:
            price = ctx.last_price(symbol)
            if price is None:
                # NullDataFeed returns None — wire a real feed to get prices.
                continue
            if price > self.threshold:
                signals.append(
                    Signal(
                        strategy=self.name,
                        symbol=symbol,
                        side=Side.LONG,
                        score=0.5,
                        price=price,
                        reason=f"price {price} > threshold {self.threshold}",
                    )
                )
        return signals
