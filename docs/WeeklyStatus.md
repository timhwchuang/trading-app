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
| **AGENTS.md 生產指引** | ✅ 已擴充：AI 安全護欄、Production Gate、工程品質、已知限制、運維 runbook。 |
| **Cursor / Grok 強制合規** | ✅ `.cursor/rules/*.mdc`（`alwaysApply`）+ `.grok/settings.json`；見 `AGENTS.md` 開頭「AI 工具強制合規」。 |

---

### 2026-06-16（P6-1-CAL A-class 1-5 完成：時間切片 + harness + sweep trend + SOP + CQR persona review）

**目前進度**
- CAL-1~5 A-class（金鑰前、非 UAT blocker）**全部 code + test + docs 落地**（依建議順序，分支+commit+verbatim CQR Chief Quant reviewer persona 直接 review）。
  - CAL-1：交易所時間切片（`select_recent_trading_days_closes` + trading_day_for_daily_reset 取代 400 magic；regression guard 定量證明「未切片會錯 regime」；mock _KBars.ts 對稱；155 tests OK）。
  - CAL-2：校準 harness（`trend_calibration.py` 純函式 + synthetic scenario；veto_rate / delta_expectancy / forward PnL；math 修復 + 強制 SYNTHETIC GUARD 後 CQR Pass w/ notes）。
  - CAL-3：param_sweep 納入 `trend_*` 參數 + 報表自動附加 `veto_metrics`（harness 呼叫；舊 grid 零破壞；結構為真實 UAT 敏感度表預留）。
  - CAL-4/5：命名誠實化（effective scale ≈ tf × ema_period，非 macro bias；trend_ema_period 語意 + alias 說明）+ BackTestingSpec 新增完整「P6-1 Trend Filter Calibration Workflow」SOP（accumulate → harness → sweep → 決策表 + 驗收條件）。
- 所有變更**嚴格遵守安全邊界**：`trend_filter_enabled` 永遠 false、`min_strength=0.0`（最嚴格）、無 live/simulation 代碼、無真實 tick 依賴（A-class 全 synthetic）。
- CQR reviewer persona（對沖基金 Chief Quant，15y+，偏執 edge/overfit/hardcode）已在每個主要 commit 後直接 spawn 執行並 address High 項（guard 真正證明、math 正確、文件誠實、無新 magic）。
- 目前狀態表 / Changelog / BackTestingSpec 狀態表已同步（AGENTS 紀律）。

**人類必做（Follow-up）**
- [ ] 申請/取得永豐模擬 API（`TICK_ARCHIVE=1` + `KBARS_ARCHIVE=1` 強制），開始累積真實 tick/kbar + SIGNAL_AUDIT（含 trend_veto），準備 B-class CAL-6/7 真實 harness + sweep。
- [ ] 週報 / Pilot gate 討論時引用本週 CAL 1-5 基建 + CQR review 結論（「synthetic guard 已就位；真實 delta 穩定為正 + veto_rate 合理才是開旗標前提」）。
- [ ] merge 各 feat/p6-1-cal-* 後執行一次完整 `python run_tests.py` + 衛生 grep（確認無 stray 400 magic 作用中、flags 預設正確）。

**Pending / 待決策**
- B-class 真實數據到後，harness + sweep 產出具體 `trend_min_strength` 敏感度表 + delta 穩定性，再做人類 Go/No-Go（維持 0.0 還是調到校準值）。
- P2-1 部分成交完整支援（Mock + 單測已規劃，可併下一個 iteration；非 UAT blocker）。
- CI 骨架（PR 強制 `python run_tests.py`）已在 AGENTS + 本次文件強化；.github/workflows 可選後補。

**備註 / 開發日記**
- 本次完全依照 approved plan + user 要求「切分支下commit 完成後透過 reviewer persona 直接code review」（CQR 逐 branch 執行，output 成為紀錄）。
- 155 tests（較前增加 harness/sweep guard 案例）；全綠。
- 後續工作嚴禁跳過 B-class 直接開旗標（違反 TODO + AGENTS + CQR 共識）。
- 感謝 Chief Quant 的嚴格把關，讓 A-class 基建真正「可量測」而非裝飾。

---

### 2026-06-16（Chief Quant 深度 Code Review：P6-1 Level 2 Trend Filter commits A/B/C）

**目前進度**
- 針對 3573ef7 (A: ATR 標準化 min_strength)、1773fbc (B: 跨日污染切片 + resample 最新 bar 保證)、31881ca (C: EMA SMA seed + 邊界測試) 完成對沖基金量化研究員級審查（統計優勢、過擬合、硬編碼偏執視角）。 
- 工程衛生面：ATR 單位正規化、最新 bar 對齊、初始值 bias 移除、文件大幅澄清 min_strength=0 為「最嚴格」而非寬鬆 —— 均屬正面修補先前 review 回饋。
- **發現 1 個測試 bug**（A 引進的 test_compute_trend_atr_normalization 在 slope 模式數值預期錯誤，已修正，現在正確示範 0.2 vs 0.3 的 gate 行為）。
- 全測 146 項（含本次新增邊界 case）。
- 核心診斷：這三個 commit 是「讓 prototype filter 不要太容易在開盤/不同波動下靜默失效」的工程修正，**不是對統計優勢的驗證**。濾網的有效性仍仰賴真實 UAT tick 下的 conditional expectancy（vetoed candidates 的後續實現 P&L）。

**人類必做（Follow-up）**
- [ ] **申請 / 取得永豐模擬 API** 並以 `TICK_ARCHIVE=1` + `KBARS_ARCHIVE=1` 累積至少 5-10 個交易日的真實 1m tick + kbar（這是 Phase 6 校準的唯一合法數據源）。
- [ ] 在 UAT 數據累積後，執行/擴充 param_sweep + uat_report 分析：針對 trend_veto 的候選 pullback，計算「若未被 veto 的條件期望值」與「實際 veto 後的後續價格行為」之間的 delta expectancy。**沒有這個數字就不要把 trend_min_strength 從 0 調高或開啟旗標**。
- [ ] 把 engine.py 裡 `approx_bars_per_trading_day = 400` 這個 TXF 特定 magic number 替換成**基於 kbar 時間戳 + exchange_time 的 session-aware 切片**（「最近 1-2 個完整交易日」）。這是 Live hygiene 硬需求。
- [ ] Pilot 前再次確認：所有 trend_allows_entry 的決策在 SIGNAL_AUDIT 裡都有完整 trend_dir/strength/atr 紀錄，方便事後 regime 切分績效。

**Pending / 待決策**
- [ ] 是否值得把目前的「短窗 price displacement / slope」升級為真正統計意義的 regime strength（例如 normalized slope、R² filter、或獨立抓取更高時間框架的 15m kbars 做 anchored trend）？還是維持「輕量 intraday bias veto」定位即可？
- [ ] trend_min_strength 預設值在 config.yaml 仍為 0.0 —— 保持現狀（文件已極度警告）還是改成一個「明顯無效」的 sentinel（如 -1）強迫使用者顯式設定？
- [ ] Phase 6 其餘（P6-4 sizing、P6-5 追價）是否要等這波 trend filter 在真實數據上站穩腳步後才動？

**備註 / 開發日記**
- 作為 Chief Quant 的結論：**UAT 期間可以 merge 這些 commit（已含測試修正）**；它們改善了濾網在 boundary condition 下的可預測性。
- **嚴禁** 在沒有足夠真實 tick + 對 veto 候選的 forward P&L 量化前，就在 config 裡把 trend_filter_enabled 改 true 或調高 min_strength 去「試試看」。
- 這套「微觀動能 + pullback + 短窗 HTF veto」的整體 edge，仍然是待證偽的假說。P6-1 的價值最終要用「被它救下來的連續小虧」與「被它錯殺的主升段」兩邊的 realized expectancy 來衡量，而不是單看合成 ramp 測試通過。
- 下一位 Agent / 人類接手時，請直接從本節 + TODO.md 內部量化 review 區塊開始閱讀，不要只看 commit message。
- 相關文件已同步：TODO.md 已新增完整 review 摘要（含量化風險分級與必須行動）。

---

### 2026-06-16（Cursor + Grok 強制合規規則落地）

**目前進度**

- **Cursor**：`.cursor/rules/theman-safety-guardrails.mdc` + `theman-agents-compliance.mdc`（皆 `alwaysApply: true`）。
- **Grok**：`.grok/settings.json`（instructions 指向根目錄 `AGENTS.md` §2 優先）。
- `AGENTS.md` 開頭新增「AI 工具強制合規（Cursor + Grok）」與衝突解決順序。

**人類必做（Follow-up）**

- [ ] Cursor 開新 Agent 對話，確認 Project Rules 出現上述兩條
- [ ] Grok：`grok inspect` 確認 `AGENTS.md` 在 instruction chain 中

**Pending / 待決策**

- （無）

**備註 / 開發日記**

- §2 安全護欄為三處同步真相：`AGENTS.md`、`.cursor/rules/theman-safety-guardrails.mdc`、`.grok/settings.json` instructions；變更 §2 時三處一併更新。

---

### 2026-06-16（AGENTS.md 生產級指引擴充）

**目前進度**

- **`AGENTS.md` 大幅擴充**（208 → ~400 行）：§2 AI 安全護欄、§4 Production Readiness Gate（UAT vs Pilot/Live）、§7 工程品質、§8 已知限制（P2-1/qty>1、Phase 6）、§9 運維 runbook（熱路徑、風控、落盤容量、kill-switch）。
- 修正：`python` vs `python3`/venv、Strategy 契約補 `update_momentum_peak`、`TradingEngine(clock=)`、資料夾補 `live/` / `scripts/windows/`。
- `docs/README.md` 索引同步指向新章節。

**人類必做（Follow-up）**

- [ ] 申請永豐模擬 API（UAT blocker，不變）
- [ ] （可選）pin `shioaji` 版本到 `requirements.txt` + 記錄於本檔
- [ ] （可選）加 GitHub Actions：`python run_tests.py`

**Pending / 待決策**

- （無 — Cursor rules 已落地，見上方最新一節）

**備註 / 開發日記**

- 週次 3 Phase 7 merge 已完成（`main`）；下一位 Agent 以 `WeeklyStatus` **最上方最新一節**為準。

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
