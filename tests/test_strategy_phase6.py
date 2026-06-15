"""Tests for P6-1～P6-3 strategy_phase6 helpers."""

from __future__ import annotations

import unittest

from strategy_phase6 import (
    dynamic_trail_points,
    dynamic_vwap_stop_distance,
    ema,
    trend_allows_entry,
    trend_from_ema,
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


if __name__ == "__main__":
    unittest.main()
