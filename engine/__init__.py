"""
StockRadar Engine — the open scaffolding for building scanner/trading strategies.

This package contains NO strategies of its own. It provides:

  - BaseStrategy : the interface every strategy implements (engine/strategy.py)
  - Signal       : the structured output a strategy emits (engine/signal.py)
  - MarketContext: the read-only snapshot a strategy receives (engine/context.py)
  - registry     : auto-discovery of strategies in the strategies/ package
  - Runner       : the scheduler/loop that drives strategies (engine/runner.py)
  - Backtester   : replays history through the same strategies (engine/backtest.py)

Drop your own strategy file into strategies/ and it is picked up automatically.
See README.md for a walkthrough.
"""

from engine.strategy import BaseStrategy
from engine.signal import Signal, Side
from engine.context import MarketContext
from engine.registry import register, discover, get_registry
from engine.runner import Runner
from engine.backtest import Backtester, BacktestResult, ReplayFeed

__all__ = [
    "BaseStrategy",
    "Signal",
    "Side",
    "MarketContext",
    "register",
    "discover",
    "get_registry",
    "Runner",
    "Backtester",
    "BacktestResult",
    "ReplayFeed",
]
