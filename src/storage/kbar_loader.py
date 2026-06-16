"""K-bar cache I/O for backtest ATR warmup."""

from __future__ import annotations

import csv
import datetime
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, List, Optional

from storage.tick_loader import (
    DEFAULT_CACHE_DIR,
    _log_usage,
    _ns_to_taipei_naive,
    date_range,
)

logger = logging.getLogger(__name__)

_KBARS_CSV_FIELDS = ["ts", "Open", "High", "Low", "Close", "Volume"]


@dataclass
class KBarRecord:
    ts: datetime.datetime
    Open: float
    High: float
    Low: float
    Close: float
    Volume: int


def kbars_cache_path(cache_dir: Path, code: str, date: datetime.date) -> Path:
    return Path(cache_dir) / f"{code}_kbars_{date.isoformat()}.csv"


def save_kbars_csv(bars: Iterable[KBarRecord], path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_KBARS_CSV_FIELDS)
        writer.writeheader()
        for bar in bars:
            writer.writerow(
                {
                    "ts": bar.ts.isoformat(),
                    "Open": bar.Open,
                    "High": bar.High,
                    "Low": bar.Low,
                    "Close": bar.Close,
                    "Volume": bar.Volume,
                }
            )
            count += 1
    return count


def load_kbars_csv(path: Path) -> List[KBarRecord]:
    bars: List[KBarRecord] = []
    with Path(path).open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            bars.append(
                KBarRecord(
                    ts=datetime.datetime.fromisoformat(row["ts"]),
                    Open=float(row["Open"]),
                    High=float(row["High"]),
                    Low=float(row["Low"]),
                    Close=float(row["Close"]),
                    Volume=int(row["Volume"]),
                )
            )
    bars.sort(key=lambda b: b.ts)
    return bars


def _kbars_raw_to_records(raw: Any) -> List[KBarRecord]:
    ts_list = list(raw.ts)
    opens = list(raw.Open)
    highs = list(raw.High)
    lows = list(raw.Low)
    closes = list(raw.Close)
    volumes = list(getattr(raw, "Volume", []) or [])
    bars: List[KBarRecord] = []
    for i in range(len(ts_list)):
        bars.append(
            KBarRecord(
                ts=_ns_to_taipei_naive(int(ts_list[i])),
                Open=float(opens[i]),
                High=float(highs[i]),
                Low=float(lows[i]),
                Close=float(closes[i]),
                Volume=int(volumes[i]) if i < len(volumes) else 0,
            )
        )
    bars.sort(key=lambda b: b.ts)
    return bars


def fetch_kbars_for_date(
    api: Any, contract: Any, date: datetime.date
) -> List[KBarRecord]:
    """呼叫 api.kbars 取單日 1 分 K，回傳依時間排序的 KBarRecord。"""
    raw = api.kbars(
        contract=contract,
        start=date.isoformat(),
        end=date.isoformat(),
    )
    return _kbars_raw_to_records(raw)


def download_and_cache_kbars(
    api: Any,
    contract: Any,
    dates: Iterable[datetime.date],
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    overwrite: bool = False,
    preload_dates: Optional[Iterable[datetime.date]] = None,
) -> List[Path]:
    """逐日抓取 K 線並落地快取；preload_dates 供 ATR 熱身（6.5）預載前日/夜盤。"""
    code = getattr(contract, "code", str(contract))
    all_dates: list[datetime.date] = []
    seen: set[datetime.date] = set()
    for group in (dates, preload_dates or ()):
        for date in group:
            if date not in seen:
                seen.add(date)
                all_dates.append(date)
    written: List[Path] = []
    _log_usage(api, "kbars_download_start")
    for date in all_dates:
        path = kbars_cache_path(cache_dir, code, date)
        if path.is_file() and not overwrite:
            logger.info("K 線快取已存在，跳過 %s", path.name)
            written.append(path)
            continue
        try:
            bars = fetch_kbars_for_date(api, contract, date)
        except Exception as e:
            logger.warning("抓取 K 線 %s %s 失敗: %s", code, date, e)
            continue
        n = save_kbars_csv(bars, path)
        logger.info("已快取 K 線 %s | %d bars → %s", date.isoformat(), n, path.name)
        written.append(path)
    _log_usage(api, "kbars_download_end")
    return written


def iter_kbars_in_range(
    code: str,
    start: datetime.date,
    end: datetime.date,
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> List[KBarRecord]:
    """讀取 [start, end] 日曆日範圍內所有已快取 K 線（缺檔略過）。"""
    bars: List[KBarRecord] = []
    for date in date_range(start, end):
        path = kbars_cache_path(cache_dir, code, date)
        if not path.is_file():
            continue
        bars.extend(load_kbars_csv(path))
    bars.sort(key=lambda b: b.ts)
    return bars
