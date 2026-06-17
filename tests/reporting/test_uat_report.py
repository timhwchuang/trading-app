"""Tests for uat_report.py."""

from __future__ import annotations

import json
import unittest

from reporting.uat_report import (
    build_tuning_hints,
    compute_metrics,
    format_report,
    format_trend_report,
    parse_daily_summary_line,
    parse_fill_audit_line,
    parse_signal_audit_line,
)


class TestUatReport(unittest.TestCase):
    def test_parse_signal_audit(self):
        payload = json.dumps(
            {
                "intent": "entry",
                "direction": "Buy",
                "price": 18000.0,
                "ts": 100,
                "reason": "pullback",
            },
            ensure_ascii=False,
        )
        line = f"12:00:00 [INFO] SIGNAL_AUDIT {payload}"
        audit = parse_signal_audit_line(line)
        assert audit is not None
        self.assertEqual(audit.intent, "entry")
        self.assertEqual(audit.ts, 100)

    def test_parse_fill_audit(self):
        payload = json.dumps(
            {
                "intent": "entry",
                "direction": "Buy",
                "signal_price": 18000.0,
                "fill_price": 18001.0,
                "slippage_pts": 1.0,
                "limit_price": 18003.0,
                "slippage_vs_limit_pts": -2.0,
                "order_id": "o1",
                "ts": 100,
            },
            ensure_ascii=False,
        )
        line = f"12:00:00 [INFO] FILL_AUDIT {payload}"
        fill = parse_fill_audit_line(line)
        assert fill is not None
        self.assertEqual(fill.slippage_pts, 1.0)

    def test_quick_stop_loss_from_fills(self):
        lines = [
            "10:00:00 [INFO] MOMENTUM Long 突破 | 價格 18000.0",
            '10:01:00 [INFO] FILL_AUDIT {"intent":"entry","direction":"Buy","signal_price":18000,"fill_price":18000,"slippage_pts":0,"limit_price":18003,"slippage_vs_limit_pts":-3,"order_id":"o1","ts":100,"hold_sec":0,"pnl_points":0,"exit_reason":"","ioc_slippage_allowed":3}',
            '10:01:03 [INFO] FILL_AUDIT {"intent":"exit","direction":"Sell","signal_price":17997,"fill_price":17997,"slippage_pts":0,"limit_price":17994,"slippage_vs_limit_pts":-3,"order_id":"o2","ts":103,"hold_sec":3,"pnl_points":-3,"exit_reason":"stop_loss","ioc_slippage_allowed":3}',
        ]
        metrics = compute_metrics(lines, quick_sl_sec=5)

        self.assertEqual(metrics["fill_count"], 2)
        self.assertEqual(metrics["quick_stop_loss_lt_5s"], 1)
        self.assertAlmostEqual(metrics["quick_stop_loss_rate_lt_5s"], 1.0)
        self.assertIn("stop_loss", metrics["expectancy_by_reason"])

    def test_daily_summary_trend(self):
        summary = {
            "date": "2026-06-10",
            "signals": {"momentum_to_entry_conversion": 0.5, "entry_signals": 2},
            "fills": {"entry_slippage_median": 1.0},
            "quick_stop_loss": {"rate": 0.1},
            "pnl": {"daily_pnl_points": 5},
        }
        line = f"16:00:00 [INFO] DAILY_SUMMARY {json.dumps(summary)}"
        parsed = parse_daily_summary_line(line)
        assert parsed is not None
        trend = format_trend_report([parsed])
        self.assertIn("2026-06-10", trend)

    def test_tuning_hints_high_quick_sl(self):
        hints = build_tuning_hints(
            conversion_rate=0.5,
            quick_sl_rate=0.4,
            slippage={},
            expectancy={},
            near_miss=None,
            cancel_rate=None,
            tick_type=None,
            daily_summaries=[],
        )
        self.assertTrue(any("exit_grace" in h for h in hints))

    def test_cumulative_risk_in_report(self):
        summaries = [
            {
                "date": "2026-06-10",
                "pnl": {"daily_pnl_points": 5.0},
                "performance": {"total_pnl_net": 5.0},
            },
            {
                "date": "2026-06-11",
                "pnl": {"daily_pnl_points": -30.0},
                "performance": {"total_pnl_net": -30.0},
            },
        ]
        lines = [
            f"16:00:00 [INFO] DAILY_SUMMARY {json.dumps(s, ensure_ascii=False)}"
            for s in summaries
        ]
        from reporting.uat_report import RiskBudgetSettings

        metrics = compute_metrics(
            lines,
            risk_budget=RiskBudgetSettings(
                initial_capital_points=100.0,
                max_acceptable_mdd_points=20.0,
            ),
        )
        self.assertTrue(metrics["cumulative_risk"]["budget_breached"])
        report = format_report(metrics)
        self.assertIn("風險預算（累進 MDD", report)
        self.assertTrue(
            any("累積 MDD" in h for h in metrics["tuning_hints"])
        )

    def test_format_report_contains_slippage_and_hints(self):
        lines = [
            '10:01:00 [INFO] FILL_AUDIT {"intent":"entry","direction":"Buy","signal_price":18000,"fill_price":18003,"slippage_pts":3,"limit_price":18003,"slippage_vs_limit_pts":0,"order_id":"o1","ts":100,"hold_sec":0,"pnl_points":0,"exit_reason":"","ioc_slippage_allowed":3}',
        ]
        metrics = compute_metrics(lines)
        report = format_report(metrics)
        self.assertIn("滑價", report)
        self.assertIn("調參提示", report)


if __name__ == "__main__":
    unittest.main()
