import shioaji as sj
from shioaji import OrderState, TickFOPv1
import atexit
import os
import time
import datetime
import logging
import logging.handlers
import queue
import sys
from collections import deque
import threading
from typing import Any, Deque, List, Optional, Tuple

from core.types import OrderSignal
from exchange_time import (
    compute_vol_threshold,
    is_at_or_after,
    is_opening_session_window,
    is_trading_session as _is_trading_session,
    trading_day_for_daily_reset,
)
from observability import (
    DailyObservability,
    compute_limit_price,
    format_daily_summary,
    format_fill_audit,
)
from core.audit.signal_audit import SignalAudit, format_signal_audit
from storage.kbar_archiver import archive_kbars_snapshot
from storage.tick_archiver import TickArchiver
from order_errors import (
    OrderErrorCategory,
    classify_order_error,
    should_retry_order,
)
from alerts import send_alert
from strategy.trend import compute_trend
from strategy.indicators import IndicatorState
from strategy.vwap_momentum import VWAPMomentumStrategy
from strategy.base import Strategy
from core.types import PositionSnapshot, RiskGate

from config import (
    ATR_TRAILING_ENABLED,
    ATR_VWAP_STOP_ENABLED,
    API_KEY,
    DUMP_ORDER_EVENTS,
    KBARS_ARCHIVE,
    TICK_ARCHIVE,
    ATR_KLINE_LOOKBACK_DAYS,
    ATR_PERIOD,
    ATR_REFRESH_SEC,
    ATR_VOL_MULT,
    BASE_VOL,
    CA_PASSWD,
    CA_PATH,
    CLOCK_SKEW_WARN_SEC,
    COOLDOWN_SEC,
    ENTRY_BAND_POINTS,
    EXIT_ORDER_MAX_RETRIES,
    EXIT_ORDER_RETRY_DELAY_SEC,
    EXHAUSTION_VOL,
    FIXED_TP_POINTS,
    EXIT_GRACE_SEC,
    EXIT_GRACE_TICKS,
    FLATTEN_SLIPPAGE_POINTS,
    HARD_STOP_POINTS,
    IOC_SLIPPAGE_POINTS,
    LOG_FILE,
    LOG_LEVEL,
    MAX_CONSECUTIVE_LOSS,
    MAX_DAILY_LOSS_POINTS,
    MIN_ATR_THRESHOLD,
    MOMENTUM_BUY_RATIO,
    NO_TICK_TIMEOUT_SEC,
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
    SESSION_RELOGIN_BACKOFF_BASE_SEC,
    SESSION_RELOGIN_MAX_ATTEMPTS,
    SESSION_START,
    SESSION_WATCHDOG_SEC,
    SIMULATION,
    TRAIL_POINTS,
    TRAIL_ATR_K,
    TRAIL_POINTS_FLOOR,
    TREND_EMA_PERIOD,
    TREND_FILTER_ENABLED,
    TREND_MIN_STRENGTH,
    TREND_MODE,
    TREND_SLOPE_MIN,
    TREND_TIMEFRAME_MIN,
    VWAP_STOP_ATR_K,
    VWAP_STOP_POINTS,
    VWAP_STOP_POINTS_FLOOR,
    VWAP_WINDOW_MIN,
    settings,
)

from runtime.logging_setup import setup_async_logging, shutdown_async_logging

logger = setup_async_logging()

from runtime.order_executor import OrderExecutorMixin
from runtime.session import SessionMixin

class TradingEngine(OrderExecutorMixin, SessionMixin):
    def __init__(self, api: Any = None, clock: Any = None, strategy: Strategy | None = None):
        self.api = api if api is not None else sj.Shioaji(simulation=SIMULATION)
        # 注入式時鐘：實盤預設 time.time()；回測傳入 tick 時間驅動的時鐘以確保確定性。
        self._clock = clock if clock is not None else time.time

        # 持倉狀態
        self.has_position = False
        self.position_dir = "Flat"          # Long / Short / Flat
        self.entry_price = 0.0
        self.entry_exchange_ts = 0
        self.ticks_since_entry = 0
        self.trailing_peak = 0.0
        self.last_exit_time = 0
        self.daily_pnl = 0.0
        self.consecutive_loss = 0
        self.block_new_entry = False
        self._trading_date: Optional[datetime.date] = None

        # 下單狀態
        self.is_pending = False
        self.pending_intent: Optional[str] = None
        self.exit_pending = False
        self.pending_trade = None
        self.pending_order_id: Optional[str] = None
        self.pending_since = 0.0          # system time; relative pending timeout only
        self.pending_exchange_ts = 0
        self.pending_qty = 0
        self.pending_signal_price = 0.0
        self.pending_limit_price = 0.0
        self.pending_exit_reason = ""
        self.pending_ioc_slippage = IOC_SLIPPAGE_POINTS
        self._resynced_position = False   # sync_positions 後待首 tick 校準 trailing_peak
        self._api_connected = True
        self._disconnect_since = 0.0
        self._session_relogin_attempts = 0
        self._next_relogin_at = 0.0
        self._exit_order_retry_count = 0
        self._exit_order_retry_at = 0.0
        self._pending_action: Optional[str] = None

        self.indicators = IndicatorState()
        self._obs = DailyObservability()
        self.strategy: Strategy = strategy or VWAPMomentumStrategy(obs=self._obs)

        self.lock = threading.Lock()
        self.contract = None
        self._running = False
        self._raw_order_evt_dumped: set = set()
        self.last_tick_exchange_ts = 0
        self._last_tick_wall_time = 0.0
        self._last_tick_exchange_dt: Optional[datetime.datetime] = None
        self._tick_type_counts = {0: 0, 1: 0, 2: 0}
        self._tick_type_inferred_counts = {1: 0, 2: 0}
        self._last_tick_type_log_wall = 0.0
        self._last_clock_skew_warn_wall = 0.0
        self._last_no_tick_resubscribe_wall = 0.0
        self._pending_intent_cancel_exchange_dt: Optional[datetime.datetime] = None
        self._tick_archiver: Optional[TickArchiver] = None
        self._order_queue: queue.Queue[Optional[OrderSignal]] = queue.Queue()
        self._order_sync_mode = False
        self._order_worker_started = False

    @property
    def current_vwap(self) -> float:
        return self.indicators.current_vwap

    @current_vwap.setter
    def current_vwap(self, value: float) -> None:
        self.indicators.current_vwap = value

    @property
    def vol_1s(self) -> int:
        return self.indicators.vol_1s

    @vol_1s.setter
    def vol_1s(self, value: int) -> None:
        self.indicators.vol_1s = value

    @property
    def buy_vol_1s(self) -> int:
        return self.indicators.buy_vol_1s

    @property
    def sell_vol_1s(self) -> int:
        return self.indicators.sell_vol_1s

    @property
    def current_atr(self) -> float:
        return self.indicators.current_atr

    @current_atr.setter
    def current_atr(self, value: float) -> None:
        self.indicators.current_atr = value

    @property
    def last_atr_refresh(self) -> float:
        return self.indicators.last_atr_refresh

    @last_atr_refresh.setter
    def last_atr_refresh(self, value: float) -> None:
        self.indicators.last_atr_refresh = value

    @property
    def trend_dir(self) -> str:
        return self.indicators.trend_dir

    @trend_dir.setter
    def trend_dir(self, value: str) -> None:
        self.indicators.trend_dir = value

    @property
    def trend_strength(self) -> float:
        return self.indicators.trend_strength

    @property
    def momentum_active(self) -> bool:
        return self.strategy.momentum.active

    @momentum_active.setter
    def momentum_active(self, value: bool) -> None:
        self.strategy.momentum.active = value

    @property
    def momentum_dir(self) -> str:
        return self.strategy.momentum.direction

    @momentum_dir.setter
    def momentum_dir(self, value: str) -> None:
        self.strategy.momentum.direction = value

    @property
    def momentum_trigger_time(self) -> int:
        return self.strategy.momentum.trigger_time

    @momentum_trigger_time.setter
    def momentum_trigger_time(self, value: int) -> None:
        self.strategy.momentum.trigger_time = value

    @property
    def momentum_peak(self) -> float:
        return self.strategy.momentum.peak

    @momentum_peak.setter
    def momentum_peak(self, value: float) -> None:
        self.strategy.momentum.peak = value

    def build_entry_audit(
        self, dt: datetime.datetime, price: float, ts: int, direction: str
    ) -> SignalAudit:
        vol_threshold = self._vol_threshold(dt)
        market = self.indicators.snapshot(ts, price, dt)
        base_vol, multiplier, threshold = vol_threshold
        return self.strategy.build_entry_audit(
            market, direction, multiplier, threshold
        )

    def build_exit_audit(
        self,
        price: float,
        ts: int,
        direction: str,
        reason: str,
        *,
        trail_points_used: float = 0.0,
    ) -> SignalAudit:
        dt = self._last_tick_exchange_dt or datetime.datetime.fromtimestamp(ts)
        market = self.indicators.snapshot(ts, price, dt)
        return self.strategy.build_exit_audit(
            market, direction, reason, trail_points_used=trail_points_used
        )

    def _position_snapshot(self) -> PositionSnapshot:
        return PositionSnapshot(
            has_position=self.has_position,
            position_dir=self.position_dir,
            entry_price=self.entry_price,
            trailing_peak=self.trailing_peak,
            entry_exchange_ts=self.entry_exchange_ts,
            ticks_since_entry=self.ticks_since_entry,
        )

    def _risk_gate(self, ts: int, dt: datetime.datetime) -> RiskGate:
        return RiskGate(
            api_connected=self._api_connected,
            is_pending=self.is_pending,
            exit_pending=self.exit_pending,
            cooldown_active=ts - self.last_exit_time < COOLDOWN_SEC,
            in_trading_session=self.is_trading_session(dt),
            block_new_entry=self.block_new_entry,
            consecutive_loss=self.consecutive_loss,
            daily_pnl=self.daily_pnl,
            after_flatten_time=is_at_or_after(dt, SESSION_FLATTEN_TIME),
            force_flatten=is_at_or_after(dt, SESSION_FORCE_FLATTEN_TIME),
        )

    def _parse_tick_locked(
        self, tick: TickFOPv1
    ) -> Tuple[int, float, int, int, int]:
        """Parse tick inside lock; infer buy/sell from price when type0."""
        ts = int(tick.datetime.timestamp())
        price = float(tick.close)
        volume = int(tick.volume)
        original_tick_type = int(getattr(tick, "tick_type", 0) or 0)
        tick_type = original_tick_type

        if tick_type == 0 and self.indicators.last_tick_price > 0:
            if price > self.indicators.last_tick_price:
                tick_type = 1
            elif price < self.indicators.last_tick_price:
                tick_type = 2

        self.indicators.last_tick_price = price
        if original_tick_type == 0 and tick_type in (1, 2):
            self._tick_type_inferred_counts[tick_type] = (
                self._tick_type_inferred_counts.get(tick_type, 0) + 1
            )
            self._obs.record_tick_type(original_tick_type, tick_type)
        return ts, price, volume, tick_type, original_tick_type

    def on_tick(self, tick: TickFOPv1):
        signal: Optional[OrderSignal] = None
        ts = 0
        price = 0.0
        volume = 0
        tick_type = 0
        original_tick_type = 0
        lock_wait_start = time.perf_counter()
        with self.lock:
            self._obs.record_lock_wait((time.perf_counter() - lock_wait_start) * 1000)
            ts, price, volume, tick_type, original_tick_type = self._parse_tick_locked(
                tick
            )
            self._record_tick_arrival_locked(ts, tick.datetime, tick_type)
            self._obs.record_atr(self.indicators.current_atr)
            self._maybe_refresh_atr(ts)
            self.indicators.update_vwap(ts, price, volume)
            self.indicators.update_momentum(ts, volume, tick_type)
            if self.has_position:
                self.ticks_since_entry += 1
                if self._resynced_position:
                    self._calibrate_trailing_peak_after_resync(price)
                self._update_trailing_peak(price)
            elif self.strategy.momentum.active:
                self.strategy.update_momentum_peak(price)
            signal = self.process_strategy(ts, price, tick.datetime)
            if signal is not None:
                if signal.intent == "entry":
                    self._pending_intent_cancel_exchange_dt = tick.datetime
                    self._obs.record_entry_signal()
                elif signal.intent == "exit":
                    self._obs.record_exit_signal()
                self._arm_pending(signal)
                self._log_signal_audit(signal)

        if self._tick_archiver is not None:
            self._tick_archiver.enqueue_tick(tick, tick_type)

        if volume >= 20:
            logger.debug(
                "Tick | Price:%.1f | Vol:%d | Type:%d (orig=%d)",
                price,
                volume,
                tick_type,
                original_tick_type,
            )

        if signal is not None:
            self._enqueue_order(signal)

    def _maybe_refresh_atr(self, ts: int):
        if ts - self.indicators.last_atr_refresh >= ATR_REFRESH_SEC:
            self.indicators.last_atr_refresh = ts
            threading.Thread(target=self.refresh_atr, daemon=True).start()

    def _today(self) -> datetime.date:
        """交易所「今天」：有 tick 時以 tick 日期為準（回測確定性），否則用系統日期。"""
        if self._last_tick_exchange_dt is not None:
            return self._last_tick_exchange_dt.date()
        return datetime.date.today()

    def refresh_atr(self):
        try:
            today = self._today()
            with self.lock:
                current_atr = self.indicators.current_atr
                long_done = self.indicators._atr_long_lookback_date
            start, used_long = self._atr_kline_start(
                today,
                current_atr=current_atr,
                long_lookback_days=ATR_KLINE_LOOKBACK_DAYS,
                long_lookback_done_for=long_done,
            )
            kbars = self.api.kbars(
                contract=self.contract,
                start=start.isoformat(),
                end=today.isoformat(),
            )
            atr = IndicatorState.compute_atr(kbars)
            if TREND_FILTER_ENABLED:
                closes = list(getattr(kbars, "Close", []) or [])
                trend_closes = closes
                if used_long:
                    # B (review): when we pulled multi-day kbars for stable ATR (current_atr==0
                    # or first time today), limit the data fed to trend computation.
                    # This mitigates the worst cross-session / night-session / gap pollution
                    # exactly at open, when the filter is most needed and the naive stride
                    # + last-N resampled would otherwise pull in yesterday's close + jump.
                    # We still allow ~2 trading days of 1m bars so the HTF detector has
                    # enough history, but we cut the ancient data that creates fake "trends".
                    approx_bars_per_trading_day = 400  # TXF ~330-390 1m bars + buffer
                    trend_closes = closes[-approx_bars_per_trading_day * 2 :]
                trend_dir, trend_strength = compute_trend(
                    trend_closes,
                    mode=TREND_MODE,
                    timeframe_min=TREND_TIMEFRAME_MIN,
                    ema_period=TREND_EMA_PERIOD,
                    slope_min=TREND_SLOPE_MIN,
                    min_strength=TREND_MIN_STRENGTH,
                    atr=atr,  # for ATR-normalized min_strength gating (A from review)
                )
            else:
                with self.lock:
                    trend_dir = self.indicators.trend_dir
                    trend_strength = self.indicators.trend_strength
            with self.lock:
                self.indicators.current_atr = atr
                self.indicators.trend_dir = trend_dir
                self.indicators.trend_strength = trend_strength
                if used_long:
                    self.indicators._atr_long_lookback_date = today
            lookback_label = (
                f"{ATR_KLINE_LOOKBACK_DAYS}d"
                if used_long
                else "當日"
            )
            logger.info(
                "ATR(%d) 更新: %.2f | start=%s lookback=%s",
                ATR_PERIOD,
                atr,
                start.isoformat(),
                lookback_label,
            )
            self._log_api_usage("atr_refresh")
            if KBARS_ARCHIVE:
                try:
                    archive_kbars_snapshot(
                        kbars,
                        product_code=self.contract.code,
                        trade_date=today,
                    )
                except Exception as arch_err:
                    logger.warning("Kbars 落盤失敗: %s", arch_err)
        except Exception as e:
            logger.warning("ATR 更新失敗: %s", e)

    def _vol_threshold(self, dt: datetime.datetime) -> tuple[float, float, float]:
        """P1-2: (base_vol, multiplier, vol_threshold)."""
        return compute_vol_threshold(
            self.indicators.current_atr,
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

    def _record_tick_arrival_locked(
        self, ts: int, exchange_dt: datetime.datetime, tick_type: int
    ) -> None:
        """Must be called with self.lock held."""
        self.last_tick_exchange_ts = ts
        self._last_tick_wall_time = self._clock()
        self._last_tick_exchange_dt = exchange_dt
        bucket = tick_type if tick_type in self._tick_type_counts else 0
        self._tick_type_counts[bucket] = self._tick_type_counts.get(bucket, 0) + 1
        self._maybe_warn_clock_skew(ts)

    def _record_tick_arrival(
        self, ts: int, exchange_dt: datetime.datetime, tick_type: int
    ) -> None:
        self.last_tick_exchange_ts = ts
        self._last_tick_wall_time = self._clock()
        self._last_tick_exchange_dt = exchange_dt
        bucket = tick_type if tick_type in self._tick_type_counts else 0
        self._tick_type_counts[bucket] = self._tick_type_counts.get(bucket, 0) + 1
        self._maybe_warn_clock_skew(ts)

    def _maybe_warn_clock_skew(self, exchange_ts: int) -> None:
        skew = abs(exchange_ts - self._clock())
        if skew <= CLOCK_SKEW_WARN_SEC:
            return
        now = self._clock()
        if now - self._last_clock_skew_warn_wall < 300:
            return
        self._last_clock_skew_warn_wall = now
        logger.warning(
            "系統鐘與交易所時間偏差 %.1fs | 策略決策仍以 tick 時間為準",
            skew,
        )

    def _maybe_log_tick_type_summary(self) -> None:
        """P1-3: 每 30 分鐘輸出 tick_type 分布（UAT 觀測）。"""
        if self._last_tick_exchange_dt is None:
            return
        if not _is_trading_session(
            self._last_tick_exchange_dt, SESSION_START, SESSION_END
        ):
            return
        now = self._clock()
        if now - self._last_tick_type_log_wall < 1800:
            return
        total = sum(self._tick_type_counts.values())
        if total == 0:
            return
        self._last_tick_type_log_wall = now
        inferred_total = sum(self._tick_type_inferred_counts.values())
        logger.info(
            "tick_type 分布 | type0=%d type1=%d type2=%d total=%d "
            "| type0_pct=%.1f%% | inferred_buy=%d inferred_sell=%d inferred_total=%d",
            self._tick_type_counts.get(0, 0),
            self._tick_type_counts.get(1, 0),
            self._tick_type_counts.get(2, 0),
            total,
            100.0 * self._tick_type_counts.get(0, 0) / total,
            self._tick_type_inferred_counts.get(1, 0),
            self._tick_type_inferred_counts.get(2, 0),
            inferred_total,
        )

    def _check_no_tick_watchdog(self) -> None:
        """P4-8: 交易時段內長時間無 tick → 告警並嘗試重訂閱。"""
        if not self._api_connected or self.contract is None:
            return
        if self._last_tick_exchange_dt is None or self._last_tick_wall_time <= 0:
            return
        if not _is_trading_session(
            self._last_tick_exchange_dt, SESSION_START, SESSION_END
        ):
            return
        silent = self._clock() - self._last_tick_wall_time
        if silent < NO_TICK_TIMEOUT_SEC:
            return
        now = self._clock()
        if now - self._last_no_tick_resubscribe_wall < 60:
            return
        self._last_no_tick_resubscribe_wall = now
        self._obs.record_no_tick_resubscribe()
        logger.warning(
            "No-tick 看門狗 | %.0fs 無 tick，嘗試重訂閱 %s",
            silent,
            self.contract.code,
        )
        try:
            self.api.subscribe(self.contract, quote_type=sj.QuoteType.Tick)
            logger.info("No-tick 看門狗 | 重訂閱已送出")
        except Exception as e:
            logger.warning("No-tick 看門狗 | 重訂閱失敗: %s", e)

    def _timeout_loop(self):
        while self._running:
            try:
                self._check_pending_timeout()
                self._check_exit_order_retry()
                self._check_session_watchdog()
                self._check_no_tick_watchdog()
                self._maybe_log_tick_type_summary()
            except Exception as e:
                logger.warning("背景維運檢查異常: %s", e)
            time.sleep(1)

    def _check_session_watchdog(self) -> None:
        with self.lock:
            if self._api_connected:
                return
            disconnected_since = self._disconnect_since
            next_at = self._next_relogin_at
            attempts = self._session_relogin_attempts

        if disconnected_since <= 0:
            return
        now = self._clock()
        if now < next_at:
            return
        if now - disconnected_since < SESSION_WATCHDOG_SEC:
            return
        if attempts >= SESSION_RELOGIN_MAX_ATTEMPTS:
            send_alert(
                f"Session 重登入已達上限 {SESSION_RELOGIN_MAX_ATTEMPTS}",
                level="CRITICAL",
            )
            with self.lock:
                self._next_relogin_at = now + 300.0
            return

        try:
            logger.warning(
                "Session 看門狗觸發重登入 | attempt=%d",
                attempts + 1,
            )
            self.api.login(
                api_key=API_KEY,
                secret_key=SECRET_KEY,
                subscribe_trade=True,
            )
            with self.lock:
                self._session_relogin_attempts = 0
                self._disconnect_since = 0.0
                self._next_relogin_at = 0.0
            self._on_reconnected()
        except Exception as e:
            backoff = SESSION_RELOGIN_BACKOFF_BASE_SEC * (2**attempts)
            logger.error("Session 重登入失敗: %s | backoff=%.1fs", e, backoff)
            send_alert(f"Session 重登入失敗: {e}", level="CRITICAL")
            with self.lock:
                self._session_relogin_attempts = attempts + 1
                self._next_relogin_at = now + backoff

    def _mark_disconnected(self) -> None:
        with self.lock:
            self._api_connected = False
            if self._disconnect_since <= 0:
                self._disconnect_since = self._clock()

    def _clear_pending(self):
        self.is_pending = False
        self.pending_intent = None
        self.exit_pending = False
        self.pending_trade = None
        self.pending_order_id = None
        self.pending_since = 0.0
        self.pending_exchange_ts = 0
        self.pending_qty = 0
        self.pending_signal_price = 0.0
        self.pending_limit_price = 0.0
        self.pending_exit_reason = ""
        self.pending_ioc_slippage = IOC_SLIPPAGE_POINTS
        self._pending_action = None
        self._exit_order_retry_count = 0
        self._exit_order_retry_at = 0.0

    def handle_session_event(
        self, resp_code: int, event_code: int, info: str, event: str
    ):
        if event_code == 12:
            logger.warning("API 重連中 | resp=%s info=%s", resp_code, info)
            self._mark_disconnected()
        elif event_code == 13:
            logger.info("API 重連成功 | resp=%s", resp_code)
            threading.Thread(
                target=self._on_reconnected, daemon=True, name="reconnect-sync"
            ).start()

    def handle_session_down(self):
        logger.warning("API 連線中斷")
        self._mark_disconnected()

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
            self._disconnect_since = 0.0
            self._session_relogin_attempts = 0
            self._next_relogin_at = 0.0

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

        if self._tick_archiver is None and TICK_ARCHIVE:
            self._tick_archiver = TickArchiver(self.contract.code)
        if self._tick_archiver is not None:
            self._tick_archiver.start()
            logger.info(
                "Tick 落盤已啟用 | TICK_ARCHIVE=1 | code=%s",
                self.contract.code,
            )

        logger.info(
            "VWAP Momentum 策略已啟動 | config=%s | ATR=%.2f | 模擬=%s",
            settings.config_path,
            self.current_atr,
            SIMULATION,
        )

        threading.Thread(target=self._timeout_loop, daemon=True).start()
        self._start_order_worker()

        try:
            while self._running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("策略手動停止")
        finally:
            self._running = False
            if not self._order_sync_mode:
                self._order_queue.put_nowait(None)
            if self._tick_archiver is not None:
                self._tick_archiver.shutdown()
            if self._trading_date is not None:
                self._emit_daily_summary(self._trading_date)
            self.api.logout()
            shutdown_async_logging()

