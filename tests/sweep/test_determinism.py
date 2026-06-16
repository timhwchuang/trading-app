"""Phase 4 + 6.2/6.8: Determinism gate and uat_report compatibility tests."""

from __future__ import annotations

import datetime
import json
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config import MIN_ATR_THRESHOLD
from storage.kbar_loader import KBarRecord, kbars_cache_path, save_kbars_csv
from sweep.determinism_check import (
    canonical_audit_json,
    capture_backtest_log_lines,
    hash_audit_lines,
    hash_audit_records,
    run_hash,
)
from trading_engine.core.types import OrderSignal
from trading_engine.engine import TradingEngine
from reporting.uat_report import compute_metrics
from tests.sweep._tick_helpers import session_ticks as _session_ticks


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
            audit=self.build_entry_audit(dt, price, ts, "Buy"),
        )

    return process


def _patched_entry_when_atr_ready(original):
    def process(self, ts, price, dt):
        if self.has_position or self.is_pending:
            return original(self, ts, price, dt)
        if self.current_atr < MIN_ATR_THRESHOLD:
            return None
        return OrderSignal(
            "Buy",
            1,
            price,
            "entry",
            exchange_ts=ts,
            audit=self.build_entry_audit(dt, price, ts, "Buy"),
        )

    return process


def _seed_kbars_cache(cache_dir: Path, code: str = "TXFR1") -> None:
    prev = datetime.date(2026, 6, 11)
    bars = [
        KBarRecord(
            datetime.datetime(2026, 6, 11, 13, 30) + datetime.timedelta(minutes=i),
            18000 + i,
            18020 + i,
            17980 + i,
            18010 + i,
            50,
        )
        for i in range(25)
    ]
    save_kbars_csv(bars, kbars_cache_path(cache_dir, code, prev))


class TestDeterminism(unittest.TestCase):
    def test_three_runs_same_hash(self):
        ticks = _session_ticks()
        date = datetime.date(2026, 6, 12)

        def fake_replay(_code, _dates, cache_dir=None):
            yield from ticks

        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            with patch("trading_backtest.loader.iter_replay_ticks", fake_replay):
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
            with patch("trading_backtest.loader.iter_replay_ticks", fake_replay):
                with patch.object(
                    TradingEngine,
                    "process_strategy",
                    _patched_entry_process(
                        TradingEngine.process_strategy
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

        original_emit = TradingEngine._emit_daily_summary

        def emit_with_bonus(self, trade_date):
            original_emit(self, trade_date)
            logging.getLogger("trading_engine").info(
                "DAILY_SUMMARY %s",
                json.dumps({"date": str(trade_date), "bonus": 1}),
            )

        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            with patch("trading_backtest.loader.iter_replay_ticks", fake_replay):
                base_hash = run_hash("TXFR1", [date], cache_dir=cache_dir)
                with patch.object(
                    TradingEngine, "_emit_daily_summary", emit_with_bonus
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

    def test_hash_ignores_operational_wall_clock(self):
        base = {
            "date": "2026-06-12",
            "operational": {
                "lock_wait_max_ms": 0.001,
                "intent_cancelled": 0,
            },
        }
        mutated = {
            "date": "2026-06-12",
            "operational": {
                "lock_wait_max_ms": 99.0,
                "intent_cancelled": 0,
            },
        }
        h_base = hash_audit_records(
            [("DAILY_SUMMARY", json.dumps(base, ensure_ascii=False))]
        )
        h_mutated = hash_audit_records(
            [("DAILY_SUMMARY", json.dumps(mutated, ensure_ascii=False))]
        )
        self.assertEqual(h_base, h_mutated)

    def test_three_runs_same_hash_with_kbars_and_fills(self):
        ticks = _session_ticks()
        date = datetime.date(2026, 6, 12)

        def fake_replay(_code, _dates, cache_dir=None):
            yield from ticks

        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            _seed_kbars_cache(cache_dir)
            with patch("trading_backtest.loader.iter_replay_ticks", fake_replay):
                with patch.object(
                    TradingEngine,
                    "process_strategy",
                    _patched_entry_when_atr_ready(
                        TradingEngine.process_strategy
                    ),
                ):
                    hashes = [
                        run_hash("TXFR1", [date], cache_dir=cache_dir)
                        for _ in range(3)
                    ]
                    captured = capture_backtest_log_lines(
                        "TXFR1", [date], cache_dir=cache_dir
                    )
        self.assertEqual(hashes[0], hashes[1])
        self.assertEqual(hashes[1], hashes[2])
        fill_lines = [line for line in captured if "FILL_AUDIT" in line]
        self.assertGreater(len(fill_lines), 0)
        metrics = compute_metrics(captured)
        self.assertGreater(metrics["fill_count"], 0)

    def test_performance_in_daily_summary_hash_stable(self):
        """P6-6 / TODO 7.6: performance block in DAILY_SUMMARY must be hash-stable."""
        ticks = _session_ticks()
        date = datetime.date(2026, 6, 12)

        def fake_replay(_code, _dates, cache_dir=None):
            yield from ticks

        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            _seed_kbars_cache(cache_dir)
            with patch("trading_backtest.loader.iter_replay_ticks", fake_replay):
                with patch.object(
                    TradingEngine,
                    "process_strategy",
                    _patched_entry_when_atr_ready(
                        TradingEngine.process_strategy
                    ),
                ):
                    hashes = [
                        run_hash("TXFR1", [date], cache_dir=cache_dir)
                        for _ in range(3)
                    ]
        self.assertEqual(hashes[0], hashes[1])
        self.assertEqual(hashes[1], hashes[2])


if __name__ == "__main__":
    unittest.main()
