"""Pluggable trading strategies.

Decision logic implements ``Strategy`` (see ``base.py``) and is injected into the
execution host via ``TradingEngine(strategy=...)`` or ``BacktestEngine(strategy=...)``.

Example — minimal plugin (inherits defaults for momentum, exit, audit)::

    from strategy.base import BaseStrategy, StrategySideEffects
    from runtime.engine import TradingEngine
    from unittest.mock import MagicMock

    class HoldFlat(BaseStrategy):
        def evaluate(self, market, position, risk, vol_threshold, **kwargs):
            return None, StrategySideEffects()

    host = TradingEngine(api=MagicMock(), strategy=HoldFlat())
    # host.strategy is the injected plugin; host itself is the execution engine.

The default plugin is ``VWAPMomentumStrategy`` when ``strategy`` is omitted.
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
