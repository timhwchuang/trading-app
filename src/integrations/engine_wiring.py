"""Default TradingEngine port wiring for trading-app (live / backtest / tests)."""

from __future__ import annotations

from typing import Any

from config import LOG_FILE, LOG_LEVEL
from core.runtime_config import RuntimeConfig, default_runtime_config
from integrations.alerts_port import TradingAppAlertPort
from integrations.archive_port import TradingAppArchivePort
from integrations.telemetry_port import TradingAppTelemetryPort
from integrations.trend_refresh import TradingAppTrendRefresh
from observability import DailyObservability
from strategy_vwap_momentum import StrategyParams, VWAPMomentumStrategy
from trading_engine.adapters.mock import MockOrderAdapter
from trading_engine.adapters.shioaji import ShioajiOrderAdapter
from trading_engine.logging_setup import setup_async_logging
from trading_engine.plugins import load_strategy

_logging_configured = False


def _ensure_logging() -> None:
    global _logging_configured
    if not _logging_configured:
        setup_async_logging(level=LOG_LEVEL, log_file=LOG_FILE)
        _logging_configured = True


def order_adapter_for(api: Any, *, use_mock: bool) -> Any:
    """Explicit adapter selection at the wiring layer (no api heuristics)."""
    if use_mock:
        return MockOrderAdapter(api)
    return ShioajiOrderAdapter(api)


def default_strategy(
    cfg: RuntimeConfig,
    obs: DailyObservability,
) -> VWAPMomentumStrategy:
    return VWAPMomentumStrategy(
        params=StrategyParams.from_runtime_config(cfg),
        obs=obs,
    )


def load_named_strategy(
    name: str,
    cfg: RuntimeConfig,
    obs: DailyObservability,
) -> Any:
    """Load strategy via entry point; falls back to explicit default for vwap_momentum."""
    if name == "vwap_momentum":
        return default_strategy(cfg, obs)
    return load_strategy(
        name,
        params=StrategyParams.from_runtime_config(cfg),
        obs=obs,
    )


def trading_app_engine_ports(
    *,
    api: Any,
    use_mock_adapter: bool,
    runtime_config: RuntimeConfig | None = None,
    with_alerts: bool = False,
    with_archive: bool = False,
) -> dict:
    """Return kwargs for ``TradingEngine(api=api, **trading_app_engine_ports(api=...))``."""
    _ensure_logging()
    cfg = runtime_config or default_runtime_config()
    obs = DailyObservability()
    ports: dict = {
        "runtime_config": cfg,
        "order_adapter": order_adapter_for(api, use_mock=use_mock_adapter),
        "telemetry": TradingAppTelemetryPort(obs=obs, runtime_config=cfg),
        "trend_refresh": TradingAppTrendRefresh(),
        "obs": obs,
    }
    if with_alerts:
        ports["alerts"] = TradingAppAlertPort()
    if with_archive:
        ports["archive"] = TradingAppArchivePort()
    return ports


__all__ = [
    "default_strategy",
    "load_named_strategy",
    "order_adapter_for",
    "trading_app_engine_ports",
]