"""Phase 5 + 6.6: Parameter sweep and config patch tests."""

from __future__ import annotations

import datetime
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import config
from storage.tick_loader import ReplayTick
from observability import build_config_snapshot
from sweep.param_sweep import (
    _apply_params,
    _restore_params,
    _run_backtest_summaries,
    sweep,
)
from runtime.engine import TradingEngine


class TestParamSweep(unittest.TestCase):
    def test_sweep_small_grid(self):
        ticks = [
            ReplayTick(datetime.datetime(2026, 6, 12, 9, 0, 0), "18000", 1, 1),
        ]

        def fake_replay(_code, _dates, cache_dir=None):
            yield from ticks

        grid = {
            "ENTRY_BAND_POINTS": [2.0, 3.0],
            "VWAP_STOP_POINTS": [3, 4],
        }
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            with patch("backtest.replay.iter_replay_ticks", fake_replay):
                results = sweep(
                    grid,
                    dates_train=[datetime.date(2026, 6, 12)],
                    dates_valid=[datetime.date(2026, 6, 13)],
                    code="TXFR1",
                    cache_dir=cache_dir,
                )
        self.assertEqual(len(results), 4)
        for row in results:
            self.assertIn("params", row)
            self.assertIn("train_kpi", row)
            self.assertIn("valid_kpi", row)
        scores = [r["valid_score"] for r in results]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_config_restored(self):
        original_cfg = config.ENTRY_BAND_POINTS
        saved = _apply_params({"ENTRY_BAND_POINTS": 99.0})
        _restore_params(saved)
        self.assertEqual(config.ENTRY_BAND_POINTS, original_cfg)

    def test_daily_summary_params_match_sweep(self):
        ticks = [
            ReplayTick(datetime.datetime(2026, 6, 12, 9, 0, 0), "18000", 1, 1),
        ]

        def fake_replay(_code, _dates, cache_dir=None):
            yield from ticks

        saved = _apply_params({"ENTRY_BAND_POINTS": 42.0})
        try:
            self.assertEqual(build_config_snapshot()["entry_band_points"], 42.0)
            with tempfile.TemporaryDirectory() as tmp:
                cache_dir = Path(tmp)
                with patch("backtest.replay.iter_replay_ticks", fake_replay):
                    summaries = _run_backtest_summaries(
                        "TXFR1",
                        [datetime.date(2026, 6, 12)],
                        cache_dir,
                    )
            self.assertEqual(
                summaries[-1]["params"]["entry_band_points"],
                42.0,
            )
        finally:
            _restore_params(saved)

    def test_sweep_params_affect_entry(self):
        original = config.ENTRY_BAND_POINTS
        saved = _apply_params({"ENTRY_BAND_POINTS": 7.5})
        try:
            host = TradingEngine(api=MagicMock())
            host._api_connected = True
            host.current_vwap = 18000.0
            host.vol_1s = 1
            host.momentum_active = True
            host.momentum_dir = "Long"
            host.momentum_trigger_time = 900
            host.current_atr = 30.0
            host.has_position = False
            host.is_pending = False
            host.consecutive_loss = 0
            host.last_exit_time = 0
            dt = datetime.datetime(2026, 6, 12, 10, 0, 0)
            self.assertEqual(config.ENTRY_BAND_POINTS, 7.5)
            signal = host.process_strategy(1000, 18000.0, dt)
            self.assertIsNotNone(signal)
            self.assertEqual(signal.intent, "entry")
        finally:
            _restore_params(saved)
        self.assertEqual(config.ENTRY_BAND_POINTS, original)


if __name__ == "__main__":
    unittest.main()
