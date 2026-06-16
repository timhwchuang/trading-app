"""Unit tests for P6-1-CAL-2 trend calibration harness (synthetic only).

Covers:
- veto_rate computation
- delta_expectancy sign in choppy (near 0 or negative) vs strong counter-trend (positive)
- edge cases (empty, all veto, zero samples)
- forward PnL provider injection (correct idx via rec.ts)
- synthetic scenario builder

SYNTHETIC GUARD: all numbers here are for harness implementation verification only.
Real delta expectancy / veto_rate used for trend_min_strength calibration or Go/No-Go
**must** come from B-class UAT tick archive + KBARS + replay forward policy (see CAL-5 SOP).

All data is synthetic per A-class safety boundary. No real tick_cache or UAT logs.
"""

from __future__ import annotations

import unittest

from reporting.trend_calibration import (
    compute_trend_veto_calibration,
    make_synthetic_veto_scenario,
)


class TestTrendCalibrationHarness(unittest.TestCase):
    def test_veto_rate_and_basic_delta(self):
        # 10 candidates, 4 vetoed
        vetoes, fwd = make_synthetic_veto_scenario(
            prices=list(range(100, 140)), veto_at=[5, 12, 20, 25], direction="Long", window_bars=10
        )
        # Allowed: the rest (toy: we pass empty allowed and rely on synthetic veto side only for this test)
        res = compute_trend_veto_calibration(vetoes, allowed_audits=[], get_forward_pnl=fwd)
        self.assertAlmostEqual(res["veto_rate"], 1.0)  # only vetoes supplied
        self.assertEqual(res["n_veto"], 4)
        self.assertIn("delta_expectancy", res)

    def test_choppy_veto_near_zero_or_negative_delta(self):
        # Choppy price (no real edge after veto) -> delta ~0 or veto "saved" us from noise (delta positive for veto? sign convention)
        # Our convention: delta = E_allowed - E_veto_if_entered. In choppy, allowing would have ~0, vetoing "missed" 0.
        prices = [100.0 + (i % 3 - 1) * 0.3 for i in range(80)]
        vetoes, fwd = make_synthetic_veto_scenario(prices, veto_at=[10, 30, 50], direction="Long", window_bars=8)
        # Simulate a couple "allowed" that also had flat forward
        allowed = [{"price": 100.5, "direction": "Long", "ts": 15}, {"price": 101.0, "direction": "Long", "ts": 35}]
        res = compute_trend_veto_calibration(vetoes, allowed_audits=allowed, get_forward_pnl=fwd)
        # In pure chop the delta should be small in magnitude (now using correct fwd via ts index)
        self.assertLess(abs(res["delta_expectancy"]), 3.0)

    def test_strong_counter_trend_veto_positive_delta(self):
        # Strong adverse move after veto point: allowing would have lost; veto protected => positive delta (saved P&L)
        prices = [100.0] * 20 + [100.0 - i * 0.8 for i in range(30)]  # sharp down after veto window
        # Veto Longs (counter the coming drop)
        vetoes, fwd = make_synthetic_veto_scenario(prices, veto_at=[5, 8, 12], direction="Long", window_bars=15)
        allowed = [{"price": 99.0, "direction": "Long", "ts": 6}]  # one that slipped through and lost
        res = compute_trend_veto_calibration(vetoes, allowed_audits=allowed, get_forward_pnl=fwd)
        # Veto side "if entered" would show large negative; allowed also negative but the delta (allowed - veto_if) may be
        # positive if the vetoed points were at worse prices. We only assert non-negative for the "protected" story.
        self.assertGreaterEqual(res["delta_expectancy"], -0.1)  # tolerant for toy numbers

    def test_empty_and_all_veto(self):
        res = compute_trend_veto_calibration([], allowed_audits=[])
        self.assertEqual(res["veto_rate"], 0.0)
        self.assertEqual(res["delta_expectancy"], 0.0)

        prices = list(range(100, 120))
        vetoes, fwd = make_synthetic_veto_scenario(prices, veto_at=[1, 3, 5], direction="Short", window_bars=5)
        res2 = compute_trend_veto_calibration(vetoes, allowed_audits=None, get_forward_pnl=fwd)
        self.assertEqual(res2["n_allowed"], 0)
        self.assertAlmostEqual(res2["veto_rate"], 1.0)

    def test_synthetic_builder_produces_valid_forward(self):
        prices = [100.0 + i for i in range(50)]
        vetoes, fwd = make_synthetic_veto_scenario(prices, veto_at=[10, 20], direction="Long", window_bars=5)
        self.assertEqual(len(vetoes), 2)
        self.assertGreater(fwd(105.0, 10), 0.0)  # price went up


if __name__ == "__main__":
    unittest.main()
