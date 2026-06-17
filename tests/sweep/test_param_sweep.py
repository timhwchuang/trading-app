"""Phase 5 + 6.6: Parameter sweep and config patch tests."""

from __future__ import annotations

import datetime
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import config
from core.runtime_config import default_runtime_config
from tests.sweep._tick_helpers import make_replay_tick
from observability import build_config_snapshot
from sweep.param_sweep import (
    _apply_params,
    _restore_params,
    _run_backtest_summaries,
    sweep,
)
from integrations.engine_wiring import trading_app_engine_ports
from strategy_vwap_momentum import StrategyParams, VWAPMomentumStrategy
from trading_engine.engine import TradingEngine


class TestParamSweep(unittest.TestCase):
    def test_sweep_small_grid(self):
        ticks = [make_replay_tick(datetime.datetime(2026, 6, 12, 9, 0, 0))]

        def fake_replay(_code, _dates, cache_dir=None):
            yield from ticks

        grid = {
            "ENTRY_BAND_POINTS": [2.0, 3.0],
            "VWAP_STOP_POINTS": [3, 4],
        }
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            with patch("trading_backtest.loader.iter_replay_ticks", fake_replay):
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

    def test_sweep_with_trend_params_attaches_veto_metrics(self):
        """P6-1-CAL-3: param_sweep now accepts trend_ keys and attaches veto_metrics via harness."""
        ticks = [make_replay_tick(datetime.datetime(2026, 6, 12, 9, 0, 0))]

        def fake_replay(_code, _dates, cache_dir=None):
            yield from ticks

        grid = {
            "trend_filter_enabled": [False, True],
            "trend_min_strength": [0.0, 0.5],
        }
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            with patch("trading_backtest.loader.iter_replay_ticks", fake_replay):
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
            self.assertIn("veto_metrics", row)
            self.assertIn("veto_rate", row["veto_metrics"])

    def test_config_restored(self):
        cfg = default_runtime_config()
        original_cfg = cfg.live_get("ENTRY_BAND_POINTS", cfg.entry_band_points)
        saved = _apply_params({"ENTRY_BAND_POINTS": 99.0}, cfg)
        _restore_params(saved, cfg)
        self.assertEqual(
            cfg.live_get("ENTRY_BAND_POINTS", cfg.entry_band_points),
            original_cfg,
        )

    def test_daily_summary_params_match_sweep(self):
        ticks = [make_replay_tick(datetime.datetime(2026, 6, 12, 9, 0, 0))]

        def fake_replay(_code, _dates, cache_dir=None):
            yield from ticks

        cfg = default_runtime_config()
        saved = _apply_params({"ENTRY_BAND_POINTS": 42.0}, cfg)
        try:
            self.assertEqual(
                build_config_snapshot(cfg)["entry_band_points"], 42.0
            )
            with tempfile.TemporaryDirectory() as tmp:
                cache_dir = Path(tmp)
                with patch("trading_backtest.loader.iter_replay_ticks", fake_replay):
                    summaries, _signals = _run_backtest_summaries(
                        "TXFR1",
                        [datetime.date(2026, 6, 12)],
                        cache_dir,
                        runtime_config=cfg,
                    )
            self.assertEqual(
                summaries[-1]["params"]["entry_band_points"],
                42.0,
            )
        finally:
            _restore_params(saved, cfg)

    def test_sweep_params_affect_entry(self):
        cfg = default_runtime_config()
        original = cfg.live_get("ENTRY_BAND_POINTS", cfg.entry_band_points)
        saved = _apply_params({"ENTRY_BAND_POINTS": 7.5}, cfg)
        try:
            api = MagicMock()
            ports = trading_app_engine_ports(
                api=api, use_mock_adapter=True, runtime_config=cfg
            )
            host = TradingEngine(
                api=api,
                strategy=VWAPMomentumStrategy(
                    params=StrategyParams.from_runtime_config(cfg),
                    obs=ports["obs"],
                ),
                **{k: v for k, v in ports.items() if k != "obs"},
            )
            host._api_connected = True
            host.current_vwap = 18000.0
            host.vol_1s = 1
            strat = host.strategy
            strat.momentum.active = True
            strat.momentum.direction = "Long"
            strat.momentum.trigger_time = 900
            host.current_atr = 30.0
            host.indicators.last_atr_refresh = 1000.0
            host.position_qty = 0
            host.is_pending = False
            host.consecutive_loss = 0
            host.last_exit_time = 0
            dt = datetime.datetime(2026, 6, 12, 10, 0, 0)
            self.assertEqual(
                cfg.live_get("ENTRY_BAND_POINTS", cfg.entry_band_points),
                7.5,
            )
            signal = host.process_strategy(1000, 18000.0, dt)
            self.assertIsNotNone(signal)
            self.assertEqual(signal.intent, "entry")
        finally:
            _restore_params(saved, cfg)
        self.assertEqual(
            cfg.live_get("ENTRY_BAND_POINTS", cfg.entry_band_points),
            original,
        )


if __name__ == "__main__":
    unittest.main()