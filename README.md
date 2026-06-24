# StockRadar Engine

A tiny, dependency-free **scaffolding for building market scanner / trading
strategies** in Python. The engine handles discovery, scheduling, and dispatch.
You write the strategies.

It ships with **no strategies of its own** — just one trivial example so you can
see the shape. Drop a file into `strategies/`, and the engine picks it up
automatically.

> ⚠️ **Educational use only.** This is a framework, not financial advice and not
> a trading system. It contains no edge, no live brokerage integration, and no
> risk controls. Anything you build on top of it is your own responsibility.

---

## Why

Most trading-bot repos hand you someone else's strategies, which are either
worthless (if they were any good, why publish them?) or a black box you can't
trust. This does the opposite: it gives you the **boring, reusable plumbing** —
a clean strategy interface, auto-discovery, a data-feed boundary, a runner — and
gets out of the way so you can focus on *your* logic.

## Architecture

```
main.py                # entry point: configure → discover → run
config/
  settings.py          # secret-free env config (optional .env)
engine/
  strategy.py          # BaseStrategy — the interface you implement
  signal.py            # Signal + Side — what a strategy emits
  context.py           # MarketContext — the read-only snapshot you receive
  registry.py          # @register decorator + discover() auto-import
  runner.py            # the loop that drives strategies
data/
  feed.py              # DataFeed interface + NullDataFeed stub
strategies/
  example_strategy.py  # one trivial example — delete it, add your own
tests/
  test_engine.py       # smoke tests for the plumbing
```

The dependency arrow points one way: **strategies depend on the engine, never
the reverse.** A strategy only ever reads from `MarketContext`; it never touches
a broker or a database directly. That keeps strategies pure, testable, and
swappable between live and backtest.

## Quick start

```bash
git clone <your-fork-url> stockradar-engine
cd stockradar-engine
pip install -r requirements.txt   # optional — core runs on the stdlib alone

python main.py                    # runs with a NullDataFeed (no data yet)
pytest                            # run the smoke tests
```

Out of the box it runs against a `NullDataFeed`, so no signals fire — that's
expected. You've confirmed the plumbing works; now give it data and logic.

## Write your first strategy

Create `strategies/my_strategy.py`:

```python
from typing import Iterable
from engine import BaseStrategy, Signal, Side, register
from engine.context import MarketContext

@register
class MovingAverageCross(BaseStrategy):
    name = "ma_cross"
    interval = "1d"          # advisory cadence for the runner

    def generate(self, ctx: MarketContext) -> Iterable[Signal]:
        out = []
        for symbol in ctx.universe:
            bars = ctx.candles(symbol, interval="1d", lookback=200)
            if len(bars) < 200:
                continue
            fast = sum(b.close for b in bars[-50:]) / 50
            slow = sum(b.close for b in bars[-200:]) / 200
            if fast > slow:
                out.append(Signal(self.name, symbol, Side.LONG, score=0.6,
                                  price=bars[-1].close, reason="50>200 MA"))
        return out
```

That's it. No registration list to edit, no scheduler to touch. `discover()`
finds it on the next run.

## Plug in real data

Implement the `DataFeed` interface with your source of choice (broker SDK, CSV,
database, websocket cache):

```python
from data.feed import DataFeed, Candle

class MyBrokerFeed(DataFeed):
    def last_price(self, symbol):
        ...                       # call your broker / cache
    def candles(self, symbol, interval="1d", lookback=100):
        ...                       # return a list[Candle], oldest first
```

Then hand it to the context in `main.py`:

```python
def build_context():
    return MarketContext(feed=MyBrokerFeed(), universe=settings.UNIVERSE)
```

## Route signals somewhere useful

By default emitted signals are logged. Pass a `sink` to the `Runner` to send
them to a queue, a database, a Telegram bot, or an order executor:

```python
def to_telegram(sig):
    send_message(f"{sig}")

runner = Runner(context_factory=build_context, sink=to_telegram)
```

## Extending the loop

`Runner.run_forever()` is a plain `while` loop on purpose. Strategies depend only
on `BaseStrategy.generate()`, so you can replace the runner with APScheduler,
asyncio, Celery, or a cloud queue without changing a single strategy. Per-strategy
`interval` is exposed for schedulers that want to honour it.

## License

MIT — see [LICENSE](LICENSE).
