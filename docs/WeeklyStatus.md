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
| **P0-11 UAT tick 落盤** | ✅ 已實作（`TICK_ARCHIVE=1`）。盤中非同步 `*.csv`；gzip 由跨日 rotate 或 `compress_tick_cache`（**預設排除當日**）→ `*.csv.gz`。 |
| **回測 K 線（ATR）** | ✅ `KBARS_ARCHIVE=1` → `kbar_archiver.py` 寫 `tick_cache/{code}_kbars_{date}.csv`（`refresh_atr` 後）；UAT 建議一併開啟。 |
| **Live 防護網** | ✅ P4-11 / P4-12 / P4-3 骨架已落地（單元測試）；Pilot 前手動斷網 / Telegram 實機驗收。 |
| **Phase 6 骨架** | ✅ P6-6 生存指標 + P6-1～3 旗標預設關；**UAT 回測校準 k 後才開**。 |
| **Phase 7 策略介面** | ✅ `Strategy` Protocol + 建構子注入；host=`TradingEngine`；預設 plugin=`VWAPMomentumStrategy`。 |
| **Phase 3 UAT** | **可開跑**（待永豐模擬 API）；見 [`UATReminder.md`](UATReminder.md)。驗狀態機，不驗獲利。 |
| **Pilot 門檻** | UAT 全過 + CA + `simulation: false`；**P2-7 秒停損率**為硬指標。 |

---

### 2026-06-16（週次 3 — Phase 7 Strategy Interface + CR 收尾）

**目前進度**

- **Phase 7** 策略介面誠實化：`strategy.base.Strategy` / `BaseStrategy`；`TradingEngine(strategy=...)` 與 `BacktestEngine(strategy=...)` 建構子注入。
- 移除 `VWAPMomentumStrategy = TradingEngine` host 別名；**engine 叫 engine、strategy 叫 strategy**。
- `BacktestEngine.host` 取代 `.strategy` 屬性（避免與注入的 decision plugin 混淆）。
- Protocol 涵蓋 host 實際依賴面（momentum、`reset`、`manage_exit`、audit builders、session flatten）；非 VWAP plugin 可 survive one tick。
- 文件同步：`BackTesting.md` / `BackTestingSpec.md` / `TODO.md`；CR nit（`make_host`、public audit API）已合入。
- `python run_tests.py` **139** 項全綠；分支 `fix/strategy-interface-honesty`（待 merge → `main`）。

**人類必做（Follow-up）**

- [ ] **merge** `fix/strategy-interface-honesty` → `main`（CR OK）
- [ ] **申請永豐模擬 API 金鑰**（行情/資料 + 帳務 + 交易）— 仍為 UAT 首要 blocker
- [ ] Windows UAT 機：`TICK_ARCHIVE=1`、選配 `KBARS_ARCHIVE=1`
- [ ] UAT 累積 tick 後：`param_sweep` / `uat_report` 校準 Phase 6 旗標

**Pending / 待決策**

- [ ] Phase 6 旗標何時開（須回測數據支撐）
- [ ] 第二套 example strategy（驗證 plugin 故事；Phase 7 Next）
- [ ] P6-4 / P6-5（Live 後段）

**備註 / 開發日記**

- 歷史 Code Review（`CodeReview#1`～`#3`、`CodeReview#BackTesting`）內 `man.py` 行號為重構前快照；現行對照見 [`BackTesting.md`](BackTesting.md) §2 與 [`AuditContract.md`](AuditContract.md)。
- 預設決策仍為 VWAP；新策略須實作完整 `Strategy` contract（或繼承 `BaseStrategy`）。

---

### 2026-06-15（週次 2 — Pre-UAT 工程批次 + review 收尾）

**目前進度**

- **P6-6** 生存指標 + 摩擦成本（`performance_metrics.py`、`uat_report` 生存指標、`param_sweep` 風險調整排序）。
- **P4-11 / P4-12** Live 防護網：`order_errors.py`、exit 退避重試、session watchdog；**P4-3** 告警改非同步 queue（不阻塞 callback）。
- **P4-0 / P4-3 / P4-4** Windows 運維：`docs/WindowsOps.md`、`scripts/windows/*.ps1`。
- **P6-1～P6-3** 策略骨架（旗標預設關）：趨勢濾網 `compute_trend`、ATR trailing / VWAP 停損。
- **kbars 落盤**：`KBARS_ARCHIVE=1` + `kbar_archiver.py`。
- `python run_tests.py` **133** 項全綠；分支 `feat/review-fixes` @ `1c3f677`。

**人類必做（Follow-up）**

- [ ] **申請永豐模擬 API 金鑰**（行情/資料 + 帳務 + 交易）
- [ ] **Windows UAT 機**：`TICK_ARCHIVE=1`、選配 `KBARS_ARCHIVE=1`、`LOG_FILE=C:\logs\theman-uat.log`
- [ ] API 到手後 **UAT Day 1**（見 [`UATReminder.md`](UATReminder.md)）
- [ ] 累積 2～4 週 tick 後：`uat_report.py` 看 **生存指標（net）** + `param_sweep` 校準 Phase 6 參數
- [ ] Pilot 前：Telegram 告警實機測試、手動斷網驗 P4-12

**Pending / 待決策**

- [ ] Phase 6 旗標何時開（須回測數據支撐，非 UAT gate）
- [ ] P6-4 風險口數 / P6-5 追價進場（Live 後段）
- [ ] 摩擦成本 `round_trip_friction_points` 以券商實際費率校準（Pilot 前）

**備註 / 開發日記**

- UAT 仍驗狀態機；P4-11/12、P6 皆 **不阻擋 UAT 開跑**。
- Review fix：MDD 權益曲線種子 0、跨日串接、determinism 三跑 hash 回歸已補。

---

### 2026-06-15（週次 1 — P0-11 完成，解除 UAT gate）

**目前進度**

- **P0-11** 已實作並通過 code review 收尾：`tick_archiver.py`、`compress_tick_cache.py`、`data_loader` `.csv.gz` 支援、`TICK_ARCHIVE=1` 整合；`python run_tests.py` **102** 項全綠。
- **Phase 3 UAT** 工程 blocker 已解除；仍待 **永豐模擬 API（0 權限）** 與 Windows UAT 機就緒。

**人類必做（Follow-up）**

- [ ] **申請永豐模擬 API 金鑰**（行情/資料 + 帳務 + 交易）
- [ ] **準備 Windows UAT 機**：venv、`SJ_API_KEY` / `SJ_SEC_KEY`、`LOG_FILE=C:\logs\theman-uat.log`、`TICK_ARCHIVE=1`
- [ ] API 到手後 **UAT Day 1**：`DUMP_ORDER_EVENTS=1` + 跑滿交易時段驗 tick 落盤與委託欄位
- [ ] 收盤後工作排程器：`python src\compress_tick_cache.py`（預設排除當日；不需 `--exclude-today`）

**Pending / 待決策**

- [ ] **kbars 日終落盤**（P0-11 選配）— ~~Phase 6 回測前再補~~ ✅ 已落地（`KBARS_ARCHIVE=1`）
- [x] P4-0 Windows 上線檢查清單、P4-3 告警、P4-4 進程守護 — 見 [`WindowsOps.md`](WindowsOps.md)

**備註 / 開發日記**

- Code review 兩項收尾已合入：① 高頻 tick 時每 2s interval flush（不只 queue 空才 flush）；② `compress_tick_cache` 預設跳過當日檔，避免 Linux 開發機誤壓進行中 CSV。
- shutdown **刻意不** gzip 當日 plain 檔（避免 `.gz` 與重啟後新 `.csv` 並存導致重放漏資料）；收盤靠排程器壓縮。
- UAT Day 1 另須確認 Shioaji tick 的 `close`（Decimal）、`bid_price`/`ask_price` 欄位與 P0-9 `RAW_ORDER_EVT` 並行驗證。

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
