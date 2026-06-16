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