"""Tests for P6-6 performance_metrics."""

from __future__ import annotations

import json
import unittest

from performance_metrics import (
    FrictionSettings,
    compute_drawdown,
    compute_expectancy_stats,
    compute_performance_from_fills,
    compute_sharpe_sortino,
    extract_round_trip_gross_pnls,
    friction_per_round_trip,
    sweep_score_from_kpi,
)
from uat_report import compute_metrics, format_report


class TestPerformanceMetrics(unittest.TestCase):
    def test_expectancy_known_sequence(self):
        gross = [10.0, -5.0, 8.0, -6.0]
        stats = compute_expectancy_stats(gross, friction_per_trade=2.0)
        self.assertEqual(stats["trade_count"], 4)
        self.assertEqual(stats["win_rate"], 0.5)
        self.assertAlmostEqual(stats["expectancy_per_trade_gross"], 1.75)
        self.assertAlmostEqual(stats["expectancy_per_trade_net"], -0.25)

    def test_drawdown_known_curve(self):
        cumulative = [5.0, 10.0, 3.0, 8.0]
        dd = compute_drawdown(cumulative)
        self.assertEqual(dd["max_drawdown_points"], 7.0)

    def test_friction_flat_round_trip(self):
        f = FrictionSettings(enabled=True, round_trip_friction_points=2.5)
        self.assertEqual(friction_per_round_trip(f), 2.5)

    def test_friction_disabled(self):
        f = FrictionSettings(enabled=True, round_trip_friction_points=2.5)
        f_off = FrictionSettings(enabled=False, round_trip_friction_points=2.5)
        self.assertEqual(friction_per_round_trip(f_off), 0.0)
        self.assertEqual(friction_per_round_trip(f), 2.5)

    def test_extract_round_trips(self):
        fills = [
            {"intent": "entry", "pnl_points": 0},
            {"intent": "exit", "pnl_points": 10},
            {"intent": "entry", "pnl_points": 0},
            {"intent": "exit", "pnl_points": -5},
        ]
        self.assertEqual(extract_round_trip_gross_pnls(fills), [10.0, -5.0])

    def test_sharpe_requires_variance(self):
        self.assertIsNone(compute_sharpe_sortino([1.0])["sharpe"])
        sharpe = compute_sharpe_sortino([1.0, 2.0, 3.0])["sharpe"]
        self.assertIsNotNone(sharpe)

    def test_compute_performance_from_fills(self):
        fills = [
            {"intent": "entry", "pnl_points": 0},
            {"intent": "exit", "pnl_points": 10},
            {"intent": "entry", "pnl_points": 0},
            {"intent": "exit", "pnl_points": -5},
        ]
        friction = FrictionSettings(enabled=True, round_trip_friction_points=2.0)
        perf = compute_performance_from_fills(fills, friction)
        self.assertEqual(perf["total_pnl_gross"], 5.0)
        self.assertEqual(perf["total_pnl_net"], 1.0)

    def test_uat_report_includes_performance(self):
        lines = [
            '10:01:00 [INFO] FILL_AUDIT {"intent":"entry","direction":"Buy","signal_price":18000,"fill_price":18000,"slippage_pts":0,"limit_price":18003,"slippage_vs_limit_pts":-3,"order_id":"o1","ts":100,"hold_sec":0,"pnl_points":0,"exit_reason":"","ioc_slippage_allowed":3}',
            '10:05:00 [INFO] FILL_AUDIT {"intent":"exit","direction":"Sell","signal_price":18010,"fill_price":18010,"slippage_pts":0,"limit_price":18007,"slippage_vs_limit_pts":-3,"order_id":"o2","ts":200,"hold_sec":100,"pnl_points":10,"exit_reason":"take_profit","ioc_slippage_allowed":3}',
        ]
        friction = FrictionSettings(enabled=True, round_trip_friction_points=2.0)
        metrics = compute_metrics(lines, friction=friction)
        self.assertIn("performance", metrics)
        self.assertEqual(metrics["performance"]["total_pnl_gross"], 10.0)
        self.assertEqual(metrics["performance"]["total_pnl_net"], 8.0)
        report = format_report(metrics)
        self.assertIn("生存指標", report)

    def test_sweep_score_expectancy_net(self):
        kpi = {
            "quick_stop_loss_rate": 0.1,
            "performance_aggregate": {
                "expectancy_per_trade_net": 2.0,
                "max_drawdown_points": 5.0,
            },
            "_summaries": [],
        }
        score = sweep_score_from_kpi(
            kpi, metric="expectancy_net", dd_penalty=0.5, sl_penalty=10.0
        )
        self.assertAlmostEqual(score, 2.0 - 0.5 * 5.0 - 10.0 * 0.1)


if __name__ == "__main__":
    unittest.main()
