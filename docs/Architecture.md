# 架構：四大類 + Broker 解耦（Phase 8 進行中）

> 本文件記錄「把可重用核心從 theman 抽離」的目標架構與**目前已落地的第一步**。
> 安全與紀律仍以 [`AGENTS.md`](../AGENTS.md) 為準（§2 護欄、§4 Gate）。

## 目標：四大類（pillars）

| 類別 | 角色 | 現況 |
| ---- | ---- | ---- |
| **TradingEngine** | 有狀態的決策＋執行宿主（單一狀態機；on_tick / pending / fills / session / risk） | `src/runtime/`（live + backtest 共用） |
| **Backtest** | tick 回放驅動 + Mock 撮合（重用 TradingEngine） | `src/backtest/`（`BacktestEngine.host = TradingEngine`） |
| **Storage** | tick / kbar 落盤與載入 | `src/storage/`（未來可轉事件 consumer） |
| **Reporting** | log 解析 + 績效/UAT 指標 | `src/reporting/`（未來可轉事件 stream consumer） |

## Broker 解耦：`BrokerPort`（已落地）

`TradingEngine` 透過 `self.api` 與券商互動。這個縫**早就存在**：

- Live：`TradingEngine(api=shioaji.Shioaji(...))`
- Backtest：`TradingEngine(api=MockBroker(...))`（且**不走** `start()`，直接驅動 `on_tick`）
- 單測：`TradingEngine(api=MagicMock())`（`tests/test_helpers.make_host`）

[`src/core/ports.py`](../src/core/ports.py) 的 `BrokerPort` Protocol **把這個縫正名**：列出 engine 真正用到的 api 方法/屬性（`login`/`place_order`/`kbars`/`subscribe`/`list_positions`/`set_*_callback`/`on_tick_fop_v1`...）。

- 僅供**型別與文件**用途，不在 runtime 強制；`MockBroker`、`MagicMock` 仍以 duck typing 通過。
- `runtime/engine.py`、`runtime/session.py` 已**移除模組頂層 `import shioaji`**：型別走 `TYPE_CHECKING`、建構與 live-only 路徑走 lazy import。Engine 讀起來即「broker-agnostic」。

### 已落地（Phase 8 + 三 repo 拆分）

- ✅ **TradingEngine**：獨立 repo `../trading-engine`（`pip install -e ../trading-engine`）；theman `src/runtime/` 為 re-export 薄層。
- ✅ **Strategy Protocol v1**：`trading_engine.core.strategy` 僅 `evaluate` + `reset` + optional helpers；momentum 狀態在 `strategy-vwap-momentum` plugin。
- ✅ **Strategy plugin**：`../strategy-vwap-momentum`（entry point `vwap_momentum`）；theman `src/strategy/` 為 re-export。
- ✅ **Backtest**：`../trading-backtest` 含 replay loop + MockBroker；theman `BacktestEngine` 薄 wrapper 注入 `theman_engine_ports`。
- ✅ **接線**：`integrations/engine_wiring.py` → `theman_engine_ports()` + `load_named_strategy()`；live/backtest 顯式 adapter。
- 🔜 **CI remote**：GitHub 僅 checkout theman 時需 submodule 或發布 PyPI；本地 monorepo 用 `scripts/ci-setup.sh`。

### 刻意保留（下一輪窄縫）

`trading_engine/session.py` 的 `sync_positions` 仍比對 `sj.Action.Buy`（可下一輪與 `order_events` 字串化統一）。

## 事件驅動（規劃中，尚未實作）

依使用者決策（2026-06-16）：

- **熱路徑維持 in-proc**：on_tick → strategy → arm_pending → enqueue order 永遠本地、lock 內 O(1) + `put_nowait`。**不**把關鍵決策路徑走外部 MQ。
- **事件僅用於 side effects / consumers**（storage、reporting、telemetry）。
- 第一步踏腳石採 **append-only NDJSON 事件檔 sink**（零維運、利於 replay/determinism），**在第一段乾淨 UAT 之後**才做。
- in-proc event bus 若實作，**必須同步、dumb（list-of-callables）、且在 lock 釋放後 emit**——避免破壞回測確定性（threaded fan-out 會破壞單執行緒 replay 的可重現性）。
- RabbitMQ / Kafka 列為 **someday/maybe**，僅在出現真實分散式 consumer 時評估。

## 時序與相容性原則

- 任何新縫以**可選參數 + 安全預設**加入；`make_host` 簽名維持相容。
- `python run_tests.py` 每次須全綠（基線 **155**）；回測 SIGNAL_AUDIT / FILL_AUDIT / DAILY_SUMMARY 與最終 host 狀態須與重構前一致。
- live 入口（`python -m live`）行為不變。
- package 搬移（`src/trading_engine/`）延後到出現第二個 app/strategy 才動；先以 `__init__` re-export 取得多數好處。
