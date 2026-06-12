"""Phase 5 + 6.6: Parameter sweep and man-namespace patch tests."""

from __future__ import annotations

import datetime
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import config
import man
import observability
from data_loader import ReplayTick
from observability import build_config_snapshot
from param_sweep import (
    _apply_params,
    _restore_params,
    _run_backtest_summaries,
    sweep,
)
from man import VWAPMomentumStrategy


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
            with patch("backtester.iter_replay_ticks", fake_replay):
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
        original_man = man.ENTRY_BAND_POINTS
        original_cfg = config.ENTRY_BAND_POINTS
        original_obs = observability.ENTRY_BAND_POINTS
        saved = _apply_params({"ENTRY_BAND_POINTS": 99.0})
        _restore_params(saved)
        self.assertEqual(man.ENTRY_BAND_POINTS, original_man)
        self.assertEqual(config.ENTRY_BAND_POINTS, original_cfg)
        self.assertEqual(observability.ENTRY_BAND_POINTS, original_obs)

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
                with patch("backtester.iter_replay_ticks", fake_replay):
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

    def test_man_namespace_patched(self):
        original = man.ENTRY_BAND_POINTS
        saved = _apply_params({"ENTRY_BAND_POINTS": 7.5})
        try:
            strategy = VWAPMomentumStrategy(api=MagicMock())
            strategy._api_connected = True
            strategy.current_vwap = 18000.0
            strategy.vol_1s = 1
            strategy.momentum_active = True
            strategy.momentum_dir = "Long"
            strategy.momentum_trigger_time = 900
            strategy.current_atr = 30.0
            strategy.has_position = False
            strategy.is_pending = False
            strategy.consecutive_loss = 0
            strategy.last_exit_time = 0
            dt = datetime.datetime(2026, 6, 12, 10, 0, 0)
            self.assertEqual(man.ENTRY_BAND_POINTS, 7.5)
            signal = strategy.process_strategy(1000, 18000.0, dt)
            self.assertIsNotNone(signal)
            self.assertEqual(signal.intent, "entry")
        finally:
            _restore_params(saved)
        self.assertEqual(man.ENTRY_BAND_POINTS, original)


if __name__ == "__main__":
    unittest.main()
