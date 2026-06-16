"""TelemetryPort adapter wrapping trading-app observability."""

from __future__ import annotations

from typing import Any

from core.runtime_config import RuntimeConfig
from observability import (
    DailyObservability,
    compute_limit_price,
    format_daily_summary,
    format_fill_audit,
)


class TradingAppTelemetryPort:
    def __init__(
        self,
        obs: DailyObservability | None = None,
        runtime_config: RuntimeConfig | None = None,
    ) -> None:
        self._obs = obs or DailyObservability()
        self._runtime_config = runtime_config

    @property
    def underlying(self) -> DailyObservability:
        return self._obs

    def record_lock_wait(self, ms: float) -> None:
        self._obs.record_lock_wait(ms)

    def record_atr(self, atr: float) -> None:
        self._obs.record_atr(atr)

    def record_entry_signal(self) -> None:
        self._obs.record_entry_signal()

    def record_exit_signal(self) -> None:
        self._obs.record_exit_signal()

    def record_tick_type(self, original: int, effective: int) -> None:
        self._obs.record_tick_type(original, effective)

    def record_intent_cancelled(self, tag: str) -> None:
        self._obs.record_intent_cancelled(tag)

    def record_no_tick_resubscribe(self) -> None:
        self._obs.record_no_tick_resubscribe()

    def reset(self) -> None:
        self._obs.reset()

    def snapshot_tick_types(self, counts: Any) -> None:
        self._obs.snapshot_tick_types(counts)

    def update_risk_state(self, daily_pnl: float, consecutive_loss: int) -> None:
        self._obs.update_risk_state(daily_pnl, consecutive_loss)

    def record_fill(self, **kwargs: Any) -> Any:
        return self._obs.record_fill(**kwargs)

    def build_summary(self, trade_date: str) -> dict[str, Any]:
        return self._obs.build_summary(
            trade_date, runtime_config=self._runtime_config
        )

    def format_daily_summary(self, summary: dict[str, Any]) -> str:
        return format_daily_summary(summary)

    def format_fill_audit(self, audit: Any) -> str:
        return format_fill_audit(audit)

    def compute_limit_price(
        self, signal_price: float, *, is_buy: bool, ioc_slippage: int
    ) -> float:
        return compute_limit_price(
            signal_price, is_buy=is_buy, ioc_slippage=ioc_slippage
        )


__all__ = ["TradingAppTelemetryPort"]