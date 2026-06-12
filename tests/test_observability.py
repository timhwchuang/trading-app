"""Tests for observability module."""

from __future__ import annotations

import unittest

from observability import (
    DailyObservability,
    NearMissTracker,
    build_config_snapshot,
    compute_adverse_slippage,
    compute_limit_price,
)


class TestSlippage(unittest.TestCase):
    def test_buy_adverse_slippage(self):
        self.assertEqual(compute_adverse_slippage(18000, 18002, is_buy=True), 2.0)
        self.assertEqual(compute_adverse_slippage(18000, 17998, is_buy=True), -2.0)

    def test_sell_adverse_slippage(self):
        self.assertEqual(compute_adverse_slippage(18000, 17998, is_buy=False), 2.0)

    def test_limit_price(self):
        self.assertEqual(compute_limit_price(18000, is_buy=True, ioc_slippage=3), 18003)
        self.assertEqual(
            compute_limit_price(18000, is_buy=False, ioc_slippage=3), 17997
        )


class TestNearMissTracker(unittest.TestCase):
    def test_pullback_blocks(self):
        tracker = NearMissTracker()
        tracker.on_momentum_start()
        tracker.on_pullback_tick(
            18005, 18000, near_vwap=False, vol_dried_up=True
        )
        tracker.on_pullback_tick(
            18000, 18000, near_vwap=True, vol_dried_up=False
        )
        tracker.on_pullback_tick(
            18010, 18000, near_vwap=False, vol_dried_up=False
        )
        self.assertEqual(tracker.stats.blocked_vwap_only, 1)
        self.assertEqual(tracker.stats.blocked_vol_only, 1)
        self.assertEqual(tracker.stats.blocked_both, 1)
        self.assertEqual(tracker.stats.closest_vwap_distance, 0.0)

    def test_entry_ready_tick_not_counted(self):
        tracker = NearMissTracker()
        tracker.on_momentum_start()
        tracker.on_pullback_tick(
            18000, 18000, near_vwap=True, vol_dried_up=True
        )
        self.assertEqual(tracker.stats.blocked_vwap_only, 0)
        self.assertEqual(tracker.stats.blocked_vol_only, 0)
        self.assertEqual(tracker.stats.blocked_both, 0)

    def test_truth_table_all_four_combos(self):
        """Each (near_vwap, vol_dried_up) maps to one bucket per man.py semantics."""
        cases = [
            ((True, True), None),
            ((True, False), "blocked_vol_only"),
            ((False, True), "blocked_vwap_only"),
            ((False, False), "blocked_both"),
        ]
        for (near, dried), expected in cases:
            tracker = NearMissTracker()
            tracker.on_momentum_start()
            tracker.on_pullback_tick(18000, 18000, near_vwap=near, vol_dried_up=dried)
            for field in (
                "blocked_vol_only",
                "blocked_vwap_only",
                "blocked_both",
            ):
                value = getattr(tracker.stats, field)
                if expected == field:
                    self.assertEqual(value, 1, f"({near},{dried}) → {field}")
                else:
                    self.assertEqual(value, 0, f"({near},{dried}) not {field}")


class TestDailyObservability(unittest.TestCase):
    def test_daily_summary_includes_params_and_fills(self):
        obs = DailyObservability()
        obs.record_momentum_trigger()
        obs.record_entry_signal()
        obs.record_fill(
            intent="entry",
            direction="Buy",
            signal_price=18000,
            fill_price=18001,
            is_buy=True,
            limit_price=18003,
            order_id="o1",
            ts=100,
            ioc_slippage_allowed=3,
        )
        obs.record_fill(
            intent="exit",
            direction="Sell",
            signal_price=18010,
            fill_price=18008,
            is_buy=False,
            limit_price=18007,
            order_id="o2",
            ts=110,
            ioc_slippage_allowed=3,
            exit_reason="stop_loss",
            pnl_points=8,
            hold_sec=10,
        )
        obs.update_risk_state(8, 0)
        summary = obs.build_summary("2026-06-10")

        self.assertEqual(summary["date"], "2026-06-10")
        self.assertIn("entry_band_points", summary["params"])
        self.assertEqual(summary["fills"]["entry_count"], 1)
        self.assertEqual(summary["pnl"]["by_reason"]["stop_loss"]["avg_pnl"], 8.0)
        self.assertEqual(summary["quick_stop_loss"]["count"], 0)

    def test_exit_fill_clears_entry_tracking_scalars(self):
        obs = DailyObservability()
        obs.record_fill(
            intent="entry",
            direction="Buy",
            signal_price=18000,
            fill_price=18000,
            is_buy=True,
            limit_price=18003,
            order_id="o1",
            ts=100,
            ioc_slippage_allowed=3,
        )
        self.assertEqual(obs._entry_fill_ts, 100)
        obs.record_fill(
            intent="exit",
            direction="Sell",
            signal_price=18010,
            fill_price=18010,
            is_buy=False,
            limit_price=18007,
            order_id="o2",
            ts=120,
            ioc_slippage_allowed=3,
            exit_reason="take_profit",
            pnl_points=10,
            hold_sec=20,
        )
        self.assertEqual(obs._entry_fill_ts, 0)
        self.assertEqual(obs._entry_signal_price, 0.0)

    def test_config_snapshot_has_strategy_keys(self):
        snap = build_config_snapshot()
        self.assertIn("hard_stop_points", snap)
        self.assertIn("vwap_stop_points", snap)


if __name__ == "__main__":
    unittest.main()
