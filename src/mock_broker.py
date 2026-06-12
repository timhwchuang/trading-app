"""Phase 3: Heuristic IOC matching for backtesting (close-based, latency + slippage)."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Callable, List, Optional

import shioaji as sj
from shioaji import OrderState

from config import MOMENTUM_VOL_1S, SESSION_FORCE_FLATTEN_TIME
from data_loader import DEFAULT_CACHE_DIR, iter_kbars_in_range
from exchange_time import is_at_or_after


@dataclass
class _KBars:
    High: List[float]
    Low: List[float]
    Close: List[float]


class MockBroker:
    """Minimal Shioaji api stand-in for backtest replay."""

    def __init__(
        self,
        clock: Callable[[], float],
        *,
        latency_ms: int = 15,
        NORMAL_SLIP: float = 0.5,
        BLOWOUT_VOL: int = MOMENTUM_VOL_1S,
        BLOWOUT_SLIP: float = 2.5,
        FLATTEN_SLIP: float = 8.0,
        cache_dir=DEFAULT_CACHE_DIR,
        spread_calibration: bool = False,
    ) -> None:
        self.clock = clock
        self.latency_ms = latency_ms
        self.NORMAL_SLIP = NORMAL_SLIP
        self.BLOWOUT_VOL = BLOWOUT_VOL
        self.BLOWOUT_SLIP = BLOWOUT_SLIP
        self.FLATTEN_SLIP = FLATTEN_SLIP
        self.cache_dir = cache_dir
        self.spread_calibration = spread_calibration
        self.futopt_account = None
        self._seq = 0
        self.inflight: list[dict[str, Any]] = []
        self.current_dt: Optional[datetime.datetime] = None

    def resolve_contract(self, code: str) -> SimpleNamespace:
        return SimpleNamespace(code=code)

    def place_order(self, contract: Any, order: Any, timeout: int = 0) -> SimpleNamespace:
        self._seq += 1
        order_id = f"BT{self._seq}"
        self.inflight.append(
            {
                "order_id": order_id,
                "action": "Buy" if order.action == sj.Action.Buy else "Sell",
                "limit_price": float(order.price),
                "quantity": int(order.quantity),
                "arrive_after": self.clock() + self.latency_ms / 1000.0,
            }
        )
        return SimpleNamespace(order=SimpleNamespace(id=order_id))

    def update_status(self, trade: Any = None) -> None:
        pass

    def order_deal_records(self) -> list:
        return []

    def usage(self) -> SimpleNamespace:
        return SimpleNamespace(bytes=0, limit_bytes=0, remaining_bytes=0, connections=0)

    def kbars(self, contract: Any, start: str, end: str) -> _KBars:
        code = getattr(contract, "code", str(contract))
        start_date = datetime.date.fromisoformat(start)
        end_date = datetime.date.fromisoformat(end)
        bars = iter_kbars_in_range(code, start_date, end_date, cache_dir=self.cache_dir)
        current = self.current_dt
        highs: List[float] = []
        lows: List[float] = []
        closes: List[float] = []
        for bar in bars:
            if current is not None:
                if bar.ts > current:
                    continue
                # Only fully closed 1-minute bars (R-3): bar end <= current_dt
                if bar.ts + datetime.timedelta(minutes=1) > current:
                    continue
            highs.append(bar.High)
            lows.append(bar.Low)
            closes.append(bar.Close)
        return _KBars(High=highs, Low=lows, Close=closes)

    def _slippage_for(
        self,
        tick: Any,
        intent: Optional[str],
        base_slippage: float,
    ) -> float:
        slippage = base_slippage
        if tick.volume > self.BLOWOUT_VOL:
            slippage = self.BLOWOUT_SLIP
        if intent == "exit" and is_at_or_after(tick.datetime, SESSION_FORCE_FLATTEN_TIME):
            slippage = self.FLATTEN_SLIP
        if self.spread_calibration:
            ask = getattr(tick, "ask_price", None)
            bid = getattr(tick, "bid_price", None)
            if ask and bid and ask > bid:
                half_spread = (ask - bid) / 2.0
                slippage = max(slippage, half_spread)
        return slippage

    def _intent_for(self, strategy: Any, order_id: str) -> Optional[str]:
        if getattr(strategy, "pending_order_id", None) == order_id:
            return getattr(strategy, "pending_intent", None)
        return None

    def process_matching_queue(self, tick: Any, strategy: Any) -> None:
        tick_ts = tick.datetime.timestamp()
        for ord in list(self.inflight):
            if tick_ts < ord["arrive_after"]:
                continue
            self.inflight.remove(ord)
            intent = self._intent_for(strategy, ord["order_id"])
            slippage = self._slippage_for(tick, intent, self.NORMAL_SLIP)
            close = float(tick.close)
            limit = ord["limit_price"]
            is_buy = ord["action"] == "Buy"
            if is_buy:
                if close <= limit:
                    fill = min(limit, close + slippage)
                else:
                    fill = None
            else:
                if close >= limit:
                    fill = max(limit, close - slippage)
                else:
                    fill = None
            if fill is None:
                strategy.handle_order_event(
                    OrderState.FuturesOrder,
                    {
                        "operation": {"op_code": "00", "op_type": "Cancel"},
                        "status": {"status": "Cancelled", "deal_quantity": 0},
                        "trade_id": ord["order_id"],
                    },
                )
            else:
                strategy.handle_order_event(
                    OrderState.FuturesDeal,
                    {
                        "price": fill,
                        "quantity": ord["quantity"],
                        "action": ord["action"],
                        "trade_id": ord["order_id"],
                    },
                )
