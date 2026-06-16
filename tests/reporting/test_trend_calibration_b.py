"""P6-1-CAL B-class integration: log parse + tick replay harness + sweep wiring."""

from __future__ import annotations

import datetime
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from reporting.calibration_cli import run_trend_sensitivity_sweep
from reporting.forward_pnl import ForwardPnlPolicy
from reporting.trend_calibration import partition_trend_entry_audits, run_b_class_calibration
from tests.sweep._tick_helpers import make_replay_tick

_FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "ticks"
_DAY = datetime.date(2026, 6, 12)
_ENTRY_TS = int(datetime.datetime(2026, 6, 12, 9, 0, 0).timestamp())


def _signal_audit_line(payload: dict) -> str:
    return f"12:00:00 [INFO] SIGNAL_AUDIT {json.dumps(payload, ensure_ascii=False)}"


class TestTrendCalibrationBClass(unittest.TestCase):
    def test_partition_trend_entry_audits(self):
        lines = [
            _signal_audit_line(
                {
                    "intent": "entry",
                    "direction": "Buy",
                    "price": 100.0,
                    "ts": _ENTRY_TS,
                    "reason": "trend_veto",
                }
            ),
            _signal_audit_line(
                {
                    "intent": "entry",
                    "direction": "Buy",
                    "price": 101.0,
                    "ts": _ENTRY_TS + 60,
                    "reason": "pullback",
                }
            ),
            _signal_audit_line(
                {
                    "intent": "exit",
                    "direction": "Sell",
                    "price": 102.0,
                    "ts": _ENTRY_TS + 120,
                    "reason": "stop_loss",
                }
            ),
        ]
        veto, allowed = partition_trend_entry_audits(
            [json.loads(l.split("SIGNAL_AUDIT ", 1)[1]) for l in lines[:2]]
        )
        self.assertEqual(len(veto), 1)
        self.assertEqual(len(allowed), 1)

    def test_run_b_class_calibration_with_fixture_ticks(self):
        log_lines = [
            _signal_audit_line(
                {
                    "intent": "entry",
                    "direction": "Buy",
                    "price": 100.0,
                    "ts": _ENTRY_TS,
                    "reason": "trend_veto",
                    "trend_dir": "Flat",
                    "trend_strength": 0.2,
                    "atr": 5.0,
                }
            ),
            _signal_audit_line(
                {
                    "intent": "entry",
                    "direction": "Buy",
                    "price": 100.0,
                    "ts": _ENTRY_TS + 30,
                    "reason": "pullback",
                    "trend_dir": "Long",
                    "trend_strength": 1.0,
                    "atr": 5.0,
                }
            ),
        ]
        result = run_b_class_calibration(
            log_lines=log_lines,
            code="TXFR1",
            dates=[_DAY],
            cache_dir=_FIXTURE_DIR,
            forward_policy=ForwardPnlPolicy(window_seconds=1800),
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["n_veto"], 1)
        self.assertEqual(result["n_allowed"], 1)
        self.assertIn("delta_expectancy", result)
        self.assertIn("B-class replay", result["notes"])
        self.assertGreater(result["mean_forward_if_vetoed"], 0.0)

    def test_sweep_with_replay_forward_policy(self):
        ticks = [
            make_replay_tick(datetime.datetime(2026, 6, 12, 9, 0, 0), close="100"),
            make_replay_tick(datetime.datetime(2026, 6, 12, 9, 30, 0), close="110"),
        ]

        def fake_replay(_code, _dates, cache_dir=None):
            yield from ticks

        policy = ForwardPnlPolicy(window_seconds=1800)
        with tempfile.TemporaryDirectory() as tmp:
            with patch("trading_backtest.loader.iter_replay_ticks", fake_replay):
                with patch("reporting.forward_pnl.iter_replay_ticks", fake_replay):
                    rows = run_trend_sensitivity_sweep(
                        code="TXFR1",
                        dates_train=[_DAY],
                        dates_valid=[_DAY],
                        cache_dir=Path(tmp),
                        forward_policy=policy,
                    )
        self.assertEqual(len(rows), len([0.0, 0.3, 0.5, 0.8, 1.0, 1.5]))
        for row in rows:
            vm = row.get("veto_metrics") or {}
            self.assertIn("delta_expectancy", vm)
            self.assertIn("B-class replay", vm.get("notes", ""))


if __name__ == "__main__":
    unittest.main()