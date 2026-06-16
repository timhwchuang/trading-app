# Phase 8 Merge Fix Spec

**Date**: 2026-06-16  
**Sources**: [CodeReview-Phase8-Step1-20260616.md](CodeReview-Phase8-Step1-20260616.md) + Cursor review (same day)  
**Branch**: `feature/refactor-tradingengine`  
**Gate**: `python run_tests.py` 155 全綠 + UAT 觀測契約不 regress + CI 可重現

---

## Verdict

| 維度 | 狀態 |
| ---- | ---- |
| 架構方向 | ✅ 正確（sibling `trading-engine` + `integrations/` 薄接線） |
| 測試 | ✅ 155 全綠（本地） |
| Merge 就緒 | ❌ **需完成下方 Blocker + P0 後再 merge** |

---

## Blocker（merge 前必做）

### B1 — `trading-engine` 必須可被 CI / 他人 clone 後解析

| | |
| - | - |
| **問題** | `run_tests.py` 依賴 sibling `../trading-engine/src`；`trading-engine/` 不在 theman git 內 → GitHub Actions / 新機 `ImportError` |
| **來源** | Cursor review P0 |
| **驗收** | 乾淨 clone 後 `python run_tests.py` 全綠（無手動放 sibling 目錄） |
| **方案（擇一）** | |

1. **git submodule**（推薦過渡）：`theman` 引用 `trading-engine` repo；CI `submodules: recursive`
2. **monorepo**：`theman/vendor/trading-engine` 或 workspace root 統一版控
3. **CI 多 checkout**：workflow 同時拉兩個 repo 到固定相對路徑
4. **pip 依賴**：`pip install -e ../trading-engine`；`requirements.txt` / `pyproject.toml` 聲明 path dep

**CI 變更**（`.github/workflows/ci.yml`）：

```yaml
# 範例：submodule 或 pip install -e 後再跑
- run: pip install -e ../trading-engine   # 若採 editable
- run: python run_tests.py
  working-directory: theman
```

---

### B2 — 日誌回歸：`LOG_FILE` / `LOG_LEVEL` 未套用

| | |
| - | - |
| **問題** | `trading_engine.logging_setup.setup_async_logging()` 預設 `INFO` + 空 `log_file`；engine/session 模組 import 時無參數呼叫 → UAT `LOG_FILE` 輪替檔不寫入 |
| **來源** | Cursor review P0 |
| **檔案** | `trading-engine/.../logging_setup.py`；`theman/src/integrations/engine_wiring.py` 或 `live/__main__.py` |
| **修法** | 在 app 啟動（`theman_engine_ports` 或 `live.main`）**最早**呼叫： |

```python
from config import LOG_FILE, LOG_LEVEL
from trading_engine.logging_setup import setup_async_logging
setup_async_logging(level=LOG_LEVEL, log_file=LOG_FILE)
```

| **驗收** | 設 `LOG_FILE=/tmp/uat.log` 跑短回測或單測觸發 log → 檔案有 `SIGNAL_AUDIT` / `DAILY_SUMMARY` 行 |

---

### B3 — 策略 observability 斷線（`VWAPMomentumStrategy.obs`）

| | |
| - | - |
| **問題** | 舊：`VWAPMomentumStrategy(obs=engine._obs)`。新：`ThemanTelemetryPort` 內有 `DailyObservability`，但 strategy 建構皆未傳 `obs` → `near_miss` / momentum / trend_veto 計數不進 `DAILY_SUMMARY` |
| **來源** | Cursor review P0 |
| **檔案** | `integrations/engine_wiring.py`；`live/__main__.py`；`backtest/engine.py`；`tests/test_helpers.py` |
| **修法** | `theman_engine_ports()` 建立**單一** `obs = DailyObservability()`，注入 `ThemanTelemetryPort(obs=obs)`；對外回傳 `obs` 或提供 `default_strategy(cfg, obs)` helper，所有 `VWAPMomentumStrategy(..., obs=obs)` 共用同一實例 |
| **驗收** | 單測或手動：觸發 momentum entry 路徑後 `build_summary()` 的 `near_miss` 欄位非空／與重構前一致；`uat_report` 解析欄位不缺失 |

---

### B4 — `order_adapter` 選擇邏輯不得留在 trading-engine（`hasattr(api, "inflight")`）

| | |
| - | - |
| **問題** | `trading_engine/engine.py:_default_order_adapter` 用 theman `MockBroker.inflight` 啟發式選 adapter；`MagicMock` 亦會誤觸發 `inflight` |
| **來源** | CodeReview Issue 1 + Cursor P1 |
| **修法** | |

1. `TradingEngine.__init__`：`order_adapter` **必填**（或 `None` → 明確 `NullOrderAdapter` 拋錯，強制 wiring）
2. 刪除 `_default_order_adapter` 與 `hasattr(api, "inflight")`
3. `theman_engine_ports(..., api=...)` 或 call site 顯式傳入：
   - live：`ShioajiOrderAdapter(api)`
   - backtest / `make_host(MockBroker)`：`MockOrderAdapter(api)`
   - 單測 `MagicMock`：`MockOrderAdapter(api)` 或 test double

| **驗收** | grep trading-engine 無 `inflight`；`test_deal_state_machine` + `test_mock_broker` 全綠 |

---

### B5 — `strategy/base.py` 改為 re-export（消除 ~190 行重複）

| | |
| - | - |
| **問題** | `theman/src/strategy/base.py` 與 `trading_engine/core/strategy.py` 全文重複，Protocol 雙源易 drift |
| **來源** | CodeReview Issue 2 |
| **修法** | |

```python
"""Re-export Strategy contract from trading-engine (source of truth)."""
from trading_engine.core.strategy import *  # noqa: F403
__all__ = ["Strategy", "BaseStrategy", "StrategySideEffects"]
```

| **驗收** | `strategy/base.py` < 10 行；`from strategy.base import Strategy` 仍可用；155 tests OK |

---

### B6 — 文件與現況同步（「文件即真相」）

| | |
| - | - |
| **問題** | `AGENTS.md`、`TODO.md`、`WeeklyStatus.md`、`Architecture.md`、`BackTestingSpec.md` 仍寫「`order_executor` 直接建 `FuturesOrder`」為下一步；實際已在 `trading_engine/adapters/shioaji.py` |
| **來源** | CodeReview Issue 4 |
| **應寫明的現況** | |

- ✅ 下單建構：`trading_engine.adapters.shioaji.ShioajiOrderAdapter`（唯一 `import shioaji` 建單）
- ✅ 訂單事件：`core/order_events.py` 字串常數
- 🔜 窄縫：`session.sync_positions` 仍比對 `sj.Action.Buy`（可下一輪字串化）
- 🔜 版控：`trading-engine` sibling package + CI 策略

| **驗收** | 五份文件同一敘事；`WeeklyStatus` 最上方一節記錄 Phase 8 全量 extraction（非僅 Step 1） |

---

## P0（merge 前強烈建議，與 Blocker 可同 PR）

### P0-1 — 測試後綁 `host.api` 與 stale `order_adapter`

| | |
| - | - |
| **問題** | `test_mock_broker` 等 `make_host()` 後 `host.api = broker`；adapter 已在 ctor 綁定舊 api |
| **來源** | CodeReview Issue 9 |
| **修法** | B4 完成後：`BacktestEngine` 建構時直接 `api=MockBroker` + `order_adapter=MockOrderAdapter(broker)`，測試勿 post-bind；或 document + 加 regression test `place_order` after 正確 wiring |
| **驗收** | 新增或更新測試覆蓋 `place_order` → `MockBroker.inflight` 有單 |

---

### P0-2 — `RuntimeConfig` 旗標來源單一化

| | |
| - | - |
| **問題** | `ThemanRuntimeConfig` 覆寫 `tick_archive`/`kbars_archive`/`dump_order_events` 讀 theman `config` 模組；`trading_engine.RuntimeConfig` 亦讀 `os.environ` → 雙實作易 drift |
| **來源** | CodeReview Issue 5 |
| **修法** | trading-engine 基底不實作這三 property；僅 `ThemanRuntimeConfig`（或注入 `ArchiveFlagsProvider`）負責 yaml+env |
| **驗收** | 單測：`TICK_ARCHIVE=1` + yaml 預設下 `default_runtime_config().tick_archive is True` |

---

## P1（merge 後第一個 follow-up PR，不擋 UAT 開跑）

| ID | 項目 | 說明 | 驗收 |
| -- | ---- | ---- | ---- |
| P1-1 | 版控 / packaging | `pip install -e trading-engine`；`run_tests.py` 移除 `sys.path` hack 或僅作 dev fallback | 新環境只靠 pip 可測 |
| P1-2 | import 風格統一 | theman 程式碼統一走 `core.*` / `runtime.*` re-export，或統一 `trading_engine.*`；消除同檔混用（如 `params.py`） | grep 無同檔 `core`+`trading_engine` 混 import |
| P1-3 | `ThemanTrendRefresh` 注入 calendar | 勿在 integration 內 `TaifexMarketCalendar()`；由 `theman_engine_ports(calendar=...)` 傳入 | Issue 6 |
| P1-4 | Logger 名稱參數化 | `setup_async_logging(logger_name="trading_engine")`；theman 覆寫 `"theman"` | Issue 8 |
| P1-5 | re-export 模板 + 表 | `Architecture.md` 增 re-export 對照表；各 shim 統一 `__all__` + 註解「edit trading-engine, not here」 | Issue 7 |
| P1-6 | `theman_engine_ports` 型別化 | `TypedDict` / `EngineWiring` dataclass 回傳 ports + `obs` + `default_strategy()` | Issue 10 |
| P1-7 | `ThemanTrendRefresh` 禁 `datetime.now()` fallback | 回測用 tick `exchange_dt` 或明確 raise | Cursor P1 |
| P1-8 | 勿 commit | `Shioaji.code-workspace` → `.gitignore` 或刪除 | — |
| P1-9 | determinism 手動驗收 | 同一 `--code --dates` 重構前後 `SIGNAL_AUDIT`/`FILL_AUDIT`/`DAILY_SUMMARY` 一致 | BackTestingSpec |

---

## P2（Step 2 / 長期）

| 項目 | 說明 |
| ---- | ---- |
| `session.sync_positions` Action 字串化 | 與 `order_events` 同一詞彙表 |
| `Settings` 單一來源 | 僅 `trading_engine.settings`；theman `config.py` 只 load YAML |
| trading-engine 自有測試套件 | kernel 最小集獨立於 theman 155 |
| NDJSON 事件層 | UAT 第一段乾淨後（原架構計畫） |

---

## 建議實作順序（單 PR 或 2 PR）

```
PR-1 (merge gate)
  B1 版控/CI
  B2 logging
  B3 obs wiring
  B4 order_adapter 外移
  B5 strategy/base re-export
  B6 文件
  P0-1 測試 wiring（與 B4 一併）
  → run_tests.py 155 綠

PR-2 (UAT 前 polish)
  P0-2 RuntimeConfig 旗標
  P1-* 依優先級
```

---

## 合併檢查清單（Agent / 人類共用）

- [x] 乾淨 clone + CI：`python run_tests.py` 158 OK（含 vendored `trading-engine/`）
- [x] `grep -r inflight trading-engine/` 無 adapter 選擇邏輯
- [x] `theman/src/strategy/base.py` 為 re-export
- [x] `LOG_FILE` 環境變數下 log 落檔（`tests/integrations/test_engine_wiring.py`）
- [x] `DAILY_SUMMARY` 含策略層 `near_miss`（`obs` 共用實例注入 strategy）
- [x] 五份核心文件與 `Phase8-MergeFixSpec.md` 狀態一致
- [x] 未 commit 密鑰 / `.env` / `Shioaji.code-workspace`（`.gitignore` 已加 `*.code-workspace`）
- [x] §2 護欄：未改 `simulation: false`、未跑 live

---

## Issue 對照表

| Fix ID | CodeReview Issue | Cursor Review |
| ------ | ---------------- | ------------- |
| B1 | — | CI / sibling package |
| B2 | — | LOG_FILE 回歸 |
| B3 | — | obs 斷線 |
| B4 | Issue 1 | `hasattr(inflight)` |
| B5 | Issue 2 | — |
| B6 | Issue 4 | — |
| P0-1 | Issue 9 | adapter + MagicMock |
| P0-2 | Issue 5 | — |
| P1-1 | Issue 3 | sys.path |
| P1-3 | Issue 6 | — |
| P1-4 | Issue 8 | — |
| P1-5 | Issue 7 | re-export |
| P1-6 | Issue 10 | engine_wiring |

---

*本 spec 為兩份 review 的去重合併；實作完成後將對應 checkbox 勾選並在 `WeeklyStatus.md` 記一節「Phase 8 merge fix landed」。*
