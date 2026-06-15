"""載入 config.yaml；密鑰與敏感路徑僅來自環境變數。"""

from __future__ import annotations

import datetime
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = _PROJECT_ROOT / "config" / "config.yaml"


def _parse_time(value: str) -> datetime.time:
    hour, minute = value.strip().split(":")
    return datetime.time(int(hour), int(minute))


def _section(data: Mapping[str, Any], name: str) -> dict[str, Any]:
    block = data.get(name)
    return dict(block) if isinstance(block, dict) else {}


@dataclass(frozen=True)
class Settings:
    simulation: bool
    product_code: str

    vwap_window_min: int
    entry_band_points: float
    momentum_vol_1s: int
    momentum_buy_ratio: float
    momentum_sell_ratio: float
    exhaustion_vol: int
    cooldown_sec: int
    max_daily_loss_points: int
    max_consecutive_loss: int
    fixed_tp_points: int
    trail_points: int
    atr_period: int
    min_atr_threshold: float
    atr_refresh_sec: int
    atr_kline_lookback_days: int
    pending_timeout_sec: int
    ioc_slippage_points: int
    exit_grace_ticks: int
    exit_grace_sec: int
    hard_stop_points: int
    vwap_stop_points: int
    no_tick_timeout_sec: int
    clock_skew_warn_sec: float

    session_start: datetime.time
    session_end: datetime.time
    session_flatten_time: datetime.time
    session_force_flatten_time: datetime.time
    flatten_slippage_points: int

    base_vol: int
    atr_vol_mult: float
    open_mult_futures: float
    open_mult_spot: float
    open_mult_normal: float

    log_level: str
    log_file: str

    config_path: Path


def load_config(path: str | Path | None = None) -> Settings:
    config_path = Path(
        path or os.environ.get("CONFIG_PATH", DEFAULT_CONFIG_PATH)
    ).expanduser()
    if not config_path.is_file():
        raise FileNotFoundError(f"找不到設定檔: {config_path}")

    with config_path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    strategy = _section(raw, "strategy")
    session = _section(raw, "session")
    opening = _section(raw, "opening_volume")
    logging_cfg = _section(raw, "logging")

    log_level = os.environ.get("LOG_LEVEL", logging_cfg.get("level", "INFO"))
    log_file = os.environ.get("LOG_FILE", logging_cfg.get("file", ""))

    return Settings(
        simulation=bool(raw.get("simulation", True)),
        product_code=str(raw.get("product_code", "TXFR1")),
        vwap_window_min=int(strategy.get("vwap_window_min", 5)),
        entry_band_points=float(strategy.get("entry_band_points", 2.0)),
        momentum_vol_1s=int(strategy.get("momentum_vol_1s", 150)),
        momentum_buy_ratio=float(strategy.get("momentum_buy_ratio", 0.80)),
        momentum_sell_ratio=float(strategy.get("momentum_sell_ratio", 0.78)),
        exhaustion_vol=int(strategy.get("exhaustion_vol", 15)),
        cooldown_sec=int(strategy.get("cooldown_sec", 10)),
        max_daily_loss_points=int(strategy.get("max_daily_loss_points", 120)),
        max_consecutive_loss=int(strategy.get("max_consecutive_loss", 4)),
        fixed_tp_points=int(strategy.get("fixed_tp_points", 20)),
        trail_points=int(strategy.get("trail_points", 8)),
        atr_period=int(strategy.get("atr_period", 20)),
        min_atr_threshold=float(strategy.get("min_atr_threshold", 25)),
        atr_refresh_sec=int(strategy.get("atr_refresh_sec", 300)),
        atr_kline_lookback_days=int(strategy.get("atr_kline_lookback_days", 10)),
        pending_timeout_sec=int(strategy.get("pending_timeout_sec", 8)),
        ioc_slippage_points=int(strategy.get("ioc_slippage_points", 3)),
        exit_grace_ticks=int(strategy.get("exit_grace_ticks", 60)),
        exit_grace_sec=int(strategy.get("exit_grace_sec", 30)),
        hard_stop_points=int(strategy.get("hard_stop_points", 6)),
        vwap_stop_points=int(strategy.get("vwap_stop_points", 3)),
        no_tick_timeout_sec=int(strategy.get("no_tick_timeout_sec", 45)),
        clock_skew_warn_sec=float(strategy.get("clock_skew_warn_sec", 1.0)),
        session_start=_parse_time(session.get("start", "08:45")),
        session_end=_parse_time(session.get("end", "13:45")),
        session_flatten_time=_parse_time(session.get("flatten_time", "13:40")),
        session_force_flatten_time=_parse_time(
            session.get("force_flatten_time", "13:44")
        ),
        flatten_slippage_points=int(session.get("flatten_slippage_points", 8)),
        base_vol=int(opening.get("base_vol", 150)),
        atr_vol_mult=float(opening.get("atr_vol_mult", 1.0)),
        open_mult_futures=float(opening.get("mult_futures", 2.5)),
        open_mult_spot=float(opening.get("mult_spot", 1.5)),
        open_mult_normal=float(opening.get("mult_normal", 1.0)),
        log_level=str(log_level).upper(),
        log_file=str(log_file or ""),
        config_path=config_path.resolve(),
    )


# 模組載入時讀取一次；man.py 以同名常數 re-export
settings = load_config()

SIMULATION = settings.simulation
PRODUCT_CODE = settings.product_code
VWAP_WINDOW_MIN = settings.vwap_window_min
ENTRY_BAND_POINTS = settings.entry_band_points
MOMENTUM_VOL_1S = settings.momentum_vol_1s
MOMENTUM_BUY_RATIO = settings.momentum_buy_ratio
MOMENTUM_SELL_RATIO = settings.momentum_sell_ratio
EXHAUSTION_VOL = settings.exhaustion_vol
COOLDOWN_SEC = settings.cooldown_sec
MAX_DAILY_LOSS_POINTS = settings.max_daily_loss_points
MAX_CONSECUTIVE_LOSS = settings.max_consecutive_loss
FIXED_TP_POINTS = settings.fixed_tp_points
TRAIL_POINTS = settings.trail_points
ATR_PERIOD = settings.atr_period
MIN_ATR_THRESHOLD = settings.min_atr_threshold
ATR_REFRESH_SEC = settings.atr_refresh_sec
ATR_KLINE_LOOKBACK_DAYS = settings.atr_kline_lookback_days
PENDING_TIMEOUT_SEC = settings.pending_timeout_sec
IOC_SLIPPAGE_POINTS = settings.ioc_slippage_points
EXIT_GRACE_TICKS = settings.exit_grace_ticks
EXIT_GRACE_SEC = settings.exit_grace_sec
HARD_STOP_POINTS = settings.hard_stop_points
VWAP_STOP_POINTS = settings.vwap_stop_points
NO_TICK_TIMEOUT_SEC = settings.no_tick_timeout_sec
CLOCK_SKEW_WARN_SEC = settings.clock_skew_warn_sec
SESSION_START = settings.session_start
SESSION_END = settings.session_end
SESSION_FLATTEN_TIME = settings.session_flatten_time
SESSION_FORCE_FLATTEN_TIME = settings.session_force_flatten_time
FLATTEN_SLIPPAGE_POINTS = settings.flatten_slippage_points
BASE_VOL = settings.base_vol
ATR_VOL_MULT = settings.atr_vol_mult
OPEN_MULT_FUTURES = settings.open_mult_futures
OPEN_MULT_SPOT = settings.open_mult_spot
OPEN_MULT_NORMAL = settings.open_mult_normal
LOG_LEVEL = settings.log_level
LOG_FILE = settings.log_file

# 密鑰僅來自環境變數，不寫入 YAML
API_KEY = os.environ.get("SJ_API_KEY", "YOUR_API_KEY")
SECRET_KEY = os.environ.get("SJ_SEC_KEY", "YOUR_SECRET_KEY")
CA_PATH = os.environ.get("SJ_CA_PATH", "")
CA_PASSWD = os.environ.get("SJ_CA_PASSWD", "")

_DUMP_ORDER_EVENTS = os.environ.get("DUMP_ORDER_EVENTS", "").strip().lower()
DUMP_ORDER_EVENTS = _DUMP_ORDER_EVENTS in ("1", "true", "yes")

_TICK_ARCHIVE = os.environ.get("TICK_ARCHIVE", "").strip().lower()
TICK_ARCHIVE = _TICK_ARCHIVE in ("1", "true", "yes")
