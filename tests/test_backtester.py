"""Phase 2 + 6.3/6.4: BacktestEngine replay loop tests."""

from __future__ import annotations

import datetime
import unittest
from unittest.mock import patch

from config import PENDING_TIMEOUT_SEC
from data_loader import ReplayTick
from backtester import BacktestEngine


class TestBacktestEngine(unittest.TestCase):
    def test_engine_runs_empty(self):
        engine = BacktestEngine("TXFR1", [datetime.date(2099, 1, 1)])
        engine.run()

    def test_clock_advances(self):
        ticks = [
            ReplayTick(datetime.datetime(2026, 6, 12, 9, 0, 0), "18000", 1, 0),
            ReplayTick(datetime.datetime(2026, 6, 12, 9, 0, 1), "18001", 1, 0),
        ]
        engine = BacktestEngine("TXFR1", [datetime.date(2026, 6, 12)])
        with patch("backtester.iter_replay_ticks", return_value=iter(ticks)):
            engine.run()
        self.assertEqual(
            engine.clock(), ticks[-1].datetime.timestamp()
        )

    def test_pending_timeout_before_tick_processing(self):
        t0 = datetime.datetime(2026, 6, 12, 9, 0, 0)
        t1 = datetime.datetime(2026, 6, 12, 9, 0, 10)
        tick1 = ReplayTick(t0, "18000", 1, 0)
        tick2 = ReplayTick(t1, "18001", 1, 0)
        engine = BacktestEngine("TXFR1", [t0.date()])
        pending_at_on_tick: list[bool] = []
        original_on_tick = engine.strategy.on_tick

        def spy_on_tick(tick):
            pending_at_on_tick.append(engine.strategy.is_pending)
            return original_on_tick(tick)

        engine.strategy.on_tick = spy_on_tick

        def fake_replay(_code, _dates, cache_dir=None):
            yield tick1
            engine.strategy.is_pending = True
            engine.strategy.pending_since = t0.timestamp()
            engine.strategy.pending_order_id = "BT1"
            engine.strategy.pending_intent = "entry"
            yield tick2

        with patch("backtester.iter_replay_ticks", fake_replay):
            engine.run()

        self.assertGreater(t1.timestamp() - t0.timestamp(), PENDING_TIMEOUT_SEC)
        self.assertEqual(len(pending_at_on_tick), 2)
        self.assertFalse(pending_at_on_tick[1])

    def test_premarket_ticks_are_filtered(self):
        ticks = [
            ReplayTick(datetime.datetime(2026, 6, 12, 8, 40), "17900", 100, 0),
            ReplayTick(datetime.datetime(2026, 6, 12, 8, 43), "17910", 100, 0),
            ReplayTick(datetime.datetime(2026, 6, 12, 8, 46), "18000", 1, 0),
        ]
        engine = BacktestEngine("TXFR1", [datetime.date(2026, 6, 12)])
        seen: list[datetime.datetime] = []
        original_on_tick = engine.strategy.on_tick

        def track(tick):
            seen.append(tick.datetime)
            return original_on_tick(tick)

        engine.strategy.on_tick = track
        with patch("backtester.iter_replay_ticks", return_value=iter(ticks)):
            engine.run()
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0].time(), datetime.time(8, 46))

    def test_premarket_tick_still_runs_matching(self):
        import shioaji as sj
        from shioaji import OrderState

        premarket_tick = ReplayTick(
            datetime.datetime(2026, 6, 12, 8, 40, 0), "18000", 1, 1
        )
        engine = BacktestEngine("TXFR1", [datetime.date(2026, 6, 12)])
        engine.broker.latency_ms = 0
        contract = engine.broker.resolve_contract("TXFR1")
        order = sj.FuturesOrder(
            action=sj.Action.Buy,
            price=18003,
            quantity=1,
            price_type=sj.FuturesPriceType.LMT,
            order_type=sj.OrderType.IOC,
            octype=sj.FuturesOCType.Auto,
            account=None,
        )
        trade = engine.broker.place_order(contract, order)
        engine.strategy.pending_order_id = str(trade.order.id)
        engine.strategy.pending_intent = "entry"
        engine.strategy.is_pending = True
        events: list[tuple] = []
        on_tick_times: list[datetime.time] = []
        original_handle = engine.strategy.handle_order_event
        original_on_tick = engine.strategy.on_tick

        def capture(stat, msg):
            events.append((stat, msg))
            return original_handle(stat, msg)

        def spy_on_tick(tick):
            on_tick_times.append(tick.datetime.time())
            return original_on_tick(tick)

        engine.strategy.handle_order_event = capture
        engine.strategy.on_tick = spy_on_tick

        def fake_replay(_code, _dates, cache_dir=None):
            yield premarket_tick

        with patch("backtester.iter_replay_ticks", fake_replay):
            engine.run()

        deals = [e for e in events if e[0] == OrderState.FuturesDeal]
        self.assertEqual(len(deals), 1)
        self.assertEqual(on_tick_times, [])
        self.assertLess(premarket_tick.datetime.time(), datetime.time(8, 45))


if __name__ == "__main__":
    unittest.main()
