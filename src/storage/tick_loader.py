"""Phase 0: Shioaji historical tick loader + local cache for backtesting.

職責：
* 透過 ``api.ticks(contract, date, query_type=AllDay)`` 抓取歷史 tick。
* 落地成本地 CSV 快取（純 stdlib，不依賴 pandas/pyarrow），回測一律讀快取。
* 配額感知：抓取前後記錄 ``api.usage()``，剩餘 < 10% 告警。
* 提供 ``ReplayTick`` 與線上 ``TickFOPv1`` 同構的屬性（datetime/close/volume/tick_type），
  讓回測重放可直接餵進 ``TradingEngine.on_tick``。

Shioaji 歷史資料限制（務必知悉）：
* 只有「最佳一檔」買賣價，沒有歷史 order book 深度，無排隊位置。
* 只能抓過去日期，且受 ``usage().limit_bytes`` 流量配額限制。
* 歷史 ``Ticks`` 無 ``simtrade`` 旗標（試搓單過濾僅適用即時串流）。
"""

from __future__ import annotations

import csv
import datetime
import gzip
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, IO, Iterable, Iterator, List, Optional

logger = logging.getLogger(__name__)

from storage.cache_paths import DEFAULT_CACHE_DIR, DEFAULT_TICK_CACHE_DIR

TAIWAN_TZ = datetime.timezone(datetime.timedelta(hours=8))

TICK_CSV_FIELDS = [
    "datetime",
    "close",
    "volume",
    "bid_price",
    "ask_price",
    "tick_type",
]
_CSV_FIELDS = TICK_CSV_FIELDS


@dataclass
class ReplayTick:
    """與 TickFOPv1 同構的最小重放單元（策略只用 datetime/close/volume/tick_type）。"""

    datetime: datetime.datetime
    close: str
    volume: int
    tick_type: int
    bid_price: float = 0.0
    ask_price: float = 0.0


def _ns_to_taipei_naive(ts_ns: int) -> datetime.datetime:
    """Shioaji ts 為奈秒 epoch；轉成台北 naive local（與線上 tick.datetime 同構）。"""
    aware = datetime.datetime.fromtimestamp(ts_ns / 1_000_000_000, TAIWAN_TZ)
    return aware.replace(tzinfo=None)


def fetch_ticks_for_date(
    api: Any, contract: Any, date: datetime.date
) -> List[ReplayTick]:
    """呼叫 api.ticks(AllDay) 取單日 tick，回傳依時間排序的 ReplayTick。"""
    import shioaji as sj

    raw = api.ticks(
        contract=contract,
        date=date.isoformat(),
        query_type=sj.TicksQueryType.AllDay,
    )
    ts = list(raw.ts)
    close = list(raw.close)
    volume = list(raw.volume)
    bid = list(getattr(raw, "bid_price", []) or [])
    ask = list(getattr(raw, "ask_price", []) or [])
    tick_type = list(getattr(raw, "tick_type", []) or [])

    ticks: List[ReplayTick] = []
    for i in range(len(ts)):
        ticks.append(
            ReplayTick(
                datetime=_ns_to_taipei_naive(int(ts[i])),
                close=str(close[i]),
                volume=int(volume[i]),
                tick_type=int(tick_type[i]) if i < len(tick_type) else 0,
                bid_price=float(bid[i]) if i < len(bid) else 0.0,
                ask_price=float(ask[i]) if i < len(ask) else 0.0,
            )
        )
    ticks.sort(key=lambda t: t.datetime)
    return ticks


def cache_path(cache_dir: Path, code: str, date: datetime.date) -> Path:
    return Path(cache_dir) / f"{code}_{date.isoformat()}.csv"


def cache_gz_path(cache_dir: Path, code: str, date: datetime.date) -> Path:
    return Path(cache_dir) / f"{code}_{date.isoformat()}.csv.gz"


def resolve_tick_cache_path(
    cache_dir: Path, code: str, date: datetime.date
) -> Optional[Path]:
    """Prefer ``*.csv.gz`` over plain ``*.csv`` when both exist."""
    gz = cache_gz_path(cache_dir, code, date)
    plain = cache_path(cache_dir, code, date)
    if gz.is_file():
        return gz
    if plain.is_file():
        return plain
    return None


def _open_tick_csv_reader(path: Path) -> IO[str]:
    path = Path(path)
    if path.suffix == ".gz" or path.name.endswith(".csv.gz"):
        return gzip.open(path, "rt", encoding="utf-8", newline="")
    return path.open("r", encoding="utf-8", newline="")


def save_ticks_csv(ticks: Iterable[ReplayTick], path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS)
        writer.writeheader()
        for t in ticks:
            writer.writerow(
                {
                    "datetime": t.datetime.isoformat(),
                    "close": t.close,
                    "volume": t.volume,
                    "bid_price": t.bid_price,
                    "ask_price": t.ask_price,
                    "tick_type": t.tick_type,
                }
            )
            count += 1
    return count


def load_ticks_csv(path: Path) -> List[ReplayTick]:
    ticks: List[ReplayTick] = []
    with _open_tick_csv_reader(Path(path)) as f:
        for row in csv.DictReader(f):
            ticks.append(
                ReplayTick(
                    datetime=datetime.datetime.fromisoformat(row["datetime"]),
                    close=row["close"],
                    volume=int(row["volume"]),
                    tick_type=int(row["tick_type"]),
                    bid_price=float(row["bid_price"]),
                    ask_price=float(row["ask_price"]),
                )
            )
    return ticks


def _log_usage(api: Any, context: str) -> None:
    try:
        usage = api.usage()
    except Exception as e:
        logger.warning("usage 查詢失敗 (%s): %s", context, e)
        return
    logger.info(
        "API usage [%s] | bytes=%s limit=%s remaining=%s",
        context,
        usage.bytes,
        usage.limit_bytes,
        usage.remaining_bytes,
    )
    if usage.limit_bytes > 0 and usage.remaining_bytes < usage.limit_bytes * 0.1:
        logger.warning(
            "API 流量剩餘 < 10%% | remaining=%s limit=%s 建議暫停抓取",
            usage.remaining_bytes,
            usage.limit_bytes,
        )


def download_and_cache(
    api: Any,
    contract: Any,
    dates: Iterable[datetime.date],
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    overwrite: bool = False,
) -> List[Path]:
    """逐日抓取並落地快取；已存在且非 overwrite 則跳過。回傳實際寫入/已存在的路徑。"""
    code = getattr(contract, "code", str(contract))
    written: List[Path] = []
    _log_usage(api, "download_start")
    for date in dates:
        path = cache_path(cache_dir, code, date)
        if path.is_file() and not overwrite:
            logger.info("快取已存在，跳過 %s", path.name)
            written.append(path)
            continue
        try:
            ticks = fetch_ticks_for_date(api, contract, date)
        except Exception as e:
            logger.warning("抓取 %s %s 失敗: %s", code, date, e)
            continue
        n = save_ticks_csv(ticks, path)
        logger.info("已快取 %s | %d ticks → %s", date.isoformat(), n, path.name)
        written.append(path)
    _log_usage(api, "download_end")
    return written


def iter_replay_ticks(
    code: str,
    dates: Iterable[datetime.date],
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> Iterator[ReplayTick]:
    """依日期序讀取本地快取並逐筆 yield（跨日 tick 連續輸出，驅動 P0-8 跨日重置）。"""
    for date in dates:
        path = resolve_tick_cache_path(cache_dir, code, date)
        if path is None:
            logger.warning(
                "快取缺檔，略過 %s_%s",
                code,
                date.isoformat(),
            )
            continue
        for tick in load_ticks_csv(path):
            yield tick


def date_range(start: datetime.date, end: datetime.date) -> List[datetime.date]:
    days = (end - start).days
    return [start + datetime.timedelta(days=i) for i in range(days + 1)]
