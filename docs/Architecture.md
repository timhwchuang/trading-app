# 架構：trading-app + 三 sibling repo（2026-06-17）

> 本文件記錄 **trading-app**（reference integrator）與 `trading-engine` / `trading-backtest` / `strategy-vwap-momentum` 的邊界。
> 安全與紀律仍以 [`AGENTS.md`](../AGENTS.md) 為準（§2 護欄、§4 Gate）。

## 模組歸屬

| 類別 | 角色 | Repo / 路徑 |
| ---- | ---- | ----------- |
| **TradingEngine** | 狀態機、下單、session、risk | `trading-engine` |
| **Backtest** | tick replay + MockBroker | `trading-backtest` |
| **Strategy** | VWAP momentum alpha | `strategy-vwap-momentum` |
| **Integrations** | port wiring | `trading-app/src/integrations/` |
| **Storage** | tick / kbar 落盤 | `trading-app/src/storage/` |
| **Reporting** | UAT log 解析 | `trading-app/src/reporting/` |

## Broker 解耦：`BrokerPort`（已落地）

`TradingEngine` 透過 `self.api` 與券商互動。這個縫**早就存在**：

- Live：`TradingEngine(api=shioaji.Shioaji(...))`
- Backtest：`TradingEngine(api=MockBroker(...))`（且**不走** `start()`，直接驅動 `on_tick`）
- 單測：`TradingEngine(api=MagicMock())`（`tests/test_helpers.make_host`）

[`src/core/ports.py`](../src/core/ports.py) 的 `BrokerPort` Protocol **把這個縫正名**：列出 engine 真正用到的 api 方法/屬性（`login`/`place_order`/`kbars`/`subscribe`/`list_positions`/`set_*_callback`/`on_tick_fop_v1`...）。

- 僅供**型別與文件**用途，不在 runtime 強制；`MockBroker`、`MagicMock` 仍以 duck typing 通過。
- `runtime/engine.py`、`runtime/session.py` 已**移除模組頂層 `import shioaji`**：型別走 `TYPE_CHECKING`、建構與 live-only 路徑走 lazy import。Engine 讀起來即「broker-agnostic」。

### 已落地（Phase 8 + 三 repo 拆分）

- ✅ **TradingEngine**：`trading-engine`（直接 `from trading_engine.engine import TradingEngine`）
- ✅ **Strategy plugin**：`strategy-vwap-momentum`（entry point `vwap_momentum`）
- ✅ **Backtest**：`trading-backtest`；app 的 `backtest/engine.py` 薄 wrapper 注入 `trading_app_engine_ports`
- ✅ **接線**：`integrations/engine_wiring.py` → `trading_app_engine_ports()` + `load_named_strategy()`
- ✅ **CI remote**：`requirements.txt` git pin（`trading-engine@v0.2.2`、`trading-backtest@v0.1.1`、`strategy-vwap-momentum@v0.1.2`）；本地 monorepo 用 `scripts/ci-setup.sh` 或 `pip install -e ../`。升級 SOP → [`UPGRADE_RUNBOOK.md`](UPGRADE_RUNBOOK.md)。

### 刻意保留（下一輪窄縫）

`trading_engine/session.py` 的 `sync_positions` 仍比對 `sj.Action.Buy`（可下一輪與 `order_events` 字串化統一）。

## 資料流（Live / Backtest）

```text
Live:  Shioaji tick → on_tick [lock] → IndicatorState → Strategy.evaluate(MarketSnapshot)
                              ↓ lock 外
       ArchivePort.enqueue → TickArchiver 背景寫 tick_cache/（TICK_ARCHIVE=1）

Backtest: tick_cache/*.csv(.gz) → load_ticks_csv（整日進 RAM）→ iter_replay_ticks → 同一 on_tick 熱路徑
```

| 問題 | 答案 |
| ---- | ---- |
| Live 會不會吃滿記憶體？ | 不會線性成長。指標用**時間窗口** deque（VWAP 5min、動量 1s）；策略只保留 `MomentumState`。 |
| 策略讀硬碟嗎？ | **否**。`strategy-vwap-momentum` 只吃 engine 組好的 `MarketSnapshot`。 |
| 日盤 tick 會落盤嗎？ | `TICK_ARCHIVE=1` 時非同步寫入；queue 滿 10k 會 silent drop（見 `tick_archiver.py`）。 |
| Backtest 記憶體？ | 按日載入整份 CSV 再 yield；非 row streaming。 |

**視窗語意**（`config.yaml`）：VWAP = 5min 滾動 VWMA（非 session 錨定 VWAP）；動量 = 1s；ATR = 20 根 1m K（每 300s 刷新）。P6-1 trend（預設關）有效尺度約 5m×20≈100min，且現用 stride resample，**非**長趨勢 regime。

## 事件驅動（規劃中，尚未實作）

依使用者決策（2026-06-16）：

- **熱路徑維持 in-proc**：on_tick → strategy → arm_pending → enqueue order 永遠本地、lock 內 O(1) + `put_nowait`。**不**把關鍵決策路徑走外部 MQ。
- **事件僅用於 side effects / consumers**（storage、reporting、telemetry）。
- 第一步踏腳石採 **append-only NDJSON 事件檔 sink**（零維運、利於 replay/determinism），**在第一段乾淨 UAT 之後**才做。
- in-proc event bus 若實作，**必須同步、dumb（list-of-callables）、且在 lock 釋放後 emit**——避免破壞回測確定性（threaded fan-out 會破壞單執行緒 replay 的可重現性）。
- RabbitMQ / Kafka 列為 **someday/maybe**，僅在出現真實分散式 consumer 時評估。

### 外部參考：NautilusTrader（借鏡，不照搬）

[NautilusTrader](https://github.com/nautechsystems/nautilus_trader)（Rust 核心 + Python 策略 + Message Bus + Cache）與本專案目標尺度不同（multi-venue / 機構級），但下列概念已對齊或列為 UAT 後改進：

| 借 | 不借 | 本專案現況 / 下一步 |
| --- | --- | --- |
| Research ↔ Live 同語意 | Rust 重寫熱路徑 | ✅ 共用 `on_tick` + `VirtualClock` |
| 統一 domain model + Adapter | 熱路徑走外部 MQ | ✅ `BrokerPort` / `TickSnapshot` / `OrderSignal` |
| Event catalog（可 replay 審計） | Redis / 分散式 state | 已有 `SIGNAL_AUDIT` / `FILL_AUDIT` → **NDJSON sink**（UAT 後） |
| Cache 作為資料面抽象 | 奈秒精度 / 多 venue | `tick_cache` + `kbar_cache` → 可選 **CachePort** 統一讀寫 |
| Bar 聚合在 cache 層 | 全事件驅動 Actor API | HTF 若要做：在 cache/engine 產 bar，再餵 snapshot；**非**策略自拉 kbars |

**決策紀錄（2026-06-17）**：P6-1 `trend_filter_enabled` 維持 false；日盤 09:45 後短趨勢不需夜盤 tick。見 [`WeeklyStatus.md`](WeeklyStatus.md)。

## 時序與相容性原則

- 任何新縫以**可選參數 + 安全預設**加入；`make_host` 簽名維持相容。
- `python run_tests.py` 每次須全綠（trading-app 基線 **79**；siblings 各自維護）；回測 SIGNAL_AUDIT / FILL_AUDIT / DAILY_SUMMARY 與最終 host 狀態須與重構前一致。
- **tick_cache 路徑**：app 層一律用 `storage.cache_paths.DEFAULT_TICK_CACHE_DIR`（repo 根 `tick_cache/`），勿用 `trading_backtest.loader` 的 cwd 預設。
- live 入口（`python -m live`）行為不變。
- package 搬移（`src/trading_engine/`）延後到出現第二個 app/strategy 才動；先以 `__init__` re-export 取得多數好處。
