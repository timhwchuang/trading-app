"""AlertPort adapter wrapping trading-app alerts."""

from __future__ import annotations

from alerts import send_alert


class TradingAppAlertPort:
    def send(self, message: str, *, level: str = "WARNING") -> bool:
        return send_alert(message, level=level)


__all__ = ["TradingAppAlertPort"]