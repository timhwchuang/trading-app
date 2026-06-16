"""Pluggable trading strategies.

Strategies implement the `Strategy` protocol (see `base.py`).

The execution host (`runtime.TradingEngine`) and backtesting host
(`backtest.BacktestEngine`) are generic — they accept any strategy that
satisfies the interface via constructor injection.

Example:
    from strategy.base import Strategy
    from runtime.engine import TradingEngine
    from backtest.engine import BacktestEngine

    class MyStrategy(BaseStrategy): ...
    engine = TradingEngine(strategy=MyStrategy())
    backtester = BacktestEngine(..., strategy=MyStrategy())
"""

from strategy.base import BaseStrategy, Strategy, StrategySideEffects
from strategy.indicators import IndicatorState
from strategy.params import SWEEPABLE_PARAMS, SWEEP_FIELD_TO_CONST, StrategyParams
from strategy.vwap_momentum import VWAPMomentumLogic
from strategy.phase6 import (
    compute_trend,
    dynamic_trail_points,
    dynamic_vwap_stop_distance,
    trend_allows_entry,
)
