# trading-app — Roadmap

> **執行環境：Windows**。原則：**UAT 驗狀態機與對帳，不驗獲利**。  
> 文件職責見 [`docs/DOC_MAP.md`](docs/DOC_MAP.md)。歷史實作細節見 git log（monolith 時代內容已瘦身）。

## 目前狀態（2026-06-16）

| 階段 | 狀態 |
| ---- | ---- |
| Phase 0～2 狀態機 / 訊號 / 委託 | ✅ 已落地（kernel + plugin） |
| **Phase 3 UAT** | **可開跑** — 待永豐模擬 API 金鑰 → [`docs/UAT_CHECKLIST.md`](docs/UAT_CHECKLIST.md) |
| Phase 4 運維骨架 | ✅ P4-1～12 已落地；Pilot 前 Telegram / 斷網實機驗收 |
| Phase 5 Pilot | 待 UAT 全過 + CA；秒停損率為硬指標 → [`docs/BeforePilot.md`](docs/BeforePilot.md) |
| Phase 6 策略真實化 | 骨架 ✅（旗標預設關）；**B 類 tooling ✅**（待 UAT tick 跑 CAL-8）；P6-4/5 待做 |
| Phase 7 策略介面 | ✅ `trading-engine` Protocol + `strategy-vwap-momentum` plugin |
| Phase 8 三 repo | ✅ 已發布 v0.1.1；`trading_app_engine_ports()` 接線 |

> **UAT Ready ≠ Live Ready**。Phase 6 是 Live gate，不是 UAT gate。

**測試基線**：`python run_tests.py` — trading-app **79**；siblings 各自 `run_tests.py`（engine 73 / backtest 27 / strategy 31）。

---

## Open items（未完成）

### Blocker — 人類

- [ ] 申請永豐**模擬** API（行情 + 帳務 + 交易；UAT 不需 CA）
- [ ] 依 [`docs/UAT_CHECKLIST.md`](docs/UAT_CHECKLIST.md) 跑第一段模擬

### P2-1 多口 / 部分成交

- [ ] 完整 qty>1 倉位管理（防禦層已有；Pilot 暫假設 **qty=1**）
-  owner: `trading-engine`

### P6-1-CAL B 類（6～8）

- [x] `forward_pnl.py` tick replay + `calibration_cli` + `param_sweep(forward_policy=...)`
- [ ] **人類**：UAT tick ≥5 日 → `python -m reporting.calibration_cli ... --sweep` → CAL-8 Go/No-Go
- owner: `strategy-vwap-momentum` + `trading-app/sweep`

### P6-4 Position sizing

- [ ] 依賴 P2-1；`risk_pct` / `max_contracts` 上線前須人類 Go/No-Go

### P6-5 追價進場

- [ ] Live gate 後段；非 UAT blocker

### P4-13 Live 連線護欄（斷線 / 恢復 — Pilot 前）

> **決策（2026-06-17）**：恢復後須等指標窗口重新對齊才允許新進場；單日斷線過多應停玩並排查網路；有倉斷線必須告警。  
> 見 [`WeeklyStatus.md`](docs/WeeklyStatus.md) 2026-06-17 備註；實作後更新 `trading-engine/docs/LIVE_SAFETY.md` + UAT checklist。

- [x] **P4-13-A 恢復暖機（reconnect warmup）**：`_on_reconnected` / 重訂閱成功後設 `reconnect_warmup_until_ts`（預設 300s），暖機期間 `RiskGate` 擋 **entry**、仍允許 **exit** / force-flatten
- [x] **P4-13-B 單日斷線上限**：`api_connected=False` 事件計數（預設 **3 次/交易日**），達標 → `block_new_entry=True` 至日切換 + `AlertPort` **CRITICAL**
- [x] **P4-13-C 有倉斷線告警**：`_mark_disconnected` 時若 `position_qty>0` → `AlertPort` **CRITICAL**
- [x] **P4-13-D config**：`config.yaml` `operations` + engine `Settings`（`reconnect_warmup_sec`、`max_disconnects_per_day`、`alert_on_disconnect_with_position`、`atr_stale_multiplier`）
- [x] **P4-13-E 測試**：`trading-engine/tests/runtime/test_atr_stale_and_reconnect_guards.py` + strategy `test_evaluate_pure`
- [ ] **P4-13-F UAT**：[`UAT_CHECKLIST.md`](docs/UAT_CHECKLIST.md) 增「手動斷網 30–60s → 恢復 → 確認無意外 entry / 有倉有告警 / 三次斷線停玩」
- owner: `trading-engine`（護欄邏輯）+ `trading-app`（config、AlertPort、UAT 條目）
- gate: **Pilot 前**必過；UAT Phase C 可先行驗 B/C（現有 reconnect）+ 暖機/上限（實作後）

### Phase 8 後續（非 UAT blocker）

- [ ] NDJSON 事件 sink（第一段乾淨 UAT 後）
- [ ] `session.sync_positions` Action 字串化統一

---

## Gates（摘要）

| Gate | 條件 | 文件 |
| ---- | ---- | ---- |
| **Merge code** | `run_tests.py` 全綠 | 各 repo |
| **UAT** | 模擬 API + `simulation: true` + checklist Pass | `docs/UAT_CHECKLIST.md` + engine checklist |
| **Pilot** | UAT 連續零異常 + CA + 秒停損率達標 | `docs/BeforePilot.md` |
| **Live** | Phase 6 旗標經 tick 校準 + 人類簽核 | `trading-engine/LIVE_SAFETY.md` |

---

## 文件索引（勿重複維護）

| 需要… | 讀… |
| ----- | --- |
| 跑 UAT | `docs/UAT_CHECKLIST.md` |
| Kernel scenario | [trading-engine UAT_CHECKLIST](https://github.com/timhwchuang/trading-engine/blob/main/docs/UAT_CHECKLIST.md) |
| 週報 / 人類 follow-up | `docs/WeeklyStatus.md` |
| Windows 運維 | `docs/WindowsOps.md` |
| 架構邊界 | `docs/Architecture.md`, `SPEC.md` |
| 回測 / sweep 規格 | `docs/SWEEP_SPEC.md` + sibling `docs/BACKTEST_*` / `CALIBRATION.md` |
| AI 協作規範 | `AGENTS.md` |