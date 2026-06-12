"""P1-2: opening volume ladder and vol_threshold tests."""

from __future__ import annotations

import datetime
import unittest

from config import (
    ATR_VOL_MULT,
    BASE_VOL,
    OPEN_MULT_FUTURES,
    OPEN_MULT_NORMAL,
    OPEN_MULT_SPOT,
)
from exchange_time import compute_vol_threshold, opening_session_multiplier


def _dt(hour: int, minute: int, second: int = 0) -> datetime.datetime:
    return datetime.datetime(2026, 6, 10, hour, minute, second)


class TestOpeningSessionMultiplier(unittest.TestCase):
    def test_futures_window_includes_085959(self):
        mult = opening_session_multiplier(
            _dt(8, 59, 59),
            mult_futures=2.5,
            mult_spot=1.5,
            mult_normal=1.0,
        )
        self.assertEqual(mult, 2.5)

    def test_spot_window_starts_at_090000(self):
        mult = opening_session_multiplier(
            _dt(9, 0, 0),
            mult_futures=2.5,
            mult_spot=1.5,
            mult_normal=1.0,
        )
        self.assertEqual(mult, 1.5)

    def test_spot_window_includes_091459(self):
        mult = opening_session_multiplier(
            _dt(9, 14, 59),
            mult_futures=2.5,
            mult_spot=1.5,
            mult_normal=1.0,
        )
        self.assertEqual(mult, 1.5)

    def test_normal_from_091500(self):
        mult = opening_session_multiplier(
            _dt(9, 15, 0),
            mult_futures=2.5,
            mult_spot=1.5,
            mult_normal=1.0,
        )
        self.assertEqual(mult, 1.0)

    def test_futures_window_starts_at_084500(self):
        mult = opening_session_multiplier(
            _dt(8, 45, 0),
            mult_futures=2.5,
            mult_spot=1.5,
            mult_normal=1.0,
        )
        self.assertEqual(mult, 2.5)


class TestVolThreshold(unittest.TestCase):
    def test_uses_base_vol_floor(self):
        base, mult, threshold = compute_vol_threshold(
            current_atr=10.0,
            dt=_dt(10, 0),
            base_vol=BASE_VOL,
            atr_vol_mult=ATR_VOL_MULT,
            mult_futures=OPEN_MULT_FUTURES,
            mult_spot=OPEN_MULT_SPOT,
            mult_normal=OPEN_MULT_NORMAL,
        )
        self.assertEqual(base, BASE_VOL)
        self.assertEqual(mult, OPEN_MULT_NORMAL)
        self.assertEqual(threshold, BASE_VOL * OPEN_MULT_NORMAL)

    def test_atr_raises_base_above_floor(self):
        base, mult, threshold = compute_vol_threshold(
            current_atr=200.0,
            dt=_dt(10, 0),
            base_vol=BASE_VOL,
            atr_vol_mult=ATR_VOL_MULT,
            mult_futures=OPEN_MULT_FUTURES,
            mult_spot=OPEN_MULT_SPOT,
            mult_normal=OPEN_MULT_NORMAL,
        )
        self.assertEqual(base, 200.0)
        self.assertEqual(threshold, 200.0)

    def test_opening_multiplier_scales_threshold(self):
        _, mult, threshold = compute_vol_threshold(
            current_atr=30.0,
            dt=_dt(8, 50),
            base_vol=BASE_VOL,
            atr_vol_mult=ATR_VOL_MULT,
            mult_futures=OPEN_MULT_FUTURES,
            mult_spot=OPEN_MULT_SPOT,
            mult_normal=OPEN_MULT_NORMAL,
        )
        self.assertEqual(mult, OPEN_MULT_FUTURES)
        self.assertEqual(threshold, 150.0 * OPEN_MULT_FUTURES)


if __name__ == "__main__":
    unittest.main()
