# 架構：trading-app + 三 sibling repo（2026-06-16）

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
- ✅ **CI remote**：`requirements.txt` git pin（`trading-engine@v0.2.0`、`trading-backtest@v0.1.1`、`strategy-vwap-momentum@v0.1.1`）；本地 monorepo 用 `scripts/ci-setup.sh` 或 `pip install -e ../`。

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
- `python run_tests.py` 每次須全綠（trading-app 基線 **79**；siblings 各自維護）；回測 SIGNAL_AUDIT / FILL_AUDIT / DAILY_SUMMARY 與最終 host 狀態須與重構前一致。
- **tick_cache 路徑**：app 層一律用 `storage.cache_paths.DEFAULT_TICK_CACHE_DIR`（repo 根 `tick_cache/`），勿用 `trading_backtest.loader` 的 cwd 預設。
- live 入口（`python -m live`）行為不變。
- package 搬移（`src/trading_engine/`）延後到出現第二個 app/strategy 才動；先以 `__init__` re-export 取得多數好處。
