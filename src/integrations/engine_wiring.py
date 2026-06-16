"""Default TradingEngine port wiring for theman apps (live / backtest / tests)."""

from __future__ import annotations

from typing import Any

from config import LOG_FILE, LOG_LEVEL
from core.runtime_config import RuntimeConfig, default_runtime_config
from integrations.alerts_port import ThemanAlertPort
from integrations.archive_port import ThemanArchivePort
from integrations.telemetry_port import ThemanTelemetryPort
from integrations.trend_refresh import ThemanTrendRefresh
from observability import DailyObservability
from strategy.params import StrategyParams
from strategy.vwap_momentum import VWAPMomentumStrategy
from trading_engine.adapters.mock import MockOrderAdapter
from trading_engine.adapters.shioaji import ShioajiOrderAdapter
from trading_engine.logging_setup import setup_async_logging

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


def theman_engine_ports(
    *,
    api: Any,
    use_mock_adapter: bool,
    runtime_config: RuntimeConfig | None = None,
    with_alerts: bool = False,
    with_archive: bool = False,
) -> dict:
    """Return kwargs for ``TradingEngine(api=api, **theman_engine_ports(api=...))``."""
    _ensure_logging()
    cfg = runtime_config or default_runtime_config()
    obs = DailyObservability()
    ports: dict = {
        "runtime_config": cfg,
        "order_adapter": order_adapter_for(api, use_mock=use_mock_adapter),
        "telemetry": ThemanTelemetryPort(obs=obs, runtime_config=cfg),
        "trend_refresh": ThemanTrendRefresh(),
        "obs": obs,
    }
    if with_alerts:
        ports["alerts"] = ThemanAlertPort()
    if with_archive:
        ports["archive"] = ThemanArchivePort()
    return ports


__all__ = [
    "default_strategy",
    "order_adapter_for",
    "theman_engine_ports",
]