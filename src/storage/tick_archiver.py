"""P0-11: Non-blocking UAT tick archiver (callback enqueue + background CSV writer)."""

from __future__ import annotations

import atexit
import csv
import datetime
import gzip
import logging
import queue
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from storage.tick_loader import DEFAULT_CACHE_DIR, TICK_CSV_FIELDS, cache_path

logger = logging.getLogger(__name__)

DEFAULT_QUEUE_MAXSIZE = 10_000
DEFAULT_FLUSH_BATCH = 500
DEFAULT_FLUSH_INTERVAL_SEC = 2.0


@dataclass(frozen=True)
class TickArchiveRecord:
    datetime: datetime.datetime
    close: str
    volume: int
    tick_type: int
    bid_price: float = 0.0
    ask_price: float = 0.0

    def to_row(self) -> dict[str, Any]:
        return {
            "datetime": self.datetime.isoformat(),
            "close": self.close,
            "volume": self.volume,
            "bid_price": self.bid_price,
            "ask_price": self.ask_price,
            "tick_type": self.tick_type,
        }


def gzip_csv_file(csv_path: Path) -> Path:
    """Compress a closed ``*.csv`` to ``*.csv.gz`` and remove the plain file."""
    csv_path = Path(csv_path)
    gz_path = Path(str(csv_path) + ".gz")
    with csv_path.open("rb") as f_in:
        with gzip.open(gz_path, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
    csv_path.unlink()
    logger.info("Tick 快取已壓縮 | %s → %s", csv_path.name, gz_path.name)
    return gz_path


class TickArchiver:
    """Background writer: ``on_tick`` only ``put_nowait``; never blocks callback."""

    def __init__(
        self,
        product_code: str,
        *,
        cache_dir: Path = DEFAULT_CACHE_DIR,
        queue_maxsize: int = DEFAULT_QUEUE_MAXSIZE,
        flush_batch: int = DEFAULT_FLUSH_BATCH,
        flush_interval_sec: float = DEFAULT_FLUSH_INTERVAL_SEC,
    ) -> None:
        self._product_code = product_code
        self._cache_dir = Path(cache_dir)
        self._queue: queue.Queue[TickArchiveRecord] = queue.Queue(
            maxsize=queue_maxsize
        )
        self._flush_batch = flush_batch
        self._flush_interval_sec = flush_interval_sec
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._shutdown_done = False
        self._dropped = 0
        self._written = 0
        self._current_date: Optional[datetime.date] = None
        self._current_path: Optional[Path] = None
        self._file = None
        self._writer: Optional[csv.DictWriter] = None
        self._pending_rows: list[dict[str, Any]] = []
        self._last_flush_mono = time.monotonic()

    @property
    def dropped(self) -> int:
        return self._dropped

    @property
    def written(self) -> int:
        return self._written

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="tick-archiver",
        )
        self._thread.start()
        atexit.register(self.shutdown)

    def enqueue(self, record: TickArchiveRecord) -> None:
        try:
            self._queue.put_nowait(record)
        except queue.Full:
            self._dropped += 1

    def enqueue_tick(self, tick: Any, tick_type: int) -> None:
        bid = float(getattr(tick, "bid_price", 0) or 0)
        ask = float(getattr(tick, "ask_price", 0) or 0)
        self.enqueue(
            TickArchiveRecord(
                datetime=tick.datetime,
                close=str(tick.close),
                volume=int(tick.volume),
                tick_type=int(tick_type),
                bid_price=bid,
                ask_price=ask,
            )
        )

    def shutdown(self) -> None:
        if self._shutdown_done:
            return
        self._shutdown_done = True
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=30.0)
            self._thread = None
        logger.info(
            "Tick 落盤結束 | written=%d dropped=%d path=%s",
            self._written,
            self._dropped,
            self._current_path,
        )

    def _run(self) -> None:
        while not self._stop.is_set() or not self._queue.empty():
            try:
                record = self._queue.get(timeout=0.1)
            except queue.Empty:
                self._maybe_flush()
                continue
            self._write_record(record)
            if len(self._pending_rows) >= self._flush_batch:
                self._flush(force=True)
            else:
                self._maybe_flush()
        self._flush(force=True)
        self._close_current_file()

    def _write_record(self, record: TickArchiveRecord) -> None:
        tick_date = record.datetime.date()
        if self._current_date != tick_date:
            self._rotate_to_date(tick_date)
        self._pending_rows.append(record.to_row())
        self._written += 1

    def _rotate_to_date(self, new_date: datetime.date) -> None:
        if self._current_date is not None and self._current_path is not None:
            self._flush(force=True)
            closed_path = self._current_path
            self._close_file_handles()
            if closed_path.is_file():
                try:
                    gzip_csv_file(closed_path)
                except OSError as e:
                    logger.warning("跨日 gzip 失敗 | %s: %s", closed_path, e)
        self._current_date = new_date
        self._open_file_for_date(new_date)

    def _open_file_for_date(self, date: datetime.date) -> None:
        path = cache_path(self._cache_dir, self._product_code, date)
        path.parent.mkdir(parents=True, exist_ok=True)
        needs_header = not path.is_file() or path.stat().st_size == 0
        self._file = path.open("a", encoding="utf-8", newline="")
        self._writer = csv.DictWriter(self._file, fieldnames=TICK_CSV_FIELDS)
        if needs_header:
            self._writer.writeheader()
        self._current_path = path

    def _maybe_flush(self) -> None:
        if not self._pending_rows:
            return
        elapsed = time.monotonic() - self._last_flush_mono
        if elapsed >= self._flush_interval_sec:
            self._flush(force=True)

    def _flush(self, *, force: bool = False) -> None:
        if not self._pending_rows:
            return
        if not force and len(self._pending_rows) < self._flush_batch:
            return
        if self._writer is None or self._file is None:
            return
        for row in self._pending_rows:
            self._writer.writerow(row)
        self._file.flush()
        self._pending_rows.clear()
        self._last_flush_mono = time.monotonic()

    def _close_file_handles(self) -> None:
        if self._file is not None:
            try:
                self._file.close()
            except OSError:
                pass
        self._file = None
        self._writer = None

    def _close_current_file(self) -> None:
        """Shutdown: flush today's plain CSV; do not gzip in-progress day file."""
        self._flush(force=True)
        self._close_file_handles()
