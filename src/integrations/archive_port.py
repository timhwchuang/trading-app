"""ArchivePort adapter wrapping trading-app storage."""

from __future__ import annotations

import datetime
from typing import Any, Optional

from storage.kbar_archiver import archive_kbars_snapshot
from storage.tick_archiver import TickArchiver


class TradingAppArchivePort:
    def __init__(self) -> None:
        self._tick_archiver: Optional[TickArchiver] = None

    def maybe_start_tick_archive(self, product_code: str) -> TickArchiver:
        if self._tick_archiver is None:
            self._tick_archiver = TickArchiver(product_code)
            self._tick_archiver.start()
        return self._tick_archiver

    def enqueue_tick(self, tick: Any, tick_type: int) -> None:
        if self._tick_archiver is not None:
            self._tick_archiver.enqueue_tick(tick, tick_type)

    def shutdown_tick_archive(self) -> None:
        if self._tick_archiver is not None:
            self._tick_archiver.shutdown()
            self._tick_archiver = None

    def archive_kbars(
        self, kbars: Any, *, product_code: str, trade_date: datetime.date
    ) -> None:
        archive_kbars_snapshot(
            kbars, product_code=product_code, trade_date=trade_date
        )


__all__ = ["TradingAppArchivePort"]