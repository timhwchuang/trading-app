"""B-class forward PnL from tick_cache replay."""

from __future__ import annotations

import datetime
import unittest
from pathlib import Path

from reporting.forward_pnl import ForwardPnlPolicy, load_tick_series, make_replay_forward_pnl

_FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "ticks"
_DAY = datetime.date(2026, 6, 12)
_ENTRY_TS = int(datetime.datetime(2026, 6, 12, 9, 0, 0).timestamp())


class TestForwardPnlReplay(unittest.TestCase):
    def test_load_fixture_ticks(self):
        series = load_tick_series("TXFR1", [_DAY], cache_dir=_FIXTURE_DIR)
        self.assertGreater(len(series), 0)
        self.assertEqual(series.timestamps[0], _ENTRY_TS)

    def test_long_forward_positive_on_uptrend(self):
        series = load_tick_series("TXFR1", [_DAY], cache_dir=_FIXTURE_DIR)
        fwd = make_replay_forward_pnl(
            series, ForwardPnlPolicy(mode="fixed_seconds", window_seconds=1800)
        )
        pnl = fwd(100.0, _ENTRY_TS, "Buy")
        self.assertGreater(pnl, 0.0)

    def test_short_forward_negative_on_uptrend(self):
        series = load_tick_series("TXFR1", [_DAY], cache_dir=_FIXTURE_DIR)
        fwd = make_replay_forward_pnl(
            series, ForwardPnlPolicy(mode="fixed_seconds", window_seconds=1800)
        )
        pnl = fwd(100.0, _ENTRY_TS, "Sell")
        self.assertLess(pnl, 0.0)

    def test_session_end_mode(self):
        series = load_tick_series("TXFR1", [_DAY], cache_dir=_FIXTURE_DIR)
        fwd = make_replay_forward_pnl(
            series,
            ForwardPnlPolicy(mode="session_end", session_end=datetime.time(13, 45)),
        )
        pnl = fwd(100.0, _ENTRY_TS, "Buy")
        self.assertGreater(pnl, 0.0)


if __name__ == "__main__":
    unittest.main()