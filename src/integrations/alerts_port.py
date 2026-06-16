"""AlertPort adapter wrapping theman alerts."""

from __future__ import annotations

from alerts import send_alert


class ThemanAlertPort:
    def send(self, message: str, *, level: str = "WARNING") -> bool:
        return send_alert(message, level=level)


__all__ = ["ThemanAlertPort"]