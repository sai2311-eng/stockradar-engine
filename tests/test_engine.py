"""
Smoke tests for the engine scaffolding. Run with: pytest
These verify the plumbing — registry, discovery, context, runner — works end to
end with the example strategy. They assert nothing about trading edge.
"""

from datetime import datetime, timezone

from engine import discover, get_registry, MarketContext, Runner, Signal, Side
from engine.registry import register, clear
from engine.strategy import BaseStrategy
from data.feed import DataFeed, Candle, NullDataFeed


def test_discover_finds_example():
    reg = discover("strategies")
    assert "example_price_threshold" in reg


def test_register_and_run_custom_strategy():
    clear()

    class StubFeed(DataFeed):
        def last_price(self, symbol):
            return 250.0
        def candles(self, symbol, interval="1d", lookback=100):
            return []

    @register
    class AlwaysLong(BaseStrategy):
        name = "always_long"
        def generate(self, ctx):
            return [Signal(self.name, "TEST", Side.LONG, score=1.0,
                           price=ctx.last_price("TEST"), reason="unit test")]

    captured = []
    runner = Runner(
        context_factory=lambda: MarketContext(feed=StubFeed(), universe=["TEST"]),
        sink=captured.append,
    )
    signals = runner.tick()

    assert len(signals) == 1
    assert captured[0].symbol == "TEST"
    assert captured[0].side is Side.LONG
    assert captured[0].price == 250.0


def test_null_feed_yields_no_signals_from_example():
    clear()
    discover("strategies")
    runner = Runner(
        context_factory=lambda: MarketContext(feed=NullDataFeed(), universe=["ACME"]),
    )
    # NullDataFeed returns no prices, so the price-threshold example emits nothing.
    assert runner.tick() == []


def test_context_defaults():
    ctx = MarketContext()
    assert isinstance(ctx.now, datetime)
    assert ctx.now.tzinfo == timezone.utc
    assert ctx.universe == []
    assert ctx.last_price("ANY") is None
