# 文件職責地圖（四 repo）

> **原則**：每份文件只有一個「真相來源」。不重複貼同一段驗收清單。

## 職責分工

| 文件 | Repo | 讀者 | 職責 |
| ---- | ---- | ---- | ---- |
| **TODO.md** | trading-app | Agent / 開發者 | **路線圖**：狀態表 + **未完成**工作項 + gate 摘要。不含歷史 changelog、不含逐步驗收細節。 |
| **docs/WeeklyStatus.md** | trading-app | 人類 | **週報 / 交接日記**：進度、Follow-up、待決策。舊節為 archive，以**最上方**為準。 |
| **docs/UAT_CHECKLIST.md** | trading-app | UAT 操作者 | **App 層 UAT 執行清單**：Windows 環境、env、`TICK_ARCHIVE`、收盤壓縮、`python -m reporting`。 |
| **docs/UAT_CHECKLIST.md** | trading-engine | 整合者 | **Kernel UAT**：狀態機、重連、pending、flatten、audit 行（Phase B/C）。App 整合時**引用**此檔，不重寫。 |
| **docs/LIVE_SAFETY.md** | trading-engine | Pilot 前 | 實盤安全護欄（CA、`simulation: false` gate）。 |
| **docs/WindowsOps.md** | trading-app | 運維 | 排程、告警、NSSM、收盤維護。 |
| **docs/BeforePilot.md** | trading-app | 人類決策 | UAT → Pilot 觀測項、秒停損率、對帳紀律。 |
| **docs/UPGRADE_RUNBOOK.md** | trading-app | 發布者 | **四 repo 升級 SOP**（pin 矩陣、tag 順序、哪些文件要同步）。 |
| **docs/RELEASE_CHECKLIST.md** | 各 repo | 發布者 | Tag 前機械檢查（測試、版本、密鑰）。 |
| **SPEC.md** | 各 repo | 整合者 | 套件邊界、公開 API、依賴方向。 |
| **docs/SWEEP_SPEC.md** | trading-app | 研究 | 確定性 hash、`param_sweep`、`calibration_cli` 編排 |
| **docs/BackTestingSpec.md** | trading-app | stub | 索引 → sibling BACKTEST_* / CALIBRATION / SWEEP_SPEC |
| **docs/ARCHIVE/** | trading-app | archive | 歷史週報、monolith `BackTestingSpec`；**非現行真相** |

## 重疊釐清（常見混淆）

| 問題 | 答案 |
| ---- | ---- |
| UAT 要跑哪些 scenario？ | **Kernel** → `trading-engine/docs/UAT_CHECKLIST.md` Phase B/C；**App 部署** → `trading-app/docs/UAT_CHECKLIST.md`。 |
| 還有什麼沒做完？ | **只看** `TODO.md` 狀態表 + Open items。 |
| 本週人類要做什麼？ | `WeeklyStatus.md` 最新一節。 |
| Phase 0～2 當初怎麼驗的？ | 已落地；驗收證據類型見 `UAT_CHECKLIST` 附錄 + `AuditContract.md`。歷史實作細節見 git log。 |
| Code review 原文？ | 已自 repo 移除；見 GitHub commit / PR 歷史。 |

## Sibling 文件入口

| Repo | 關鍵文件 |
| ---- | -------- |
| [trading-engine](https://github.com/timhwchuang/trading-engine) | `SPEC.md`, `docs/BACKTEST_HOST_CONTRACT.md`, `docs/UAT_CHECKLIST.md`, `docs/LIVE_SAFETY.md` |
| [trading-backtest](https://github.com/timhwchuang/trading-backtest) | `SPEC.md`, `docs/BACKTEST_IMPLEMENTATION.md`, `docs/RELEASE_CHECKLIST.md` |
| [strategy-vwap-momentum](https://github.com/timhwchuang/strategy-vwap-momentum) | `SPEC.md`, `docs/CALIBRATION.md`, `CHANGELOG.md`（B 類待 UAT tick） |
| [trading-app](https://github.com/timhwchuang/trading-app) | 本檔、`TODO.md`, `docs/UAT_CHECKLIST.md` |