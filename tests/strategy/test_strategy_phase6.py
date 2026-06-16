"""Tests for P6-1～P6-3 strategy_phase6 helpers."""

from __future__ import annotations

import unittest

from strategy.phase6 import (
    compute_trend,
    dynamic_atr_based,
    dynamic_trail_points,
    dynamic_vwap_stop_distance,
    ema,
    linear_regression_slope,
    resample_closes,
    trend_allows_entry,
    trend_from_ema,
    trend_from_vwap_slope,
)


class TestStrategyPhase6(unittest.TestCase):
    def test_ema(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        self.assertIsNotNone(ema(values, 3))

    def test_trend_long(self):
        closes = [100.0 + i for i in range(30)]
        direction, strength = trend_from_ema(closes, 20)
        self.assertEqual(direction, "Long")
        self.assertGreater(strength, 0)

    def test_trend_filter_blocks_counter(self):
        self.assertFalse(
            trend_allows_entry(
                enabled=True, trend_dir="Long", momentum_dir="Short"
            )
        )
        self.assertTrue(
            trend_allows_entry(
                enabled=True, trend_dir="Long", momentum_dir="Long"
            )
        )

    def test_resample_closes_5m(self):
        closes = [float(i) for i in range(10)]
        self.assertEqual(resample_closes(closes, 5), [4.0, 9.0])

    def test_compute_trend_ema_mode(self):
        closes = [100.0 + i for i in range(60)]
        direction, strength = compute_trend(
            closes, mode="ema", timeframe_min=5, ema_period=10
        )
        self.assertEqual(direction, "Long")
        self.assertGreater(strength, 0)

    def test_compute_trend_vwap_slope_mode(self):
        closes = [100.0 + i for i in range(30)]
        direction, _ = compute_trend(
            closes, mode="vwap_slope", timeframe_min=1, vwap_slope_min=0.1
        )
        self.assertEqual(direction, "Long")
        flat, _ = trend_from_vwap_slope([100.0, 100.1], min_slope=1.0)
        self.assertEqual(flat, "Flat")

    def test_linear_regression_slope(self):
        slope = linear_regression_slope([100.0, 101.0, 102.0, 103.0])
        self.assertAlmostEqual(slope, 1.0)

    def test_dynamic_atr_based_factory(self):
        self.assertEqual(dynamic_atr_based(10, floor=8, atr_k=0.25), 8.0)
        self.assertEqual(dynamic_atr_based(100, floor=8, atr_k=0.25), 25.0)

    def test_dynamic_trail_floor(self):
        self.assertEqual(
            dynamic_trail_points(10, floor=8, atr_k=0.25),
            8.0,
        )
        self.assertEqual(
            dynamic_trail_points(100, floor=8, atr_k=0.25),
            25.0,
        )

    def test_dynamic_vwap_stop(self):
        self.assertEqual(
            dynamic_vwap_stop_distance(40, floor=3, atr_k=0.25),
            10.0,
        )


# --- Interface injection test (new for pluggable strategies) ---

import datetime

from strategy.base import BaseStrategy, StrategySideEffects
from storage.tick_loader import ReplayTick
from unittest.mock import MagicMock


class _DummyStrategy(BaseStrategy):
    """Trivial strategy for testing injection. Always returns no signal."""
    def evaluate(self, *a, **k):
        return None, StrategySideEffects()

    def reset(self) -> None:
        pass


class TestStrategyInterfaceInjection(unittest.TestCase):
    def test_make_strategy_accepts_custom_decision_strategy(self):
        from tests.test_helpers import make_host

        dummy = _DummyStrategy()
        host = make_host(decision=dummy)

        self.assertIs(host.strategy, dummy)

    def test_trading_engine_constructor_accepts_strategy(self):
        from runtime.engine import TradingEngine

        dummy = _DummyStrategy()
        host = TradingEngine(api=MagicMock(), strategy=dummy)

        self.assertIs(host.strategy, dummy)

    def test_host_reset_momentum_delegates_to_strategy_reset(self):
        from runtime.engine import TradingEngine

        calls: list[str] = []

        class _SpyStrategy(_DummyStrategy):
            def reset(self) -> None:
                calls.append("reset")

        host = TradingEngine(api=MagicMock(), strategy=_SpyStrategy())
        host.reset_momentum()
        self.assertEqual(calls, ["reset"])

    def test_custom_strategy_survives_one_tick(self):
        """Injected BaseStrategy subclass must survive a full on_tick pass."""
        from runtime.engine import TradingEngine

        dummy = _DummyStrategy()
        host = TradingEngine(api=MagicMock(), strategy=dummy)
        host._api_connected = True
        host._order_sync_mode = True
        tick = ReplayTick(
            datetime.datetime(2026, 6, 12, 9, 0, 0), "18000", 1, 1
        )
        host.on_tick(tick)


if __name__ == "__main__":
    unittest.main()
