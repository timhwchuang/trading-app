"""Tests for P2-7 uat_report.py."""

from __future__ import annotations

import json
import unittest

from uat_report import compute_metrics, format_report, parse_signal_audit_line


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

    def test_quick_stop_loss_detection(self):
        lines = [
            "10:00:00 [INFO] MOMENTUM Long 突破 | 價格 18000.0",
            "10:00:01 [INFO] MOMENTUM Long 突破 | 價格 18010.0",
            '10:01:00 [INFO] SIGNAL_AUDIT {"intent":"entry","direction":"Buy","price":18000,"ts":100,"reason":"pullback"}',
            '10:01:03 [INFO] SIGNAL_AUDIT {"intent":"exit","direction":"Sell","price":17997,"ts":103,"reason":"stop_loss"}',
            '10:05:00 [INFO] SIGNAL_AUDIT {"intent":"entry","direction":"Buy","price":18020,"ts":500,"reason":"pullback"}',
            '10:05:20 [INFO] SIGNAL_AUDIT {"intent":"exit","direction":"Sell","price":18040,"ts":520,"reason":"take_profit"}',
        ]
        metrics = compute_metrics(lines, quick_sl_sec=5)

        self.assertEqual(metrics["momentum_triggers"], 2)
        self.assertEqual(metrics["entry_signals"], 2)
        self.assertEqual(metrics["completed_rounds"], 2)
        self.assertEqual(metrics["quick_stop_loss_lt_5s"], 1)
        self.assertAlmostEqual(metrics["quick_stop_loss_rate_lt_5s"], 0.5)
        self.assertAlmostEqual(metrics["momentum_to_entry_conversion"], 1.0)

    def test_format_report_contains_key_lines(self):
        metrics = compute_metrics([], quick_sl_sec=5)
        report = format_report(metrics, quick_sl_sec=5)
        self.assertIn("動量觸發數", report)
        self.assertIn("秒停損", report)


if __name__ == "__main__":
    unittest.main()
