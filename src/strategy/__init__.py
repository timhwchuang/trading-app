"""Pluggable trading strategies.

Strategies implement the ``Strategy`` protocol (see ``base.py``) and are injected
into ``runtime.TradingEngine`` or ``backtest.BacktestEngine`` via ``strategy=``.

Example::

    from strategy.base import BaseStrategy
    from runtime.engine import TradingEngine

    class MyStrategy(BaseStrategy):
        def evaluate(self, ...):
            return None, StrategySideEffects()

    engine = TradingEngine(strategy=MyStrategy())
"""

from strategy.base import BaseStrategy, Strategy, StrategySideEffects
from strategy.indicators import IndicatorState
from strategy.params import SWEEPABLE_PARAMS, SWEEP_FIELD_TO_CONST, StrategyParams
from strategy.vwap_momentum import VWAPMomentumStrategy
from strategy.phase6 import (
    compute_trend,
    dynamic_trail_points,
    dynamic_vwap_stop_distance,
    trend_allows_entry,
)
