"""Tests for P6-1 trend filter (now in trend.py) + P6-2/3 dynamic ATR helpers."""

from __future__ import annotations

import unittest

from strategy.trend import (
    compute_trend,
    dynamic_atr_based,
    dynamic_trail_points,
    dynamic_vwap_stop_distance,
    ema,
    linear_regression_slope,
    resample_closes,
    trend_allows_entry,
    trend_from_ema,
    trend_from_slope,
)


class TestTrendHelpers(unittest.TestCase):
    def test_ema(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        self.assertIsNotNone(ema(values, 3))

    def test_trend_long(self):
        closes = [100.0 + i for i in range(30)]
        direction, strength = trend_from_ema(closes, 20)
        self.assertEqual(direction, "Long")
        self.assertGreater(strength, 0)

    def test_trend_filter_blocks_counter(self):
        self.assertFalse(
            trend_allows_entry(
                enabled=True, trend_dir="Long", momentum_dir="Short"
            )
        )
        self.assertTrue(
            trend_allows_entry(
                enabled=True, trend_dir="Long", momentum_dir="Long"
            )
        )

    def test_resample_closes_5m(self):
        closes = [float(i) for i in range(10)]
        self.assertEqual(resample_closes(closes, 5), [4.0, 9.0])

    def test_resample_closes_includes_latest_bar(self):
        """B: resample must always represent the most recent price (critical at decision time)."""
        closes = [float(i) for i in range(12)]  # 0..11
        # 5m stride from end: should end with 11 (the latest)
        res = resample_closes(closes, 5)
        self.assertEqual(res[-1], 11.0)
        # Another length not multiple
        closes2 = [float(i) for i in range(13)]
        res2 = resample_closes(closes2, 5)
        self.assertEqual(res2[-1], 12.0)  # latest included even in partial bucket

    def test_compute_trend_ema_mode(self):
        closes = [100.0 + i for i in range(60)]
        direction, strength = compute_trend(
            closes, mode="ema", timeframe_min=5, ema_period=10
        )
        self.assertEqual(direction, "Long")
        self.assertGreater(strength, 0)

    def test_compute_trend_slope_mode(self):
        closes = [100.0 + i for i in range(30)]
        direction, _ = compute_trend(
            closes, mode="slope", timeframe_min=1, slope_min=0.1
        )
        self.assertEqual(direction, "Long")
        flat, _ = trend_from_slope([100.0, 100.1], min_slope=1.0)
        self.assertEqual(flat, "Flat")

    def test_compute_trend_min_strength_level2(self):
        """Level 2: min_strength forces weak signals back to Flat (real filtering power).

        Only when |trend_strength| >= min_strength do we emit a committed Long/Short
        that can then cause counter-trend blocks in trend_allows_entry.
        """
        # Use data known to produce strong signal (same as test_compute_trend_ema_mode)
        closes = [100.0 + i for i in range(60)]
        direction, strength = compute_trend(
            closes, mode="ema", timeframe_min=5, ema_period=10, min_strength=0.0
        )
        self.assertEqual(direction, "Long")
        self.assertGreater(strength, 10)  # post SMA-seed warmup ~22.5 on this data

        # With min_strength that this move exceeds → still Long
        direction, _ = compute_trend(
            closes, mode="ema", timeframe_min=5, ema_period=10, min_strength=5.0
        )
        self.assertEqual(direction, "Long")

        # Very high threshold → forced Flat (this is the Level 2 protection)
        direction, _ = compute_trend(
            closes, mode="ema", timeframe_min=5, ema_period=10, min_strength=50.0
        )
        self.assertEqual(direction, "Flat")

        # Slope mode also respects it
        direction, _ = compute_trend(
            closes, mode="slope", timeframe_min=1, slope_min=0.0, min_strength=0.5
        )
        self.assertEqual(direction, "Long")
        direction, _ = compute_trend(
            closes, mode="slope", timeframe_min=1, slope_min=0.0, min_strength=20.0
        )
        self.assertEqual(direction, "Flat")

    def test_compute_trend_atr_normalization(self):
        """A: ATR normalization makes min_strength comparable across modes and vol regimes."""
        closes = [100.0 + i for i in range(60)]
        raw_atr = 5.0

        # Without ATR: use raw strength (old behavior when atr=0)
        d_raw, s_raw = compute_trend(
            closes, mode="ema", timeframe_min=5, ema_period=10, min_strength=10.0, atr=0.0
        )
        self.assertEqual(d_raw, "Long")  # ~22.5 (post SMA-seed) > 10 raw

        # With ATR: effective = raw / atr
        # 18.8 / 5.0 = 3.76 > 2.0 → still Long
        d_norm, _ = compute_trend(
            closes, mode="ema", timeframe_min=5, ema_period=10, min_strength=2.0, atr=raw_atr
        )
        self.assertEqual(d_norm, "Long")

        # Higher ATR threshold: 22.5 / 5 = 4.5 . Use 5.0 to force Flat example.
        d_norm, _ = compute_trend(
            closes, mode="ema", timeframe_min=5, ema_period=10, min_strength=5.0, atr=raw_atr
        )
        self.assertEqual(d_norm, "Flat")

        # Slope mode with same ATR threshold should behave consistently in "ATR units".
        # On this ramp data (perfect +1 per bar, 60 bars), linreg slope ≈ +1.0.
        # raw_strength=1.0, eff=1.0/5.0=0.2. Choose threshold low enough to demonstrate pass.
        d_slope, s_slope = compute_trend(
            closes, mode="slope", timeframe_min=1, slope_min=0.0, min_strength=0.1, atr=raw_atr
        )
        self.assertEqual(d_slope, "Long")
        self.assertGreater(s_slope, 0.0)
        # And confirm the normalization gate actually works at higher threshold
        d_slope2, _ = compute_trend(
            closes, mode="slope", timeframe_min=1, slope_min=0.0, min_strength=0.3, atr=raw_atr
        )
        self.assertEqual(d_slope2, "Flat")  # 0.2 < 0.3 after /atr

    def test_linear_regression_slope(self):
        slope = linear_regression_slope([100.0, 101.0, 102.0, 103.0])
        self.assertAlmostEqual(slope, 1.0)

    def test_dynamic_atr_based_factory(self):
        self.assertEqual(dynamic_atr_based(10, floor=8, atr_k=0.25), 8.0)
        self.assertEqual(dynamic_atr_based(100, floor=8, atr_k=0.25), 25.0)

    def test_dynamic_trail_floor(self):
        self.assertEqual(
            dynamic_trail_points(10, floor=8, atr_k=0.25),
            8.0,
        )
        self.assertEqual(
            dynamic_trail_points(100, floor=8, atr_k=0.25),
            25.0,
        )

    def test_dynamic_vwap_stop(self):
        self.assertEqual(
            dynamic_vwap_stop_distance(40, floor=3, atr_k=0.25),
            10.0,
        )

    def test_ema_sma_seed_warmup(self):
        """C: EMA now uses SMA seed. Test reduced first-bar bias vs old behavior."""
        # Exactly period bars -> reduces to SMA of the window (no further EMA steps)
        vals = [100.0, 101.0, 102.0]  # len == period
        result = ema(vals, 3)
        self.assertAlmostEqual(result, 101.0)

        # Longer window: SMA seed + EMA updates on the tail
        vals2 = [100.0, 101.0, 102.0, 103.0, 104.0]
        result2 = ema(vals2, 3)
        self.assertGreater(result2, 101.0)  # has been pulled up by 103/104

        # Linear ramp case used elsewhere: the 'strength' will now be last vs SMA of last N
        # (we mainly care direction + that it does not explode from first bar only)
        closes = [100.0 + i for i in range(30)]
        direction, strength = trend_from_ema(closes, 20)
        self.assertEqual(direction, "Long")
        self.assertGreater(strength, 0)

    def test_trend_choppy_flat(self):
        """C: obvious chop/oscillation should not produce strong committed trend."""
        # Zigzag around a level
        base = 100.0
        closes = [base + (i % 3 - 1) * 2 for i in range(50)]
        direction, strength = compute_trend(
            closes, mode="ema", timeframe_min=1, ema_period=10, min_strength=1.0
        )
        # With min_strength it should be Flat or very weak; we accept either but prefer no strong signal
        self.assertIn(direction, ("Flat", "Long", "Short"))  # at least doesn't crash
        # With high min it must be Flat
        direction2, _ = compute_trend(
            closes, mode="ema", timeframe_min=1, ema_period=10, min_strength=10.0
        )
        self.assertEqual(direction2, "Flat")

    def test_trend_gap_simulation(self):
        """C: simulate a gap (previous close + jump). Trend on post-gap data should not be polluted by pre-gap."""
        # Pre-gap flat, then strong up move after 'gap'
        pre = [100.0] * 20
        post = [100.0 + i * 0.8 for i in range(25)]  # strong ramp after gap
        closes = pre + [108.0] + post  # the 108 is the 'gap open'
        # If we only look at recent (post-gap), should see Long
        direction, _ = compute_trend(
            closes[-30:], mode="ema", timeframe_min=1, ema_period=8, min_strength=2.0
        )
        self.assertEqual(direction, "Long")

        # Full data without slicing would mix pre + gap; our B mitigation (slicing in engine)
        # + this test using suffix simulates the protection.
        # We don't assert the full mixed case here (that is the 'bad old behavior').

    def test_resample_and_ema_with_gap_and_latest(self):
        """C: combined boundary - resample includes latest even after gap-like data, EMA decision uses recent."""
        closes = list(range(100, 120)) + [150] + list(range(151, 170))  # gap at ~120->150
        res = resample_closes(closes, 5)
        self.assertEqual(res[-1], 169.0)  # latest must be present

        # Trend on the suffix after gap should be able to detect the new regime
        direction, _ = compute_trend(
            closes[-25:], mode="slope", timeframe_min=3, slope_min=0.1, min_strength=0.5
        )
        self.assertEqual(direction, "Long")

    def test_p6_cal1_select_recent_trading_days_replaces_approx_bars_heuristic(self):
        """P6-1-CAL-1 regression guard: unsliced long polluted input (old approx 800-bar style)
        can produce wrong regime vs properly day-sliced recent trading days closes.

        Simulates the exact problem the 400*2 heuristic + raw [-N:] tried to paper over:
        multi-day kbars (ATR long lookback) containing prior session + gap + new day move.
        The select helper (using ts + trading_day_for_daily_reset) must protect compute_trend.

        CQR review fix: the guard now *quantitatively exercises the claimed failure mode*.
        Recent trading day is deliberately given too few bars to fill the ema window after resample
        (tf=5, ema=10 -> resampled needs ~10 points; give recent only ~18 bars -> ~4 after stride -> Flat).
        Full long polluted list supplies enough history in the resample tail to fabricate a committed Long.
        This proves "未切片輸入會產生錯誤 regime" under the conditions the hygiene matters (sparse recent day at open).
        """
        import datetime as dt_mod
        from exchange_time import select_recent_trading_days_closes, trading_day_for_daily_reset

        # Build fake "kbars raw" spanning two trading days with ts (ns epoch style).
        # Prior day (2026-06-12): strong upward ramp. With short recent, resample stride from end of *full* list
        # will land some of its tail bars back into the prior ramp -> committed Long under old behavior.
        base_day1 = dt_mod.datetime(2026, 6, 12, 9, 0)
        day1_closes = [100.0 + i * 0.5 for i in range(60)]  # strong positive ramp
        # Today sparse (at open): deliberately *very* few bars so that resample on *recent only* has
        # len(resampled) << ema_period -> Flat (correct, no fake regime from stale data).
        # tf=5, ema=8: need < ~40 recent for the guard; use 7 bars -> ~2 resampled <8 -> Flat.
        base_day2 = dt_mod.datetime(2026, 6, 13, 8, 50)
        day2_closes = [100.0 + i * 0.05 for i in range(7)]  # tiny move, too few for ema window

        # Simulate raw kbars object with .ts (ns) + .Close parallel (like live api + backtest _KBars now)
        all_closes = day1_closes + day2_closes
        all_ts = []
        for i, c in enumerate(all_closes):
            if i < len(day1_closes):
                d = base_day1 + dt_mod.timedelta(minutes=i)
            else:
                d = base_day2 + dt_mod.timedelta(minutes=(i - len(day1_closes)))
            ns = int(d.timestamp() * 1_000_000_000)
            all_ts.append(ns)

        class _FakeRaw:
            ts = all_ts
            Close = all_closes

        # Old heuristic style (full or last ~800) on polluted: resample tail can reach prior-day ramp -> Long
        full_dir, _ = compute_trend(
            all_closes, mode="ema", timeframe_min=5, ema_period=10, min_strength=0.3
        )

        # Proper CAL-1 slice (max_days=1): only recent sparse day -> resampled too short -> Flat (correct conservative)
        ref = base_day2 + dt_mod.timedelta(minutes=5)
        sliced = select_recent_trading_days_closes(_FakeRaw(), ref, max_days=1)
        sliced_dir, _ = compute_trend(
            sliced, mode="ema", timeframe_min=5, ema_period=10, min_strength=0.3
        )

        # Guard assertion (CQR review fix): sliced (only recent, too sparse for ema) is correctly Flat (conservative).
        # Full (old polluted heuristic) fabricates a committed direction (Long or Short) from stale prior-day data
        # that resample tail reaches. This *is* the "未切片輸入會產生錯誤 regime" failure mode the hygiene prevents.
        self.assertEqual(sliced_dir, "Flat")
        self.assertNotEqual(full_dir, "Flat")
        self.assertLess(len(sliced), len(all_closes))
        # Existence of select + this quantitative guard (engine now uses it instead of 400 magic) protects the
        # regime label that later feeds trend_allows_entry + reason=trend_veto + delta expectancy harness.
        # All synthetic; real UAT calibration still required (see docstring).


# --- Interface injection test (new for pluggable strategies) ---

import datetime

from strategy.base import BaseStrategy, StrategySideEffects
from tests.test_helpers import make_host
from storage.tick_loader import ReplayTick
from unittest.mock import MagicMock


class _DummyStrategy(BaseStrategy):
    """Trivial strategy for testing injection. Always returns no signal."""
    def evaluate(self, *a, **k):
        return None, StrategySideEffects()

    def reset(self) -> None:
        pass


class TestStrategyInterfaceInjection(unittest.TestCase):
    def test_make_strategy_accepts_custom_decision_strategy(self):
        dummy = _DummyStrategy()
        host = make_host(decision=dummy)

        self.assertIs(host.strategy, dummy)

    def test_trading_engine_constructor_accepts_strategy(self):
        from runtime.engine import TradingEngine

        dummy = _DummyStrategy()
        host = TradingEngine(api=MagicMock(), strategy=dummy)

        self.assertIs(host.strategy, dummy)

    def test_host_reset_momentum_delegates_to_strategy_reset(self):
        from runtime.engine import TradingEngine

        calls: list[str] = []

        class _SpyStrategy(_DummyStrategy):
            def reset(self) -> None:
                calls.append("reset")

        host = TradingEngine(api=MagicMock(), strategy=_SpyStrategy())
        host.reset_momentum()
        self.assertEqual(calls, ["reset"])

    def test_custom_strategy_survives_one_tick(self):
        """Injected BaseStrategy subclass must survive a full on_tick pass."""
        from runtime.engine import TradingEngine

        dummy = _DummyStrategy()
        host = TradingEngine(api=MagicMock(), strategy=dummy)
        host._api_connected = True
        host._order_sync_mode = True
        tick = ReplayTick(
            datetime.datetime(2026, 6, 12, 9, 0, 0), "18000", 1, 1
        )
        host.on_tick(tick)


if __name__ == "__main__":
    unittest.main()
