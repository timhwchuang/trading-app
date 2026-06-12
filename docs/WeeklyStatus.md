# Weekly Status — 人機協作開發日記

> 類似 Jira Story / FT 的 **Weekly Status + Follow-up**：給**人類**看的進度、待辦、下一步。
> AI 可讀此檔接續工作；工程規格仍以 [`TODO.md`](../TODO.md) 為準。

**用法**：每週（或重大決策時）在下方新增一節，填四塊即可。

---

## 範本（複製用）

```markdown
### YYYY-MM-DD（週次 / 標題一句話）

**目前進度**
- 

**人類必做（Follow-up）**
- [ ] 

**Pending / 待決策**
- 

**備註 / 開發日記**
- 
```

---

## 長期提醒（跨週有效）

| 項目 | 說明 |
| ---- | ---- |
| **申請永豐 API** | 目前 **0 權限**。模擬 UAT 建議勾：**行情/資料** + **帳務** + **交易**（不必勾正式環境、UAT 不需 CA）。 |
| **UAT 累積 tick，取代大量下載歷史** | 決策：**不再**用 API 批量抓過往 tick。改在 **UAT 模擬盤中每日落盤 tick** → 累積成 `tick_cache/`，作為日後回測資料。優點：格式與實盤一致、零額外流量；缺點：回測樣本從 UAT 起跑日才開始累積。 |
| **P0-11 UAT tick 落盤** | **UAT hard gate**：盤中非同步寫 **`*.csv`**；**gzip 由 rotate（換日/shutdown）或工作排程器** `compress_tick_cache` 執行 → `*.csv.gz`；`TICK_ARCHIVE=1`。 |
| **回測 K 線（ATR）** | P0-11 選配：日終或 `refresh_atr` 後落地 kbars；開跑前確認 ATR 熱身（前日 bar）有覆蓋。 |
| **Phase 3 UAT** | **待 P0-11**；見 [`UATReminder.md`](UATReminder.md)。驗狀態機，不驗獲利。 |
| **Pilot 門檻** | UAT 全過 + CA + `simulation: false`；**P2-7 秒停損率**為硬指標。 |

---

### 2026-06-12（週次 0 — 啟動人機協作日記）

**目前進度**

- Phase 0～2、回測 Phase 2–7（`BackTestingSpec`）程式面已完成；`python run_tests.py` 93 項全綠。
- **Phase 3 UAT** 被 **P0-11（tick 落盤）** 擋住；另 **尚未申請永豐 API（0 權限）**。
- 專案已重構為 `config/`、`src/`、`tests/`、`docs/` 結構。

**人類必做（Follow-up）**

- [ ] **申請永豐模擬 API 金鑰**（行情/資料 + 帳務 + 交易；先不勾正式環境）
- [ ] **準備 Windows UAT 機**：venv、`SJ_API_KEY` / `SJ_SEC_KEY`、`LOG_FILE=C:\logs\theman-uat.log`、`config/config.yaml` → `simulation: true`
- [ ] API 到手後：**第一個交易日** 設 `DUMP_ORDER_EVENTS=1`，跑一筆模擬委託（P0-9 欄位驗證）
- [ ] 等 **P0-11** 實作完成後再開 UAT（`TICK_ARCHIVE=1`）

**Pending / 待決策**

- [x] **回測資料策略**：不批量下載歷史 tick；改 **UAT 每日保存** → 已納入 **P0-11**
- [ ] **P0-11 實作**（AI）：盤中 `*.csv` + rotate/排程器 gzip；`data_loader` 讀取相容 `.csv` / `.csv.gz`
- [ ] 是否同時日終保存 kbars（ATR 回測熱身）— 建議要，細節待實作時定
- [ ] P4-0 Windows 上線檢查清單、P4-3 告警、P4-4 進程守護 — Pilot 前再做即可

**備註 / 開發日記**

- 0 權限期間：只能跑單元測試與 mock 回測；**有意義的回測 tick 只能來自 API 或 UAT 累積**。
- 網路下載的 1 分 K / 日線**不能**直接餵現有回測主迴圈（引擎吃的是 tick）。
- UAT 累積 tick 的想像：每天收盤後多一檔 CSV，幾週後就有真實模擬環境的樣本，可跑 `param_sweep` / `uat_report` 對照；樣本偏「模擬流動性」，Pilot 後可再補實盤 tick（若未來允許）。

---

<!-- 下一週在此上方插入新節，最新週次放最上面 -->
