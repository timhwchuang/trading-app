"""Phase 3 + 6.1/6.5/6.7: MockBroker heuristic matching tests."""

from __future__ import annotations

import datetime
import tempfile
import unittest
from pathlib import Path
import shioaji as sj
from shioaji import OrderState

from config import MOMENTUM_VOL_1S
from storage.kbar_loader import KBarRecord, save_kbars_csv
from storage.tick_loader import ReplayTick
from backtest.mock_broker import MockBroker
from tests.test_helpers import make_host


def _make_buy_order(limit: float) -> sj.FuturesOrder:
    return sj.FuturesOrder(
        action=sj.Action.Buy,
        price=limit,
        quantity=1,
        price_type=sj.FuturesPriceType.LMT,
        order_type=sj.OrderType.IOC,
        octype=sj.FuturesOCType.Auto,
        account=None,
    )


def _make_sell_order(limit: float) -> sj.FuturesOrder:
    return sj.FuturesOrder(
        action=sj.Action.Sell,
        price=limit,
        quantity=1,
        price_type=sj.FuturesPriceType.LMT,
        order_type=sj.OrderType.IOC,
        octype=sj.FuturesOCType.Auto,
        account=None,
    )


class _RecordingStrategy:
    def __init__(self) -> None:
        self.events: list[tuple] = []
        self.pending_intent = "entry"
        self.pending_order_id: str | None = None
        self.is_pending = False

    def handle_order_event(self, stat, msg) -> None:
        self.events.append((stat, msg))


class TestMockBrokerMatching(unittest.TestCase):
    def _broker_at(self, epoch: float, **kwargs) -> MockBroker:
        return MockBroker(clock=lambda: epoch, **kwargs)

    def _place_and_match(
        self,
        broker: MockBroker,
        strategy: _RecordingStrategy,
        order: sj.FuturesOrder,
        tick: ReplayTick,
    ) -> list[tuple]:
        contract = broker.resolve_contract("TXFR1")
        trade = broker.place_order(contract, order)
        strategy.pending_order_id = str(trade.order.id)
        strategy.is_pending = True
        broker.current_dt = tick.datetime
        broker.process_matching_queue(tick, strategy)
        return strategy.events

    def test_buy_fill_normal_slip(self):
        epoch = datetime.datetime(2026, 6, 12, 9, 0, 0).timestamp()
        broker = self._broker_at(epoch, latency_ms=0)
        strategy = _RecordingStrategy()
        tick = ReplayTick(
            datetime.datetime(2026, 6, 12, 9, 0, 0), "18000", 1, 1
        )
        events = self._place_and_match(
            broker, strategy, _make_buy_order(18003), tick
        )
        deals = [e for e in events if e[0] == OrderState.FuturesDeal]
        self.assertEqual(len(deals), 1)
        self.assertAlmostEqual(deals[0][1]["price"], 18000.5)

    def test_buy_cancel_when_close_above_limit(self):
        epoch = datetime.datetime(2026, 6, 12, 9, 0, 0).timestamp()
        broker = self._broker_at(epoch, latency_ms=0)
        strategy = _RecordingStrategy()
        tick = ReplayTick(
            datetime.datetime(2026, 6, 12, 9, 0, 0), "18010", 1, 1
        )
        events = self._place_and_match(
            broker, strategy, _make_buy_order(18003), tick
        )
        cancels = [e for e in events if e[0] == OrderState.FuturesOrder]
        deals = [e for e in events if e[0] == OrderState.FuturesDeal]
        self.assertEqual(len(cancels), 1)
        self.assertEqual(len(deals), 0)

    def test_sell_fill(self):
        epoch = datetime.datetime(2026, 6, 12, 9, 0, 0).timestamp()
        broker = self._broker_at(epoch, latency_ms=0)
        strategy = _RecordingStrategy()
        tick = ReplayTick(
            datetime.datetime(2026, 6, 12, 9, 0, 0), "18000", 1, 2
        )
        events = self._place_and_match(
            broker, strategy, _make_sell_order(17997), tick
        )
        deals = [e for e in events if e[0] == OrderState.FuturesDeal]
        self.assertEqual(len(deals), 1)
        self.assertAlmostEqual(deals[0][1]["price"], 17999.5)

    def test_blowout_slippage(self):
        epoch = datetime.datetime(2026, 6, 12, 9, 0, 0).timestamp()
        broker = self._broker_at(epoch, latency_ms=0)
        strategy = _RecordingStrategy()
        tick = ReplayTick(
            datetime.datetime(2026, 6, 12, 9, 0, 0),
            "18000",
            MOMENTUM_VOL_1S + 1,
            1,
        )
        events = self._place_and_match(
            broker, strategy, _make_buy_order(18003), tick
        )
        deals = [e for e in events if e[0] == OrderState.FuturesDeal]
        self.assertAlmostEqual(deals[0][1]["price"], 18002.5)

    def test_latency_gate(self):
        base = datetime.datetime(2026, 6, 12, 9, 0, 0)
        clock_val = {"t": base.timestamp()}
        broker = MockBroker(clock=lambda: clock_val["t"], latency_ms=15)
        strategy = _RecordingStrategy()
        contract = broker.resolve_contract("TXFR1")
        trade = broker.place_order(contract, _make_buy_order(18003))
        strategy.pending_order_id = str(trade.order.id)
        strategy.is_pending = True

        same_tick = ReplayTick(base, "18000", 1, 1)
        broker.current_dt = same_tick.datetime
        broker.process_matching_queue(same_tick, strategy)
        self.assertEqual(strategy.events, [])

        clock_val["t"] = base.timestamp() + 0.02
        later_tick = ReplayTick(base.replace(microsecond=20000), "18000", 1, 1)
        broker.current_dt = later_tick.datetime
        broker.process_matching_queue(later_tick, strategy)
        deals = [e for e in strategy.events if e[0] == OrderState.FuturesDeal]
        self.assertEqual(len(deals), 1)

    def test_no_lookahead_kbars(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            code = "TXFR1"
            day = datetime.date(2026, 6, 12)
            bars = [
                KBarRecord(
                    datetime.datetime(2026, 6, 12, 9, 0),
                    18000,
                    18010,
                    17990,
                    18005,
                    100,
                ),
                KBarRecord(
                    datetime.datetime(2026, 6, 12, 9, 1),
                    18005,
                    18015,
                    17995,
                    18010,
                    100,
                ),
                KBarRecord(
                    datetime.datetime(2026, 6, 12, 9, 2),
                    18010,
                    18020,
                    18000,
                    18015,
                    100,
                ),
            ]
            from storage.kbar_loader import kbars_cache_path

            save_kbars_csv(bars, kbars_cache_path(cache_dir, code, day))
            broker = MockBroker(clock=lambda: 0.0, cache_dir=cache_dir)
            contract = broker.resolve_contract(code)
            broker.current_dt = datetime.datetime(2026, 6, 12, 9, 0, 30)
            kb_mid = broker.kbars(contract, day.isoformat(), day.isoformat())
            self.assertEqual(len(kb_mid.Close), 0)
            broker.current_dt = datetime.datetime(2026, 6, 12, 9, 1, 0)
            kb_closed = broker.kbars(contract, day.isoformat(), day.isoformat())
            self.assertEqual(len(kb_closed.Close), 1)
            self.assertEqual(kb_closed.Close[-1], 18005.0)

    def test_fill_never_worse_than_limit(self):
        epoch = datetime.datetime(2026, 6, 12, 13, 44, 0).timestamp()
        broker = self._broker_at(epoch, latency_ms=0, FLATTEN_SLIP=8.0)
        strategy = _RecordingStrategy()
        strategy.pending_intent = "exit"
        tick = ReplayTick(
            datetime.datetime(2026, 6, 12, 13, 44, 0), "18000", 1, 1
        )
        events = self._place_and_match(
            broker, strategy, _make_buy_order(18003), tick
        )
        deals = [e for e in events if e[0] == OrderState.FuturesDeal]
        self.assertEqual(len(deals), 1)
        self.assertLessEqual(deals[0][1]["price"], 18003)
        self.assertAlmostEqual(deals[0][1]["price"], 18003)

        strategy2 = _RecordingStrategy()
        strategy2.pending_intent = "exit"
        tick2 = ReplayTick(
            datetime.datetime(2026, 6, 12, 13, 44, 0), "18000", 1, 2
        )
        events2 = self._place_and_match(
            broker, strategy2, _make_sell_order(17997), tick2
        )
        deals2 = [e for e in events2 if e[0] == OrderState.FuturesDeal]
        self.assertGreaterEqual(deals2[0][1]["price"], 17997)

    def test_atr_available_on_first_tick(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            code = "TXFR1"
            prev = datetime.date(2026, 6, 11)
            today = datetime.date(2026, 6, 12)
            from storage.kbar_loader import kbars_cache_path

            prev_bars = [
                KBarRecord(
                    datetime.datetime(2026, 6, 11, 13, 30) + datetime.timedelta(minutes=i),
                    18000 + i,
                    18010 + i,
                    17990 + i,
                    18005 + i,
                    50,
                )
                for i in range(25)
            ]
            save_kbars_csv(prev_bars, kbars_cache_path(cache_dir, code, prev))
            clock_val = {
                "t": datetime.datetime(2026, 6, 12, 8, 45, 0).timestamp()
            }
            broker = MockBroker(clock=lambda: clock_val["t"], cache_dir=cache_dir)
            broker.current_dt = datetime.datetime(2026, 6, 12, 8, 45, 0)
            host = make_host()
            host.api = broker
            host.contract = broker.resolve_contract(code)
            host._last_tick_exchange_dt = datetime.datetime(2026, 6, 12, 8, 45, 0)
            host.refresh_atr()
            self.assertGreater(host.current_atr, 0)

    def test_spread_calibration_optional(self):
        epoch = datetime.datetime(2026, 6, 12, 9, 0, 0).timestamp()
        tick = ReplayTick(
            datetime.datetime(2026, 6, 12, 9, 0, 0),
            "18000",
            1,
            1,
            bid_price=17998.0,
            ask_price=18004.0,
        )
        broker_off = self._broker_at(epoch, latency_ms=0, spread_calibration=False)
        strategy_off = _RecordingStrategy()
        events_off = self._place_and_match(
            broker_off, strategy_off, _make_buy_order(18003), tick
        )
        fill_off = [
            e for e in events_off if e[0] == OrderState.FuturesDeal
        ][0][1]["price"]

        broker_on = self._broker_at(epoch, latency_ms=0, spread_calibration=True)
        strategy_on = _RecordingStrategy()
        events_on = self._place_and_match(
            broker_on, strategy_on, _make_buy_order(18003), tick
        )
        fill_on = [
            e for e in events_on if e[0] == OrderState.FuturesDeal
        ][0][1]["price"]
        self.assertAlmostEqual(fill_off, 18000.5)
        self.assertAlmostEqual(fill_on, 18003.0)


if __name__ == "__main__":
    unittest.main()
