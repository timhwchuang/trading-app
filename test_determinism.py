"""Phase 4 + 6.2/6.8: Determinism gate and uat_report compatibility tests."""

from __future__ import annotations

import datetime
import json
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from data_loader import ReplayTick
from determinism_check import (
    canonical_audit_json,
    capture_backtest_log_lines,
    hash_audit_lines,
    run_hash,
)
from man import OrderSignal, VWAPMomentumStrategy
from uat_report import compute_metrics


def _session_ticks() -> list[ReplayTick]:
    base = datetime.datetime(2026, 6, 12, 9, 0, 0)
    return [
        ReplayTick(base, "18000", 1, 1),
        ReplayTick(base.replace(second=1), "18000", 1, 1),
    ]


def _patched_entry_process(original):
    def process(self, ts, price, dt):
        if self.has_position or self.is_pending:
            return original(self, ts, price, dt)
        return OrderSignal(
            "Buy",
            1,
            price,
            "entry",
            exchange_ts=ts,
            audit=self._build_entry_audit(dt, price, ts, "Buy"),
        )

    return process


class TestDeterminism(unittest.TestCase):
    def test_three_runs_same_hash(self):
        ticks = _session_ticks()
        date = datetime.date(2026, 6, 12)

        def fake_replay(_code, _dates, cache_dir=None):
            yield from ticks

        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            with patch("backtester.iter_replay_ticks", fake_replay):
                hashes = [run_hash("TXFR1", [date], cache_dir=cache_dir) for _ in range(3)]
        self.assertEqual(hashes[0], hashes[1])
        self.assertEqual(hashes[1], hashes[2])
        self.assertTrue(hashes[0])

    def test_uat_report_parses_backtest_log(self):
        ticks = _session_ticks()
        date = datetime.date(2026, 6, 12)

        def fake_replay(_code, _dates, cache_dir=None):
            yield from ticks

        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            with patch("backtester.iter_replay_ticks", fake_replay):
                with patch.object(
                    VWAPMomentumStrategy,
                    "process_strategy",
                    _patched_entry_process(
                        VWAPMomentumStrategy.process_strategy
                    ),
                ):
                    captured = capture_backtest_log_lines(
                        "TXFR1", [date], cache_dir=cache_dir
                    )
            lines = [
                "10:00:00 [INFO] MOMENTUM Long 突破 | 價格 18000.0",
                *captured,
            ]
            metrics = compute_metrics(lines)
        self.assertGreater(metrics["fill_count"], 0)
        self.assertIsNotNone(metrics["momentum_to_entry_conversion"])

    def test_daily_summary_in_hash(self):
        ticks = _session_ticks()
        date = datetime.date(2026, 6, 12)

        def fake_replay(_code, _dates, cache_dir=None):
            yield from ticks

        original_emit = VWAPMomentumStrategy._emit_daily_summary

        def emit_with_bonus(self, trade_date):
            original_emit(self, trade_date)
            logging.getLogger("man").info(
                "DAILY_SUMMARY %s",
                json.dumps({"date": str(trade_date), "bonus": 1}),
            )

        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            with patch("backtester.iter_replay_ticks", fake_replay):
                base_hash = run_hash("TXFR1", [date], cache_dir=cache_dir)
                with patch.object(
                    VWAPMomentumStrategy, "_emit_daily_summary", emit_with_bonus
                ):
                    mutated_hash = run_hash("TXFR1", [date], cache_dir=cache_dir)
        self.assertNotEqual(base_hash, mutated_hash)

    def test_hash_robust_to_key_order(self):
        forward = json.dumps({"b": 1, "a": 2}, ensure_ascii=False)
        reversed_keys = json.dumps({"a": 2, "b": 1}, ensure_ascii=False)
        self.assertEqual(
            canonical_audit_json(forward),
            canonical_audit_json(reversed_keys),
        )
        self.assertEqual(
            hash_audit_lines([forward]),
            hash_audit_lines([reversed_keys]),
        )


if __name__ == "__main__":
    unittest.main()
