# Micro TAIEX VWAP 策略：UAT 回測規格書（同構性 / 確定性 / 啟發式執行）

> 本文件已對照實際專案（`man.py:VWAPMomentumStrategy`、`observability.py`、
> `exchange_time.py`、`config.py`、`uat_report.py`）與 Shioaji `_core.pyi` 修訂。
> 目標：在 UAT 期間能用歷史 tick 重放回測本策略，產出與生產環境 **語意一致** 的
> KPI（進場轉換率、秒停損率、滑價、期望值），作為進 Pilot 前的相對調參工具。

---

## 0. 先講清楚：回測能驗證什麼、不能驗證什麼

| 回測「能」量化（相對可信） | 回測「不能」驗證（須留待 Pilot） |
|---|---|
| 動量→進場轉換率、near-miss 漏斗 | 真實 IOC 成交機率 / 部分成交 |
| 秒停損率、出場 reason 分布 | 真實網路延遲變異、報價跳空 |
| 理論滑價（基於假設模型） | 真實 order book 排隊位置 |
| 毛點數 PnL、by-reason 期望值 | 真實摩擦成本（稅 / 手續費 / 滑價） |

**結論**：回測勝率是「相對調參工具」，不是絕對損益真相。執行模型是
**啟發式（heuristic）**，非高仿真撮合。Pilot 的真實成交才是最終閘門。

---

## 1. 核心哲學：實盤 / 回測「同構性」與「確定性」

* **核心決策邏輯一字不改**：`VWAPMomentumStrategy` 的 `process_strategy` /
  `manage_exit` / `update_vwap` / `update_momentum` / `_handle_futures_deal`
  在實盤與回測共用同一份程式碼。回測只替換「外部依賴」，不替換決策。
* **外部依賴注入（已落地的縫）**：
  * `api`：建構子 `VWAPMomentumStrategy(api=...)` 已支援注入（實盤為 `sj.Shioaji`，
    回測為 `MockBroker`）。
  * `clock`：建構子 `VWAPMomentumStrategy(clock=...)` 已支援注入。實盤預設
    `time.time()`；回測傳入「tick 時間驅動的時鐘」，使 pending 超時、看門狗等
    背景判斷在回測中**確定性可重現**。
  * `_today()`：ATR 的「今天」優先取最後一筆 tick 的交易所日期，無 tick 時才退回
    系統日期 → 回測不偷看真實今天。
* **交易所時間驅動（P0-6）**：所有時段 / cooldown / 開盤量能階梯由 `tick.datetime`
  驅動（見 `exchange_time.py`，naive datetime 視為台北本地時間）。

---

## 2. 專案結構（現況，非重寫）

```
theman/
├── config.py            # 參數快照（yaml + 環境變數）
├── exchange_time.py     # 交易所時間 helper（純函式，實盤回測共用）
├── signal_audit.py      # SIGNAL_AUDIT dataclass
├── observability.py     # FILL_AUDIT / DAILY_SUMMARY / near-miss（實盤回測共用）
├── man.py               # 策略狀態機 + 實盤進入點（api/clock 可注入）
├── data_loader.py       # ★ Phase 0：歷史 tick 抓取 + 本地 CSV 快取
├── backtester.py        # ☐ Phase 2：單執行緒 tick 重放引擎（待實作）
└── uat_report.py        # 日終指標解析（實盤回測共用）
```

> 不採用 big-bang 改寫成 `strategy.py` / `interfaces.py`。利用已存在的 `api`/`clock`
> 注入縫即可達成同構回測，風險最低。

---

## 3. Shioaji 歷史資料能力與限制（券商面）

實作參考 `data_loader.py`。對照 `_core.pyi`：

* **`api.ticks(contract, date, query_type=AllDay|RangeTime|LastCount)`** 回傳 `Ticks`：
  `ts`(奈秒 epoch)、`close`、`volume`、`bid_price`/`bid_volume`、
  `ask_price`/`ask_volume`、`tick_type`。
* **限制**：
  * 只有「最佳一檔」買賣價，**無歷史 order book 深度、無排隊位置**。
  * 只能抓**過去日期**；受 `usage().limit_bytes` 流量配額限制。
  * 歷史 `Ticks` **無 `simtrade` 旗標**（試搓單過濾僅適用即時串流）。
* **策略**：一次性下載 → 本地 CSV 快取（`tick_cache/<code>_<date>.csv`）。回測一律
  讀快取，**不**每次打 API。`data_loader.download_and_cache` 抓取前後記錄
  `api.usage()`，剩餘 < 10% 告警。

### ⚠️ bid/ask 同構性紀律（重要）

線上只訂閱 `QuoteType.Tick` → `TickFOPv1`（**無 bid/ask**）；策略決策只用
`tick.close`，下單 limit = `ref_price ± IOC_SLIPPAGE_POINTS`。因此：

* **撮合基準必須與線上一致 = 成交價（close）**，不可用 `ask + slippage` 對撞，
  否則模擬了一條生產環境看不到的執行路徑。
* `bid_price` / `ask_price` 僅作為**選配的真實性參考**（例如估計 spread 成本），
  且明確標註「不屬於確定性核心」。

---

## 4. `ReplayTick` 與 `TickFOPv1` 同構

`data_loader.ReplayTick` 提供策略 `_parse_tick` 會用到的屬性：

| 屬性 | 型別 | 說明 |
|---|---|---|
| `datetime` | `datetime`（台北 naive） | 由奈秒 ts 轉換，與線上 `tick.datetime` 同構 |
| `close` | `str` | `_parse_tick` 以 `float()` 轉換（線上亦為 str） |
| `volume` | `int` | 當筆成交量 |
| `tick_type` | `int` | **餵原始值**；`tick_type==0` 時由策略內 `_parse_tick` 推斷內外盤，與線上一致 |
| `bid_price`/`ask_price` | `float` | 選配，撮合核心不依賴 |

---

## 5. 回測引擎 `backtester.py`（Phase 2，待實作）

單執行緒、確定性。主迴圈：

```
for tick in data_loader.iter_replay_ticks(code, dates):
    clock.set(tick.datetime.timestamp())   # 推進虛擬時鐘
    strategy.on_tick(tick)                  # 同一份決策邏輯
    mock_broker.process_matching_queue(tick, strategy)  # 撮合 in-flight 委託
    strategy._check_pending_timeout()       # 同一份超時邏輯，由虛擬時鐘驅動
```

* **時鐘**：注入 `clock`（可變的 callable，回測中回傳當前 tick epoch 秒）。策略內
  所有 `self._clock()` 因此被 tick 時間驅動，無 `time.time()` 洩漏。
* **超時邏輯共用**：呼叫策略既有的 `_check_pending_timeout`，**不**在回測重寫一份。
* **成交回報走同一條路**：MockBroker 撮合後，組出與 Shioaji 同構的 deal dict，餵回
  `strategy.handle_order_event(OrderState.FuturesDeal, msg)` →
  既有 `_handle_futures_deal` → 既有 `_apply_deal_fill`。FILL_AUDIT / DAILY_SUMMARY
  因此自動產生，無需在回測另寫。

### 5.1 啟發式撮合模型（MockBroker）

收到 IOC 委託後，**不**即時成交，推入 in-flight 隊列：

1. **延遲**：固定模擬延遲（預設 15ms，可調）。`tick.datetime >= order_time + 延遲`
   才抵達市場邊界。
2. **IOC 一次性**：抵達後僅與當下 tick 撮合一次；不滿足即 `intent_cancelled`
   （對齊 P2-5 開盤漏單保護）。
3. **撮合基準 = close（與線上同構）**：
   * Buy 可成交條件：`tick.close <= limit_price`，成交價 = `min(close, limit) + 滑價`。
   * Sell 可成交條件：`tick.close >= limit_price`，成交價 = `max(close, limit) − 滑價`。
4. **滑價懲罰（可調旋鈕，標註為假設）**：
   * 常態：0.5 點。
   * 爆量（`tick.volume > momentum_vol_1s` 等門檻）：2.5 點。
   * 收盤強平（`intent==exit` 且 13:44 階段）：8.0 點（對齊 `flatten_slippage_points`）。

> 滑價數值是**假設**，UAT 期間應用 Pilot 真實 FILL_AUDIT 的 `slippage_pts`
> 反過來校準這些常數。

---

## 6. 數據閉環與驗證

* **uat_report 無縫相容**：回測輸出至 log 檔後，直接 `python uat_report.py <log>`，
  其「動量→進場轉換率」、「秒停損率(<5s)」、滑價、期望值等指標語意必須與生產環境
  **完全相同**（因為走同一份 `observability` 與同樣的 FILL_AUDIT/SIGNAL_AUDIT 行）。
* **確定性閘門（Determinism Gate）**：
  * 無 `time.time()` / `datetime.now()` 洩漏（已透過 `clock` 注入與 `_today()` 消除）。
  * 同一組歷史 tick 連跑 3 次，對 **四捨五入後** 的 `SIGNAL_AUDIT` + `FILL_AUDIT` 行串接做
    SHA-256，必須一致。
  * ⚠️ 跨平台（Windows 生產 vs 開發機）浮點不保證逐位元一致 → **hash 的是 audit 內
    已 round 的欄位**，不可 hash 原始 float。

---

## 7. AI-driven 調參迴圈（進 Pilot 前）

已具備的基礎：`DAILY_SUMMARY` 內含 `params` 參數快照 + 當日 KPI =
乾淨的 State → Action → Reward。

1. **參數掃描**：對 `config` 旋鈕（`entry_band_points`、`exit_grace_*`、
   `vwap_stop_points`、`exhaustion_vol`、`fixed_tp_points`、`trail_points` …）產生候選組合。
2. **每組跑回測** → 收 `DAILY_SUMMARY` JSON。
3. **餵 AI / 優化器**：以 `uat_report.py --json` 的 `tuning_hints` + 多日趨勢為輸入。
4. **walk-forward 防過擬合**：train 日 / validate 日分離；任何 AI 建議的參數，
   必須先過 **out-of-sample 回測**，再進 **UAT 模擬**，最後才 Pilot。
5. **護欄**：固定 1 口；參數變更須留存「哪組 config 對應哪份 KPI」的稽核連結
   （`DAILY_SUMMARY.params` 已內建此能力）。

---

## 8. 實作進度

* [x] **Phase 0**：`data_loader.py`（歷史 tick 抓取 + CSV 快取 + 配額告警）。
* [x] **Phase 1**：注入縫 —— `clock`（消除 `time.time()` 洩漏）、`_today()`
  （消除 `date.today()` 洩漏）。
* [ ] **Phase 2**：`backtester.py` 重放引擎（虛擬時鐘 + 同構 deal 回報）。
* [ ] **Phase 3**：`MockBroker` 啟發式撮合（close 基準 + 延遲 + 滑價旋鈕）。
* [ ] **Phase 4**：確定性閘門（3 次 SHA-256 一致）+ uat_report 語意比對。
* [ ] **Phase 5**：AI 調參迴圈（參數掃描 + walk-forward）。
