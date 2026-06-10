import shioaji as sj
from shioaji import OrderState, TickFOPv1
import atexit
import time
import datetime
import logging
import logging.handlers
import queue
import sys
from collections import deque
import threading
from dataclasses import dataclass
from typing import Deque, List, Optional, Tuple

from exchange_time import (
    compute_vol_threshold,
    is_at_or_after,
    is_trading_session as _is_trading_session,
    trading_day_for_daily_reset,
)
from signal_audit import SignalAudit, format_signal_audit

from config import (
    API_KEY,
    ATR_KLINE_LOOKBACK_DAYS,
    ATR_PERIOD,
    ATR_REFRESH_SEC,
    ATR_VOL_MULT,
    BASE_VOL,
    CA_PASSWD,
    CA_PATH,
    COOLDOWN_SEC,
    EXHAUSTION_VOL,
    FIXED_TP_POINTS,
    FLATTEN_SLIPPAGE_POINTS,
    IOC_SLIPPAGE_POINTS,
    LOG_FILE,
    LOG_LEVEL,
    MAX_CONSECUTIVE_LOSS,
    MAX_DAILY_LOSS_POINTS,
    MIN_ATR_THRESHOLD,
    MOMENTUM_BUY_RATIO,
    MOMENTUM_SELL_RATIO,
    OPEN_MULT_FUTURES,
    OPEN_MULT_NORMAL,
    OPEN_MULT_SPOT,
    PENDING_TIMEOUT_SEC,
    PRODUCT_CODE,
    SECRET_KEY,
    SESSION_END,
    SESSION_FLATTEN_TIME,
    SESSION_FORCE_FLATTEN_TIME,
    SESSION_START,
    SIMULATION,
    TRAIL_POINTS,
    VWAP_WINDOW_MIN,
    settings,
)

_log_listener: Optional[logging.handlers.QueueListener] = None


class _NonBlockingQueueHandler(logging.handlers.QueueHandler):
    """Callback 路徑專用：queue 滿時丟棄 log，絕不阻塞 on_tick。"""

    def enqueue(self, record: logging.LogRecord) -> None:
        try:
            self.queue.put_nowait(record)
        except queue.Full:
            pass


def setup_async_logging(
    level: str = LOG_LEVEL,
    log_file: str = LOG_FILE,
) -> logging.Logger:
    """QueueHandler（非阻塞入隊）+ 背景 QueueListener 負責磁碟/終端 I/O。"""
    global _log_listener

    if _log_listener is not None:
        _log_listener.stop()
        _log_listener = None

    numeric_level = getattr(logging, level, logging.INFO)
    log_queue: queue.Queue = queue.Queue(-1)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(numeric_level)
    root.addHandler(_NonBlockingQueueHandler(log_queue))

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    sink_handlers: List[logging.Handler] = []
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    sink_handlers.append(stream_handler)

    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        sink_handlers.append(file_handler)

    _log_listener = logging.handlers.QueueListener(
        log_queue,
        *sink_handlers,
        respect_handler_level=True,
    )
    _log_listener.start()
    atexit.register(shutdown_async_logging)
    return logging.getLogger(__name__)


def shutdown_async_logging() -> None:
    global _log_listener
    if _log_listener is not None:
        _log_listener.stop()
        _log_listener = None


logger = setup_async_logging()


@dataclass
class OrderSignal:
    action: str   # "Buy" | "Sell"
    qty: int
    ref_price: float
    intent: str   # "entry" | "exit"
    exchange_ts: int = 0   # tick timestamp when signal was generated
    audit: Optional[SignalAudit] = None
    slippage_points: Optional[int] = None


class VWAPMomentumStrategy:
    def __init__(self):
        self.api = sj.Shioaji(simulation=SIMULATION)

        # 持倉狀態
        self.has_position = False
        self.position_dir = "Flat"          # Long / Short / Flat
        self.entry_price = 0.0
        self.momentum_active = False
        self.momentum_dir = "None"
        self.momentum_peak = 0.0
        self.trailing_peak = 0.0        # 持倉後出場用，與進場前 momentum_peak 分離
        self.momentum_trigger_time = 0
        self.last_exit_time = 0           # exchange tick timestamp (P0-6)
        self.daily_pnl = 0.0
        self.consecutive_loss = 0
        self.block_new_entry = False      # 日虧觸發後禁止新進場，持倉仍可平倉
        self._trading_date: Optional[datetime.date] = None

        # 下單狀態
        self.is_pending = False
        self.pending_intent: Optional[str] = None   # "entry" | "exit"
        self.exit_pending = False
        self.pending_trade = None
        self.pending_order_id: Optional[str] = None
        self.pending_since = 0.0          # system time; relative pending timeout only
        self.pending_exchange_ts = 0
        self.pending_qty = 0
        self._resynced_position = False   # sync_positions 後待首 tick 校準 trailing_peak
        self._api_connected = True

        # VWAP
        self.vwap_window: Deque[Tuple[int, float, int]] = deque()
        self.vwap_sum_pv = 0.0
        self.vwap_sum_vol = 0
        self.current_vwap = 0.0

        # Momentum
        self.momentum_window: Deque[Tuple[int, int, int]] = deque()
        self.vol_1s = 0
        self.buy_vol_1s = 0
        self.sell_vol_1s = 0
        self.last_tick_price = 0.0

        # ATR
        self.current_atr = 0.0
        self.last_atr_refresh = 0.0

        self.lock = threading.Lock()
        self.contract = None
        self._running = False

    def login(self):
        self.api.login(
            api_key=API_KEY,
            secret_key=SECRET_KEY,
            subscribe_trade=True,
        )
        self.contract = self._resolve_contract()
        logger.info(
            "登入成功 | 合約: %s | 模擬: %s | 帳號: %s",
            self.contract.code,
            SIMULATION,
            getattr(self.api.futopt_account, "account_id", "N/A"),
        )

        if not SIMULATION:
            if not CA_PATH or not CA_PASSWD:
                raise RuntimeError("正式模式需設定 SJ_CA_PATH 與 SJ_CA_PASSWD")
            self.api.activate_ca(ca_path=CA_PATH, ca_passwd=CA_PASSWD)
            self.api.subscribe_trade(self.api.futopt_account)

        self.sync_positions()
        self.refresh_atr()

    def _contract_position_codes(self) -> set:
        codes = {self.contract.code}
        for attr in ("target_code", "symbol"):
            value = getattr(self.contract, attr, None)
            if value:
                codes.add(value)
        return codes

    def _position_matches_contract(self, pos) -> bool:
        return pos.code in self._contract_position_codes()

    def sync_positions(self):
        """啟動時從券商同步持倉，避免重啟後策略與實際部位脫節。"""
        try:
            positions = self.api.list_positions(account=self.api.futopt_account)
        except Exception as e:
            logger.warning("持倉對帳失敗: %s", e)
            return

        matched = None
        for pos in positions:
            if int(pos.quantity) == 0:
                continue
            if self._position_matches_contract(pos):
                matched = pos
                break

        with self.lock:
            if matched is None:
                self.has_position = False
                self.position_dir = "Flat"
                self.entry_price = 0.0
                self.trailing_peak = 0.0
                open_positions = [
                    p for p in positions if int(p.quantity) != 0
                ]
                if open_positions:
                    logger.warning(
                        "券商有 %d 筆持倉，但無法對應合約 %s（%s）",
                        len(open_positions),
                        self.contract.code,
                        ", ".join(p.code for p in open_positions),
                    )
                else:
                    logger.info("持倉對帳 | 無持倉")
                return

            is_long = matched.direction in (sj.Action.Buy, "Buy")
            self.has_position = True
            self.position_dir = "Long" if is_long else "Short"
            self.entry_price = float(matched.price)
            self.trailing_peak = self.entry_price
            self._resynced_position = True
            self.reset_momentum()
            logger.info(
                "持倉對帳 | %s %d口 @ %.1f | code=%s | peak 待首 tick 校準",
                self.position_dir,
                matched.quantity,
                self.entry_price,
                matched.code,
            )

    def _resolve_contract(self):
        txf = getattr(self.api.Contracts.Futures, "TXF", None)
        if txf is not None and hasattr(txf, PRODUCT_CODE):
            return getattr(txf, PRODUCT_CODE)
        return self.api.Contracts.Futures[PRODUCT_CODE]

    def _parse_tick(self, tick: TickFOPv1) -> Tuple[int, float, int, int]:
        ts = int(tick.datetime.timestamp())
        price = float(tick.close)
        volume = int(tick.volume)
        tick_type = int(getattr(tick, "tick_type", 0) or 0)

        if tick_type == 0 and self.last_tick_price > 0:
            if price > self.last_tick_price:
                tick_type = 1
            elif price < self.last_tick_price:
                tick_type = 2

        self.last_tick_price = price
        return ts, price, volume, tick_type

    def on_tick(self, tick: TickFOPv1):
        ts, price, volume, tick_type = self._parse_tick(tick)

        if volume >= 20:
            logger.debug(
                "Tick | Price:%.1f | Vol:%d | Type:%d", price, volume, tick_type
            )

        signal: Optional[OrderSignal] = None
        with self.lock:
            self._maybe_refresh_atr(ts)
            self.update_vwap(ts, price, volume)
            self.update_momentum(ts, volume, tick_type)
            if self.has_position:
                if self._resynced_position:
                    self._calibrate_trailing_peak_after_resync(price)
                self._update_trailing_peak(price)
            elif self.momentum_active:
                self._update_momentum_peak(price)
            signal = self.process_strategy(ts, price, tick.datetime)
            if signal is not None:
                self._arm_pending(signal)
                self._log_signal_audit(signal)

        if signal is not None:
            self.place_order(signal)

    def _maybe_refresh_atr(self, ts: int):
        if ts - self.last_atr_refresh >= ATR_REFRESH_SEC:
            self.last_atr_refresh = ts
            threading.Thread(target=self.refresh_atr, daemon=True).start()

    def refresh_atr(self):
        try:
            today = datetime.date.today()
            start = today - datetime.timedelta(days=ATR_KLINE_LOOKBACK_DAYS)
            kbars = self.api.kbars(
                contract=self.contract,
                start=start.isoformat(),
                end=today.isoformat(),
            )
            atr = self._compute_atr(kbars)
            with self.lock:
                self.current_atr = atr
            logger.info(
                "ATR(%d) 更新: %.2f | lookback=%d 天",
                ATR_PERIOD,
                atr,
                ATR_KLINE_LOOKBACK_DAYS,
            )
        except Exception as e:
            logger.warning("ATR 更新失敗: %s", e)

    def _vol_threshold(self, dt: datetime.datetime) -> tuple[float, float, float]:
        """P1-2: (base_vol, multiplier, vol_threshold)."""
        return compute_vol_threshold(
            self.current_atr,
            dt,
            base_vol=BASE_VOL,
            atr_vol_mult=ATR_VOL_MULT,
            mult_futures=OPEN_MULT_FUTURES,
            mult_spot=OPEN_MULT_SPOT,
            mult_normal=OPEN_MULT_NORMAL,
        )

    def _calibrate_trailing_peak_after_resync(self, price: float) -> None:
        """P0-3: 重啟對帳後首 tick，保守初始化 trailing_peak。"""
        old_peak = self.trailing_peak
        if self.position_dir == "Long":
            self.trailing_peak = max(self.entry_price, price)
        elif self.position_dir == "Short":
            self.trailing_peak = min(self.entry_price, price)
        self._resynced_position = False
        logger.info(
            "持倉 peak 校準 | %s entry=%.1f tick=%.1f peak %.1f→%.1f",
            self.position_dir,
            self.entry_price,
            price,
            old_peak,
            self.trailing_peak,
        )

    def _arm_pending(self, signal: OrderSignal) -> None:
        """P2-2: lock 內同步設 pending，堵住雙 tick 雙單。"""
        self.is_pending = True
        self.pending_intent = signal.intent
        self.pending_exchange_ts = signal.exchange_ts
        self.pending_qty = signal.qty
        if signal.intent == "exit":
            self.exit_pending = True

    @staticmethod
    def _log_signal_audit(signal: OrderSignal) -> None:
        if signal.audit is None:
            return
        logger.info("SIGNAL_AUDIT %s", format_signal_audit(signal.audit))

    def _build_entry_audit(
        self, dt: datetime.datetime, price: float, ts: int, direction: str
    ) -> SignalAudit:
        buy_ratio = self.buy_vol_1s / self.vol_1s if self.vol_1s > 0 else 0.0
        sell_ratio = self.sell_vol_1s / self.vol_1s if self.vol_1s > 0 else 0.0
        base_vol, multiplier, vol_threshold = self._vol_threshold(dt)
        return SignalAudit(
            intent="entry",
            direction=direction,
            price=price,
            ts=ts,
            vol_1s=self.vol_1s,
            buy_ratio=round(buy_ratio, 4),
            sell_ratio=round(sell_ratio, 4),
            atr=round(self.current_atr, 2),
            multiplier=multiplier,
            vol_threshold=round(vol_threshold, 1),
            vwap=round(self.current_vwap, 1),
            reason="pullback",
        )

    def _build_exit_audit(
        self, price: float, ts: int, direction: str, reason: str
    ) -> SignalAudit:
        return SignalAudit(
            intent="exit",
            direction=direction,
            price=price,
            ts=ts,
            atr=round(self.current_atr, 2),
            vwap=round(self.current_vwap, 1),
            reason=reason,
        )

    @staticmethod
    def _compute_atr(kbars) -> float:
        closes = kbars.Close
        highs = kbars.High
        lows = kbars.Low
        if len(closes) < 2:
            return 0.0

        trs = []
        for i in range(1, len(closes)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
            trs.append(tr)

        period = min(ATR_PERIOD, len(trs))
        if period == 0:
            return 0.0
        return sum(trs[-period:]) / period

    def update_vwap(self, ts: int, price: float, volume: int):
        self.vwap_window.append((ts, price, volume))
        self.vwap_sum_pv += price * volume
        self.vwap_sum_vol += volume

        cutoff = ts - VWAP_WINDOW_MIN * 60
        while self.vwap_window and self.vwap_window[0][0] < cutoff:
            old_ts, old_p, old_v = self.vwap_window.popleft()
            self.vwap_sum_pv -= old_p * old_v
            self.vwap_sum_vol -= old_v

        self.current_vwap = (
            self.vwap_sum_pv / self.vwap_sum_vol if self.vwap_sum_vol > 0 else price
        )

    def update_momentum(self, ts: int, volume: int, tick_type: int):
        self.momentum_window.append((ts, volume, tick_type))
        self.vol_1s += volume

        if tick_type == 1:
            self.buy_vol_1s += volume
        elif tick_type == 2:
            self.sell_vol_1s += volume

        cutoff = ts - 1
        while self.momentum_window and self.momentum_window[0][0] < cutoff:
            old_ts, old_v, old_type = self.momentum_window.popleft()
            self.vol_1s -= old_v
            if old_type == 1:
                self.buy_vol_1s -= old_v
            elif old_type == 2:
                self.sell_vol_1s -= old_v

    def _update_momentum_peak(self, price: float):
        """進場前突破偵測用 peak，僅在 momentum_active 時更新。"""
        if self.momentum_dir == "Long":
            self.momentum_peak = max(self.momentum_peak, price)
        elif self.momentum_dir == "Short":
            self.momentum_peak = min(self.momentum_peak, price)

    def _update_trailing_peak(self, price: float):
        """持倉後 trailing stop 用 peak，僅在 manage_exit 邏輯內使用。"""
        if self.position_dir == "Long":
            self.trailing_peak = max(self.trailing_peak, price)
        elif self.position_dir == "Short":
            self.trailing_peak = min(self.trailing_peak, price)

    def is_trading_session(self, dt: datetime.datetime) -> bool:
        return _is_trading_session(dt, SESSION_START, SESSION_END)

    def _maybe_reset_daily_state(self, dt: datetime.datetime) -> None:
        """P0-8: 交易日變更時重置日內風控（日盤 = 日曆日，見 exchange_time）。"""
        trade_date = trading_day_for_daily_reset(dt)
        if self._trading_date is None:
            self._trading_date = trade_date
            return
        if trade_date == self._trading_date:
            return
        logger.info(
            "交易日切換 %s → %s，重置日內風控",
            self._trading_date,
            trade_date,
        )
        self._reset_daily_state()
        self._trading_date = trade_date

    def _reset_daily_state(self) -> None:
        self.daily_pnl = 0.0
        self.block_new_entry = False
        self.consecutive_loss = 0

    def process_strategy(
        self, ts: int, price: float, dt: datetime.datetime
    ) -> Optional[OrderSignal]:
        self._maybe_reset_daily_state(dt)

        if not self._api_connected:
            if self.has_position:
                if is_at_or_after(dt, SESSION_FORCE_FLATTEN_TIME):
                    return self._session_force_flatten_signal(price, ts)
                return self.manage_exit(price, ts)
            return None

        if self.is_pending or self.exit_pending:
            return None
        if ts - self.last_exit_time < COOLDOWN_SEC:
            return None
        if not self.is_trading_session(dt):
            return None

        if self.daily_pnl <= -MAX_DAILY_LOSS_POINTS and not self.block_new_entry:
            self.block_new_entry = True
            logger.warning("觸發單日最大虧損，停止新進場")

        # 持倉管理優先（日虧觸發後仍須平倉）
        if self.has_position:
            if is_at_or_after(dt, SESSION_FORCE_FLATTEN_TIME):
                return self._session_force_flatten_signal(price, ts)
            return self.manage_exit(price, ts)

        # P2-3: flatten_time 後禁止新進場
        if is_at_or_after(dt, SESSION_FLATTEN_TIME):
            return None

        if self.block_new_entry:
            return None

        # 新進場需通過風控濾鏡
        if self.consecutive_loss >= MAX_CONSECUTIVE_LOSS:
            return None
        if self.current_atr < MIN_ATR_THRESHOLD:
            return None

        if not self.momentum_active:
            buy_ratio = self.buy_vol_1s / self.vol_1s if self.vol_1s > 0 else 0
            sell_ratio = self.sell_vol_1s / self.vol_1s if self.vol_1s > 0 else 0
            base_vol, multiplier, vol_threshold = self._vol_threshold(dt)

            if self.vol_1s >= vol_threshold and buy_ratio >= MOMENTUM_BUY_RATIO:
                logger.info(
                    "MOMENTUM 量能通過 | dir=Long vol_1s=%d base=%.0f mult=%.2f "
                    "threshold=%.0f buy_ratio=%.2f",
                    self.vol_1s,
                    base_vol,
                    multiplier,
                    vol_threshold,
                    buy_ratio,
                )
                self.activate_momentum("Long", price, ts)
            elif self.vol_1s >= vol_threshold and sell_ratio >= MOMENTUM_SELL_RATIO:
                logger.info(
                    "MOMENTUM 量能通過 | dir=Short vol_1s=%d base=%.0f mult=%.2f "
                    "threshold=%.0f sell_ratio=%.2f",
                    self.vol_1s,
                    base_vol,
                    multiplier,
                    vol_threshold,
                    sell_ratio,
                )
                self.activate_momentum("Short", price, ts)
            return None

        # Pullback 進場
        if ts - self.momentum_trigger_time > 180:
            self.reset_momentum()
            return None

        dynamic_threshold = max(2.0, self.current_vwap * 0.0001)
        near_vwap = abs(price - self.current_vwap) <= dynamic_threshold
        exhausted = self.vol_1s <= EXHAUSTION_VOL

        if not (near_vwap and exhausted):
            return None

        if self.momentum_dir == "Long":
            return OrderSignal(
                "Buy",
                1,
                price,
                "entry",
                exchange_ts=ts,
                audit=self._build_entry_audit(dt, price, ts, "Buy"),
            )
        return OrderSignal(
            "Sell",
            1,
            price,
            "entry",
            exchange_ts=ts,
            audit=self._build_entry_audit(dt, price, ts, "Sell"),
        )

    def activate_momentum(self, direction: str, price: float, ts: int):
        self.momentum_active = True
        self.momentum_dir = direction
        self.momentum_peak = price
        self.momentum_trigger_time = ts
        logger.info("MOMENTUM %s 突破 | 價格 %.1f", direction, price)

    def reset_momentum(self):
        self.momentum_active = False
        self.momentum_dir = "None"
        self.momentum_peak = 0.0
        self.momentum_trigger_time = 0

    def manage_exit(self, price: float, ts: int) -> Optional[OrderSignal]:
        if self.position_dir == "Long":
            sl_hit = price <= self.entry_price - 6 or price <= self.current_vwap - 3
            tp_hit = price >= self.entry_price + FIXED_TP_POINTS
            trail_hit = price <= self.trailing_peak - TRAIL_POINTS
            if sl_hit or tp_hit or trail_hit:
                reason = (
                    "stop_loss"
                    if sl_hit
                    else "take_profit"
                    if tp_hit
                    else "trailing_stop"
                )
                return OrderSignal(
                    "Sell",
                    1,
                    price,
                    "exit",
                    exchange_ts=ts,
                    audit=self._build_exit_audit(price, ts, "Sell", reason),
                )
        else:
            sl_hit = price >= self.entry_price + 6 or price >= self.current_vwap + 3
            tp_hit = price <= self.entry_price - FIXED_TP_POINTS
            trail_hit = price >= self.trailing_peak + TRAIL_POINTS
            if sl_hit or tp_hit or trail_hit:
                reason = (
                    "stop_loss"
                    if sl_hit
                    else "take_profit"
                    if tp_hit
                    else "trailing_stop"
                )
                return OrderSignal(
                    "Buy",
                    1,
                    price,
                    "exit",
                    exchange_ts=ts,
                    audit=self._build_exit_audit(price, ts, "Buy", reason),
                )
        return None

    def _session_force_flatten_signal(
        self, price: float, ts: int
    ) -> OrderSignal:
        action = "Sell" if self.position_dir == "Long" else "Buy"
        logger.warning(
            "收盤強制平倉 | %s @ %.1f | force_flatten_time=%s",
            self.position_dir,
            price,
            SESSION_FORCE_FLATTEN_TIME.strftime("%H:%M"),
        )
        return OrderSignal(
            action,
            1,
            price,
            "exit",
            exchange_ts=ts,
            slippage_points=FLATTEN_SLIPPAGE_POINTS,
            audit=self._build_exit_audit(
                price, ts, action, "session_force_flatten"
            ),
        )

    def place_order(self, signal: OrderSignal):
        action = signal.action
        qty = signal.qty
        ref_price = signal.ref_price

        try:
            slip = (
                signal.slippage_points
                if signal.slippage_points is not None
                else IOC_SLIPPAGE_POINTS
            )
            price = ref_price + slip if action == "Buy" else ref_price - slip
            order = sj.FuturesOrder(
                action=sj.Action.Buy if action == "Buy" else sj.Action.Sell,
                price=price,
                quantity=qty,
                price_type=sj.FuturesPriceType.LMT,
                order_type=sj.OrderType.IOC,
                octype=sj.FuturesOCType.Auto,
                account=self.api.futopt_account,
            )
            trade = self.api.place_order(self.contract, order, timeout=0)
            with self.lock:
                self.pending_trade = trade
                self.pending_order_id = str(trade.order.id)
                self.pending_since = time.time()
            logger.info(
                "下單 %s %d 口 @ %.1f (%s) | trade=%s",
                action,
                qty,
                price,
                signal.intent,
                trade.order.id,
            )
        except Exception as e:
            logger.error("下單失敗: %s", e)
            with self.lock:
                self._clear_pending()

    def handle_order_event(self, stat, msg):
        needs_sync = False
        with self.lock:
            if stat == OrderState.FuturesOrder:
                self._handle_futures_order(msg)
            elif stat == OrderState.FuturesDeal:
                needs_sync = self._handle_futures_deal(msg)
        if needs_sync:
            self.sync_positions()

    def _event_order_id(self, msg: dict) -> Optional[str]:
        trade_id = msg.get("trade_id")
        if trade_id:
            return str(trade_id)
        status = msg.get("status") or {}
        for key in ("id", "order_id"):
            value = status.get(key)
            if value:
                return str(value)
        order = msg.get("order") or {}
        for key in ("id", "order_id"):
            value = order.get(key)
            if value:
                return str(value)
        return None

    def _matches_pending_order(self, msg: dict) -> bool:
        expected = self.pending_order_id
        if not expected:
            return False
        actual = self._event_order_id(msg)
        return actual is not None and actual == expected

    def _handle_futures_order(self, msg):
        op = msg.get("operation", {})
        op_code = op.get("op_code", "")
        op_type = op.get("op_type", "")
        status = msg.get("status", {}).get("status", "")

        logger.info(
            "委託回報 | op=%s code=%s status=%s | order=%s",
            op_type,
            op_code,
            status,
            self._event_order_id(msg),
        )

        if not self.is_pending:
            return
        if not self._matches_pending_order(msg):
            logger.warning(
                "忽略非當前委託狀態回報 | expected=%s got=%s",
                self.pending_order_id,
                self._event_order_id(msg),
            )
            return

        if op_code and op_code != "00":
            logger.warning("委託失敗: %s", op.get("op_msg", op_code))
            self._clear_pending()
            return

        if status in ("Cancelled", "Failed") or op_type in ("Cancel", "Delete"):
            deal_qty = msg.get("status", {}).get("deal_quantity", 0)
            if deal_qty == 0:
                if self.pending_intent == "entry":
                    logger.info(
                        "委託未成交/已取消，重置 pending | tag=intent_cancelled"
                    )
                else:
                    logger.info("委託未成交/已取消，重置 pending")
                self._clear_pending()

    def _handle_futures_deal(self, msg) -> bool:
        price = float(msg["price"])
        qty = int(msg["quantity"])
        action = msg.get("action", "")
        order_id = self._event_order_id(msg)
        logger.info(
            "成交回報 | %s %d 口 @ %.1f | order=%s",
            action,
            qty,
            price,
            order_id,
        )

        if not self.is_pending:
            logger.warning("忽略非 pending 成交回報 | order=%s", order_id)
            return False
        if not self._matches_pending_order(msg):
            logger.warning(
                "忽略非當前委託成交回報 | expected=%s got=%s",
                self.pending_order_id,
                order_id,
            )
            return False

        is_buy = action in (sj.Action.Buy, "Buy")
        return self._apply_deal_fill(price, is_buy, deal_qty=qty)

    def _apply_deal_fill(
        self, price: float, is_buy: bool, deal_qty: int = 1
    ) -> bool:
        """套用成交。回傳 True 表示須在 lock 外呼叫 sync_positions()。"""
        expected = self.pending_qty if self.pending_qty > 0 else 1
        if deal_qty < expected:
            logger.critical(
                "部分成交 | intent=%s expected=%d got=%d order=%s | "
                "解鎖 pending，改以券商對帳為準",
                self.pending_intent,
                expected,
                deal_qty,
                self.pending_order_id,
            )
            self._clear_pending()
            return True

        intent = self.pending_intent
        if intent == "entry":
            self.has_position = True
            self.entry_price = price
            self.position_dir = "Long" if is_buy else "Short"
            self.trailing_peak = price
            self.reset_momentum()
            self._clear_pending()
            logger.info("進場完成 | %s %d口 @ %.1f", self.position_dir, deal_qty, price)
            return False

        elif intent == "exit" and self.has_position:
            if self.position_dir == "Long":
                pnl = price - self.entry_price
            else:
                pnl = self.entry_price - price

            self.daily_pnl += pnl
            if pnl < 0:
                self.consecutive_loss += 1
            else:
                self.consecutive_loss = 0

            self.has_position = False
            self.position_dir = "Flat"
            self.entry_price = 0.0
            self.trailing_peak = 0.0
            self.last_exit_time = self.pending_exchange_ts
            self._clear_pending()
            logger.info(
                "平倉完成 | PnL=%.1f | 今日=%.1f | 連續虧損=%d",
                pnl,
                self.daily_pnl,
                self.consecutive_loss,
            )
            return False

        return False

    @staticmethod
    def _is_buy_action(action) -> bool:
        return action in (sj.Action.Buy, "Buy")

    def _extract_fill_from_trade(self, trade) -> Optional[Tuple[float, bool]]:
        deals = getattr(trade.status, "deals", None) or []
        if deals:
            deal = deals[-1]
            return float(deal.price), self._is_buy_action(deal.action)

        deal_qty = int(getattr(trade.status, "deal_quantity", 0) or 0)
        if deal_qty > 0:
            return float(trade.order.price), self._is_buy_action(trade.order.action)
        return None

    def _still_own_pending(self, trade) -> bool:
        """須在 lock 內呼叫：確認 pending 仍屬於此 trade。"""
        return (
            self.is_pending
            and self.pending_order_id is not None
            and self.pending_order_id == str(trade.order.id)
        )

    def _reconcile_pending_trade(self, trade) -> bool:
        """補查委託狀態。回傳 True 表示 pending 已處理完畢（含 callback 已搶先處理）。"""
        try:
            self.api.update_status(trade=trade)
        except Exception as e:
            logger.warning("update_status 補查失敗: %s", e)
            return False

        status = str(getattr(trade.status, "status", "") or "")
        deal_qty = int(getattr(trade.status, "deal_quantity", 0) or 0)
        fill = self._extract_fill_from_trade(trade)

        if fill and deal_qty > 0 and status in ("Filled", "PartFilled"):
            price, is_buy = fill
            needs_sync = False
            with self.lock:
                if not self._still_own_pending(trade):
                    return True
                logger.info("補查確認成交 | status=%s qty=%d", status, deal_qty)
                needs_sync = self._apply_deal_fill(price, is_buy, deal_qty=deal_qty)
            if needs_sync:
                self.sync_positions()
            return True

        if status in ("Cancelled", "Failed") and deal_qty == 0:
            with self.lock:
                if not self._still_own_pending(trade):
                    return True
                logger.info("補查確認委託未成交/已取消，重置 pending")
                self._clear_pending()
            return True

        if not SIMULATION:
            try:
                records = self.api.order_deal_records()
            except Exception as e:
                logger.warning("order_deal_records 補查失敗: %s", e)
                records = []

            order_id = str(trade.order.id)
            for state, event in records:
                if state != OrderState.FuturesDeal:
                    continue
                if str(event.get("trade_id", "")) != order_id:
                    continue
                needs_sync = False
                with self.lock:
                    if not self._still_own_pending(trade):
                        return True
                    logger.info("order_deal_records 補查到成交")
                    needs_sync = self._handle_futures_deal(event)
                if needs_sync:
                    self.sync_positions()
                return True

        return False

    def _check_pending_timeout(self):
        with self.lock:
            if not self.is_pending:
                return
            if time.time() - self.pending_since < PENDING_TIMEOUT_SEC:
                return
            trade = self.pending_trade

        if trade is None:
            with self.lock:
                if self.is_pending:
                    logger.warning("Pending 超時但無 trade 物件，重置 pending")
                    self._clear_pending()
            return

        resolved = self._reconcile_pending_trade(trade)
        with self.lock:
            if not self.is_pending:
                return
            if resolved:
                return
            if not self._still_own_pending(trade):
                return
            logger.warning(
                "Pending 超時 %.0fs 且補查無結果，重置 pending",
                PENDING_TIMEOUT_SEC,
            )
            self._clear_pending()

    def _timeout_loop(self):
        while self._running:
            try:
                self._check_pending_timeout()
            except Exception as e:
                logger.warning("Pending 超時檢查異常: %s", e)
            time.sleep(1)

    def _clear_pending(self):
        self.is_pending = False
        self.pending_intent = None
        self.exit_pending = False
        self.pending_trade = None
        self.pending_order_id = None
        self.pending_since = 0.0
        self.pending_exchange_ts = 0
        self.pending_qty = 0

    def handle_session_event(
        self, resp_code: int, event_code: int, info: str, event: str
    ):
        if event_code == 12:
            logger.warning("API 重連中 | resp=%s info=%s", resp_code, info)
            with self.lock:
                self._api_connected = False
        elif event_code == 13:
            logger.info("API 重連成功 | resp=%s", resp_code)
            threading.Thread(
                target=self._on_reconnected, daemon=True, name="reconnect-sync"
            ).start()

    def handle_session_down(self):
        logger.warning("API 連線中斷")
        with self.lock:
            self._api_connected = False

    def _on_reconnected(self):
        """P4-1: 先補查 pending，再對帳持倉，最後重新訂閱。"""
        with self.lock:
            trade = self.pending_trade if self.is_pending else None

        if trade is not None:
            try:
                self._reconcile_pending_trade(trade)
            except Exception as e:
                logger.warning("重連後 pending 補查失敗: %s", e)

        self.sync_positions()

        try:
            self.api.subscribe(self.contract, quote_type=sj.QuoteType.Tick)
        except Exception as e:
            logger.warning("重連後 subscribe 失敗: %s", e)

        self.refresh_atr()

        with self.lock:
            self._api_connected = True

        logger.info("重連後狀態同步完成")

    def start(self):
        self.login()
        self._running = True

        self.api.set_order_callback(self.handle_order_event)
        self.api.set_event_callback(self.handle_session_event)
        if hasattr(self.api, "set_session_down_callback"):
            self.api.set_session_down_callback(self.handle_session_down)

        @self.api.on_tick_fop_v1()
        def on_fop_tick(tick: TickFOPv1):
            self.on_tick(tick)

        self.api.subscribe(self.contract, quote_type=sj.QuoteType.Tick)

        logger.info(
            "VWAP Momentum 策略已啟動 | config=%s | ATR=%.2f | 模擬=%s",
            settings.config_path,
            self.current_atr,
            SIMULATION,
        )

        threading.Thread(target=self._timeout_loop, daemon=True).start()

        try:
            while self._running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("策略手動停止")
        finally:
            self._running = False
            self.api.logout()
            shutdown_async_logging()


if __name__ == "__main__":
    strategy = VWAPMomentumStrategy()
    strategy.start()
