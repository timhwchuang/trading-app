"""Trading-app bridge: YAML settings → trading_engine.RuntimeConfig."""

from __future__ import annotations

from dataclasses import fields

import config as _config_module
from config import Settings as AppSettings, load_config, settings

from trading_engine.core.runtime_config import (
    RuntimeConfig as EngineRuntimeConfig,
    SWEEP_FIELD_TO_CONST,
    normalize_overlay_key,
)
from trading_engine.settings import Settings as EngineSettings

RuntimeConfig = EngineRuntimeConfig
RuntimeConfigBase = EngineSettings


def _to_engine_settings(src: AppSettings | None = None) -> EngineSettings:
    base = src or settings
    data = {f.name: getattr(base, f.name) for f in fields(EngineSettings)}
    return EngineSettings(**data)


class TradingAppRuntimeConfig(EngineRuntimeConfig):
    """Extends engine RuntimeConfig with app env-gated flags from config module."""

    @property
    def dump_order_events(self) -> bool:
        return _config_module.DUMP_ORDER_EVENTS

    @property
    def tick_archive(self) -> bool:
        return _config_module.TICK_ARCHIVE

    @property
    def kbars_archive(self) -> bool:
        return _config_module.KBARS_ARCHIVE


def default_runtime_config() -> TradingAppRuntimeConfig:
    load_config()
    return TradingAppRuntimeConfig(_to_engine_settings())


__all__ = [
    "RuntimeConfig",
    "RuntimeConfigBase",
    "SWEEP_FIELD_TO_CONST",
    "TradingAppRuntimeConfig",
    "default_runtime_config",
    "normalize_overlay_key",
]