# 回測實作規格書（Phase 2-5）— 給實作模型的逐步指令

> 本文件是 `BackTesting.md` 的「可執行版」。目的：讓**任何模型（含較便宜的模型）**
> 能照本規格實作，**不需自行做架構決策**。每個 Phase 都有：要建立的檔案、精確函式
> 簽名、輸入/輸出、邊界情況、以及「驗收條件 + 具體測試案例與預期數值」。
>
> 黃金鐵律（違反即視為實作失敗）：
> 1. **絕對不可修改** `man.py` 的決策邏輯（`process_strategy` / `manage_exit` /
>    `update_vwap` / `update_momentum` / `_handle_futures_deal` / `_handle_futures_order`
>    / `_apply_deal_fill` / `_stop_loss_hit` / `_in_exit_grace_period`）。
> 2. 回測只能**注入** `api`（=MockBroker）與 `clock`（=虛擬時鐘），以及**新增**檔案。
> 3. 不可引入 `pandas` / `numpy`，只用 Python 標準庫。
> 4. 不可使用 `time.time()` / `datetime.now()` / `date.today()`。時間一律來自 `tick.datetime`。
> 5. 每個 Phase 完成後，`python -m unittest discover -p "test_*.py"` 必須全綠。

---

## 既有可用介面（實作前必讀，不要重寫這些）

`man.py:VWAPMomentumStrategy` 已具備：

* 建構子：`VWAPMomentumStrategy(api=None, clock=None)`。
* `on_tick(tick)`：`tick` 只需具備 `.datetime`(datetime, 台北 naive)、`.close`(str)、
  `.volume`(int)、`.tick_type`(int)。`data_loader.ReplayTick` 已符合。
* `place_order(signal)`：內部建 `sj.FuturesOrder(..., account=self.api.futopt_account)`，
  呼叫 `self.api.place_order(contract, order, timeout=0)`，期待回傳物件有 `.order.id`。
  **已驗證 `account=None` 可正常建構。**
* 成交回報入口：`handle_order_event(stat, msg)`：
  * `stat == OrderState.FuturesDeal`：`msg` 需含 `price`(可 float)、`quantity`(int)、
    `action`("Buy"/"Sell")、`trade_id`(str)。
  * `stat == OrderState.FuturesOrder`（取消用）：`msg` 需含
    `operation={"op_code":"00","op_type":"Cancel"}`、
    `status={"status":"Cancelled","deal_quantity":0}`、`trade_id`。
* `_check_pending_timeout()`：用 `self._clock()` 判斷超時，超時且補查無果會重置 pending。
* pending 欄位（回測會讀）：`pending_order_id`、`pending_intent`、`pending_signal_price`、
  `pending_limit_price`、`pending_ioc_slippage`、`pending_exchange_ts`、`pending_qty`、
  `is_pending`、`pending_trade`。
* ATR：`on_tick` 每 `ATR_REFRESH_SEC` 秒觸發 `refresh_atr()` →
  `self.api.kbars(contract, start, end)`，期待回傳物件有 `.High`/`.Low`/`.Close`(list)。

`data_loader.py` 已具備：`ReplayTick`、`iter_replay_ticks(code, dates, cache_dir=)`、
`download_and_cache(...)`、`date_range(start, end)`。

---

## Phase 2：重放引擎 `backtester.py`

### 2.1 建立 `VirtualClock`

```python
class VirtualClock:
    def __init__(self) -> None:
        self._now = 0.0
    def set(self, epoch_sec: float) -> None: self._now = epoch_sec
    def __call__(self) -> float: return self._now
```

### 2.2 建立 `BacktestEngine`

```python
class BacktestEngine:
    def __init__(self, code: str, dates: list[datetime.date], cache_dir=...):
        self.clock = VirtualClock()
        self.broker = MockBroker(clock=self.clock)        # Phase 3
        self.strategy = VWAPMomentumStrategy(api=self.broker, clock=self.clock)
        self.strategy.contract = self.broker.resolve_contract(code)
        self.code, self.dates, self.cache_dir = code, dates, cache_dir

    def run(self) -> None:
        for tick in iter_replay_ticks(self.code, self.dates, cache_dir=self.cache_dir):
            self.clock.set(tick.datetime.timestamp())   # 1. 推進虛擬時鐘
            self.broker.current_dt = tick.datetime        # 供 kbars 時間過濾
            self.strategy.on_tick(tick)                   # 2. 同一份決策邏輯
            self.broker.process_matching_queue(tick, self.strategy)  # 3. 撮合
            self.strategy._check_pending_timeout()        # 4. 超時（虛擬時鐘驅動）
        # 收盤：輸出當日 DAILY_SUMMARY
        if self.strategy._last_tick_exchange_dt is not None:
            self.strategy._emit_daily_summary(
                self.strategy._last_tick_exchange_dt.date()
            )
```

### 2.3 邊界情況（必須處理）

* 若某日快取缺檔，`iter_replay_ticks` 已自動略過並 warning，引擎不需特別處理。
* 跨日：`iter_replay_ticks` 連續輸出，`on_tick` 內 `_maybe_reset_daily_state` 會自動
  觸發跨日重置與**前一日 DAILY_SUMMARY 輸出**（既有行為，不要重做）。
* 引擎結束時，最後一日的 DAILY_SUMMARY 由 `run()` 末端補發（見 2.2）。

### 2.4 驗收條件（Phase 2）
* `test_backtester.py::test_engine_runs_empty`：無快取時 `run()` 不丟例外。
* `test_backtester.py::test_clock_advances`：餵 2 筆人工 tick，`clock()` 等於最後一筆
  `tick.datetime.timestamp()`。

---

## Phase 3：啟發式撮合 `MockBroker`

### 3.1 必須實作的 `api` 介面（`man.py` 在回測會用到的最小集合）

| 成員                                      | 簽名 / 回傳                                        | 說明                                    |
| ----------------------------------------- | -------------------------------------------------- | --------------------------------------- |
| `futopt_account`                          | 屬性 = `None`                                      | 讓 `sj.FuturesOrder(account=None)` 成立 |
| `place_order(contract, order, timeout=0)` | 回傳 `_Trade`，含 `.order.id`(str)                 | 推入 in-flight 隊列                     |
| `kbars(contract, start, end)`             | 回傳 `_KBars`，含 `.High/.Low/.Close`(list[float]) | 由 kbars 快取過濾 `ts <= current_dt`    |
| `update_status(trade=...)`                | no-op                                              | 超時補查呼叫；回測直接 pass             |
| `order_deal_records()`                    | 回傳 `[]`                                          | 同上                                    |
| `usage()`                                 | 可省略（回測不需）                                 | —                                       |
| `resolve_contract(code)`                  | 回傳簡單物件含 `.code`                             | 供引擎設定 `strategy.contract`          |

> `_Trade` / `_KBars` 用 `dataclass` 或 `SimpleNamespace` 即可。`order.id` 用遞增整數轉 str。

### 3.2 `place_order` 行為

```python
def place_order(self, contract, order, timeout=0):
    self._seq += 1
    order_id = f"BT{self._seq}"
    self.inflight.append({
        "order_id": order_id,
        "action": "Buy" if order.action == sj.Action.Buy else "Sell",
        "limit_price": float(order.price),
        "quantity": int(order.quantity),
        "arrive_after": self.clock() + self.latency_ms / 1000.0,  # 虛擬延遲
    })
    return SimpleNamespace(order=SimpleNamespace(id=order_id))
```

> 注意：`man.py` 會在 `place_order` 回傳後，於 lock 內設 `pending_order_id = str(trade.order.id)`。
> 因此 MockBroker **不需**自行回填 order_id。

### 3.3 `process_matching_queue(tick, strategy)` 行為

對每筆 in-flight 委託（用 `list(self.inflight)` 迭代，邊走邊移除）：

1. **延遲閘門**：`if tick.datetime.timestamp() < ord["arrive_after"]: continue`（尚未抵達）。
2. 從隊列移除該單。
3. **計算滑價懲罰**（可調，預設值見下）：
   * 基本 `slippage = NORMAL_SLIP`（預設 0.5）。
   * 若 `tick.volume > BLOWOUT_VOL`（預設 = `config.MOMENTUM_VOL_1S`）→ `slippage = BLOWOUT_SLIP`（預設 2.5）。
   * 若該單 `intent == "exit"` 且 `tick.datetime` 在 13:44 之後 → `slippage = FLATTEN_SLIP`（預設 8.0）。
     （intent 從 `strategy.pending_intent` 取，或在 place_order 時一併記錄。）
4. **撮合基準 = 成交價 `close`（與線上同構）**：
   ```python
   close = float(tick.close); limit = ord["limit_price"]; is_buy = ord["action"] == "Buy"
   if is_buy:
       if close <= limit: fill = min(close, limit) + slippage
       else:              fill = None   # 不可成交
   else:
       if close >= limit: fill = max(close, limit) - slippage
       else:              fill = None
   ```
5. **未成交 → 取消（IOC）**：呼叫
   ```python
   strategy.handle_order_event(OrderState.FuturesOrder, {
       "operation": {"op_code": "00", "op_type": "Cancel"},
       "status": {"status": "Cancelled", "deal_quantity": 0},
       "trade_id": ord["order_id"],
   })
   ```
6. **成交 → 餵回 deal**：呼叫
   ```python
   strategy.handle_order_event(OrderState.FuturesDeal, {
       "price": fill,
       "quantity": ord["quantity"],
       "action": ord["action"],
       "trade_id": ord["order_id"],
   })
   ```

> 不要在 MockBroker 自行算 PnL / 寫 FILL_AUDIT。`_apply_deal_fill` 已會做。

### 3.4 `kbars` 防 look-ahead（重要）

回測的 `kbars(start, end)` **只能回傳 `ts <= self.current_dt` 的 bar**，否則 ATR 會偷看
未來。實作：
* `data_loader` 增加 `download_and_cache_kbars` / `load_kbars_csv`（仿 ticks 快取，
  欄位 `ts,Open,High,Low,Close,Volume`）。
* `MockBroker.kbars` 載入快取後，過濾 `bar_ts <= current_dt`，回傳含 `.High/.Low/.Close` 的
  `_KBars`。
* 若快取無 kbars（UAT 初期），允許 `kbars` 回傳空 → `_compute_atr` 回 0.0 → 策略因
  `current_atr < MIN_ATR_THRESHOLD` 不進場（安全退化）。

### 3.5 可調參數（放 `MockBroker.__init__`，預設值如下）
`latency_ms=15`、`NORMAL_SLIP=0.5`、`BLOWOUT_VOL=MOMENTUM_VOL_1S`、`BLOWOUT_SLIP=2.5`、
`FLATTEN_SLIP=8.0`。

### 3.6 驗收條件（Phase 3）— 具體測試案例與預期值

`test_mock_broker.py`：

1. `test_buy_fill_normal_slip`：limit=18003，餵 tick close=18000 vol=1，延遲後撮合 →
   產生 FuturesDeal，fill_price = `min(18000,18003)+0.5 = 18000.5`。
2. `test_buy_cancel_when_close_above_limit`：limit=18003，close=18010 →
   產生 FuturesOrder Cancel（`intent_cancelled`），不產生 deal。
3. `test_sell_fill`：sell limit=17997，close=18000 → `max(18000,17997)-0.5 = 17999.5`。
4. `test_blowout_slippage`：close 可成交且 `volume > MOMENTUM_VOL_1S` → 滑價用 2.5。
5. `test_latency_gate`：下單後同一 tick（未過 15ms）不成交；後續 tick 過延遲才成交。
6. `test_no_lookahead_kbars`：`current_dt` 設為某分鐘，`kbars` 回傳的最後一根 bar 的
   ts ≤ current_dt。

---

## Phase 4：確定性閘門 + uat_report 語意比對

### 4.1 建立 `determinism_check.py`

```python
def run_hash(code, dates, cache_dir) -> str:
    """跑一次回測，蒐集所有 SIGNAL_AUDIT + FILL_AUDIT 行（log 攔截），
    對其串接做 SHA-256。回傳 hexdigest。"""
```

實作要點：
* 用 `logging.Handler` 攔截 logger 輸出，只收 message 以 `"SIGNAL_AUDIT "` 或
  `"FILL_AUDIT "` 開頭的行（取 JSON 部分）。
* **hash 前不可包含時間戳前綴**（`%(asctime)s`），只 hash JSON 內容。
* JSON 內已是 round 過的欄位（`observability` 已 round），故跨平台穩定。

### 4.2 驗收條件（Phase 4）
1. `test_determinism.py::test_three_runs_same_hash`：同一組快取連跑 3 次，
   `run_hash` 三次結果**完全相同**。
2. `test_determinism.py::test_uat_report_parses_backtest_log`：把回測 log 寫檔，
   `uat_report.compute_metrics(lines)` 能解析出 `fill_count > 0` 且
   `momentum_to_entry_conversion` 不為 None（在有交易的測試資料下）。
3. 人工核對：回測 log 跑 `python uat_report.py <log>`，輸出的「秒停損率」「轉換率」
   欄位存在且數值合理（非 N/A，當測試資料有完整 round-trip）。

---

## Phase 5：AI-driven 參數掃描 `param_sweep.py`

### 5.1 規格

```python
def sweep(grid: dict[str, list], dates_train, dates_valid, code, cache_dir) -> list[dict]:
    """對 grid 的笛卡兒積，逐組：
      1. 以該組參數覆寫參數（⚠️ 見 6.6：必須 monkeypatch `man` 模組命名空間，
         不是 config！man.py 頂層已 from config import，patch config 無效）
      2. 跑 train 區間回測 → 收 DAILY_SUMMARY（train KPI）
      3. 跑 valid 區間回測 → 收 DAILY_SUMMARY（valid KPI，out-of-sample）
      4. 輸出 {params, train_kpi, valid_kpi} 一列
    回傳所有組合結果，依 valid 的綜合分數排序。"""
```

* **綜合分數**建議：`score = valid.daily_pnl_points - penalty * valid.quick_stop_loss_rate`
  （penalty 預設 50）。可調。
* **walk-forward 鐵律**：排序與選擇**只能用 valid（out-of-sample）KPI**，train 僅供參考。
* 輸出一份 `sweep_result.jsonl`，每行一組，供上游 AI / 人工挑選。

### 5.2 掃描範圍（建議起手式，grid）
`entry_band_points: [2.0, 3.0, 4.0]`、`vwap_stop_points: [3, 4, 6]`、
`exit_grace_ticks: [40, 60, 90]`、`exhaustion_vol: [15, 25]`。

### 5.3 驗收條件（Phase 5）
1. `test_param_sweep.py::test_sweep_small_grid`：2×2 grid，回傳 4 列，每列含
   `params/train_kpi/valid_kpi`，且排序用的是 valid。
2. `test_param_sweep.py::test_config_restored`：sweep 後 `config` 全域值還原（不污染）。

---

## Phase 6：Code Review 迭代修訂（P0/P1）

> 本章為 review 後追加的修訂事項，**優先於前述各 Phase 的對應段落**。
> 建議實作順序（P0 優先）：6.1 → 6.3 → 6.4 → 6.6 →（P1）6.2 → 6.8 → 6.5 → 6.7。
> P0：6.1 穿價、6.3 timeout 時序、6.4 試撮隔離、6.6 模組動態注入。
> P1：6.2 KPI 漂移、6.8 hash 正規化、6.5 ATR 熱身、6.7 bid/ask 滑價校準。
> 後續會再迭代細化，本章先鎖定問題與驗收。

### 6.1【P0】限價單穿價保護（修訂 3.3 步驟 4）

**問題**：現況 `fill = min(close, limit) + slippage`，當買單可成交（`close <= limit`）時
`min` 永遠取 `close`，於是 `fill = close + slippage`，**無 limit 上限保護**。配合
`FLATTEN_SLIP=8.0`，成交價會劣於 limit（例：close=18000、limit=18003、slip=8 → 18008），
這在 IOC Limit 真實市場**不可能發生**。

**修訂**：撮合價必須 clamp 回 limit：

```python
if is_buy:
    if close <= limit: fill = min(limit, close + slippage)
    else:              fill = None
else:
    if close >= limit: fill = max(limit, close - slippage)
    else:              fill = None
```

> 語意註記：clamp 至 limit 等同「假設於 limit 成交」，屬樂觀處理（真實穿價多為直接
> 不成交→cancel），但優於現況產生不合法的劣於 limit 成交價。

**驗收**：`test_mock_broker.py::test_fill_never_worse_than_limit`
* Buy：任何 `slippage` 下，`fill <= limit`。
* Sell：任何 `slippage` 下，`fill >= limit`。
* 具體：buy limit=18003、close=18000、slip=8 → `fill == 18003`（被 clamp，非 18008）。

### 6.2【P0】KPI 漂移防護（修訂 4.1 hash 範圍）

**問題**：determinism hash 僅涵蓋 `SIGNAL_AUDIT` + `FILL_AUDIT`。若未來修改
`_emit_daily_summary()` 使 KPI 計算邏輯改變，hash 不會發現。

**修訂**：`run_hash` 攔截範圍擴為 `SIGNAL_AUDIT` + `FILL_AUDIT` + `DAILY_SUMMARY`。

**前置條件（必須先滿足，否則確定性閘門會 flaky）**：
* 先審 `_emit_daily_summary()` 輸出，確認**每一個數值欄位都已 round**（沿用第 6 節
  「只 hash round 過欄位」鐵律），跨平台才不會逐位元裂開。
* 確認 DAILY_SUMMARY 不含 wall-clock、絕對路徑、或順序不穩的內容（`params` 快照於同
  config 連跑下穩定，可納入）。

**驗收**：
* `test_determinism.py::test_daily_summary_in_hash`：修改任一 DAILY_SUMMARY 欄位值後，
  `run_hash()` 結果**必須改變**。
* 既有 `test_three_runs_same_hash` 仍須全綠（同資料連跑 3 次一致）。

### 6.3【P0】Pending Timeout 時序修正（修訂 2.2 主迴圈順序）

**問題**：現況順序 `clock.set() → on_tick() → process_matching_queue() →
_check_pending_timeout()`。線上 `_timeout_loop()` 是**獨立背景執行緒每秒檢查一次**，與
tick 無關；故線上在「09:00:00 下單、09:00:10 才有下一筆 tick」的空窗中，timeout 早已
解除。現況回測卻讓 `on_tick` 看到一個**線上不會存在的 stale `is_pending`**，破壞同構性。

**修訂**：將 `_check_pending_timeout()` 移到 `on_tick()` 之前：

```python
self.clock.set(tick.datetime.timestamp())   # 1. 推進虛擬時鐘
self.broker.current_dt = tick.datetime
self.strategy._check_pending_timeout()        # 2. 先用新時鐘解除過期 pending
self.strategy.on_tick(tick)                    # 3. 決策（看到的是 fresh pending 狀態）
self.broker.process_matching_queue(tick, self.strategy)  # 4. 撮合
```

> 注意：因 `PENDING_TIMEOUT_SEC >> latency_ms`，timeout 先於撮合不會誤殺「本 tick 應成交」
> 的單；且拖數秒才成交的 IOC 本就不真實，先 timeout 更貼近線上。

**驗收**：`test_backtester.py::test_pending_timeout_before_tick_processing`
* 09:00:00 下單後，下一筆 tick 在 09:00:10（> `PENDING_TIMEOUT_SEC`）抵達時，
  進入 `on_tick` 前 `is_pending` 已為 False。

### 6.4【P0（原 P1，升級）】歷史試撮資料隔離

**問題**：歷史 `Ticks` 無 `simtrade` 旗標（見 BackTesting.md §3）。且 `on_tick`
（man.py:406）**無條件先 `update_vwap`/`update_momentum`（line 421-422）**，session 檢查
在更後面才發生 → 08:40-08:45 試撮 tick 會污染 VWAP/動量基準，造成虛假爆量/動量/進場。
KPI 必然失真，故升為 P0。

**修訂**：在 **feed 層**（`backtester` / `data_loader`）過濾非交易時段 tick，**不可改
man.py**（違反黃金鐵律）。此舉與線上同構——線上 `simtrade` 亦於訂閱層就濾除、不進
`on_tick`。過濾沿用 `exchange_time.is_trading_session(dt, SESSION_START, SESSION_END)`，
**禁止硬編 08:45**。

```python
# backtester.run() 迴圈內，clock.set 之後、on_tick 之前
if not is_trading_session(tick.datetime, SESSION_START, SESSION_END):
    continue
```

**驗收**：`test_backtester.py::test_premarket_ticks_are_filtered`
* 餵入 08:40、08:43 試撮 tick + 08:46 正式 tick；08:45 前的 tick 不得進入 `on_tick`
  （VWAP/動量不被其污染）。

### 6.5【P1】ATR 熱身資料（修訂 3.4 kbars 快取）

**問題**：空 kbars → ATR=0 → `current_atr < MIN_ATR_THRESHOLD` 不進場。開盤
08:45-09:15（最有價值區段）可能全失效，回測低估。

**修訂**：屬資料供給任務。`download_and_cache_kbars` 多預載「前一交易日 + 夜盤」最後
N 根 K 線（N ≥ ATR 週期），確保 08:45 第一筆 tick 即可算 ATR。預載 bar 的 `ts` 天然
< 當日 08:45，不破壞 no-look-ahead（3.4）。

**驗收**：`test_mock_broker.py::test_atr_available_on_first_tick`
* kbars 快取含前一日/夜盤 bar 時，08:45 首筆 tick 觸發 `refresh_atr` 後
  `current_atr > 0`。

### 6.6【P0（致命）】模組 Import 固化 → 動態注入（修訂 5.1）

**問題（實錘，非理論）**：`man.py` 頂層 `from config import (ENTRY_BAND_POINTS,
VWAP_STOP_POINTS, EXHAUSTION_VOL, EXIT_GRACE_TICKS, ...)`（man.py:31-74），且決策點
**直接讀 module global**，非 `config.X`、非 `self.X`：

```python
# man.py:843
near_vwap = abs(price - self.current_vwap) <= ENTRY_BAND_POINTS
exhausted = self.vol_1s <= EXHAUSTION_VOL
# man.py:914 / 917
vwap_hit = price <= self.current_vwap - VWAP_STOP_POINTS
```

`import` 當下 `man.ENTRY_BAND_POINTS` 已是獨立綁定。Phase 5 sweep 若 monkeypatch
`config.ENTRY_BAND_POINTS`，**完全無效**——`man` 早有自己的綁定。**規格 5.1 原寫
「patch config」是錯的。**

**修訂**：sweep 每組參數時，monkeypatch **`man` 模組命名空間**（line 843 在 call time
從 `man` 的 global 解析，故建構後再 patch 亦有效）：

```python
import man, config

_PATCH_TARGETS = (
    "ENTRY_BAND_POINTS", "VWAP_STOP_POINTS", "EXHAUSTION_VOL", "EXIT_GRACE_TICKS",
    # ... 其餘掃描旋鈕同步列入
)

def _apply_params(params: dict) -> dict:
    """patch man.* + config.*（兩者都改：DAILY_SUMMARY.params 取自 config 快照），
    回傳原值供還原。"""
    saved = {}
    for k, v in params.items():
        saved[k] = (getattr(man, k, None), getattr(config, k, None))
        setattr(man, k, v)       # ★ 決策邏輯真正讀的是這個
        setattr(config, k, v)    # 讓 DAILY_SUMMARY.params 快照同步反映
    return saved

def _restore_params(saved: dict) -> None:
    for k, (mv, cv) in saved.items():
        setattr(man, k, mv)
        setattr(config, k, cv)
```

> 注意：`config.settings` / `DAILY_SUMMARY.params` 若另取 `config.*`，需一併 patch
> `config.*` 以免 KPI 稽核連結對不上參數。以上兩者都 patch 即可。

**驗收**：
* `test_param_sweep.py::test_man_namespace_patched`：patch 後在 `process_strategy`
  路徑讀到的 `ENTRY_BAND_POINTS` 等於掃描值（非 import 時的舊值）。
* `test_param_sweep.py::test_config_restored`：sweep 後 `man.*` **與** `config.*`
  全域值皆還原（不污染）。

### 6.7【P1（部分採納）】Bid/Ask 真實度 — 僅作滑價校準，不得當撮合基準

**背景**：review 建議改用 `ask_price`（主動買）/`bid_price`（主動賣）撮合以消除
optimistic bias。**此提案不予採納為撮合基準**，理由：直接違反 BackTesting.md §3
「bid/ask 同構性紀律」——線上只訂閱 `QuoteType.Tick`（`TickFOPv1`，**無 bid/ask**），
策略只用 `close` 決策；撮合基準若改 ask/bid，會模擬一條**生產環境看不到的執行路徑**，
破壞同構核心與確定性閘門，且歷史僅「最佳一檔」無深度無排隊位置（false precision）。

**已有對策**：spread / 衝擊成本**已由滑價旋鈕**（`NORMAL_SLIP`/`BLOWOUT_SLIP`/
`FLATTEN_SLIP`）建模，標注為「假設值，由 Pilot 真實 `slippage_pts` 反向校準」。

**部分採納（選配、非確定性核心）**：允許**用 bid/ask 校準滑價假設**，例如以
half-spread 動態調整 `slippage`：

```python
# 選配；ord 撮合基準仍為 close。bid/ask 缺值時退回固定 slippage。
half_spread = None
if getattr(tick, "ask_price", None) and getattr(tick, "bid_price", None):
    if tick.ask_price > tick.bid_price:
        half_spread = (tick.ask_price - tick.bid_price) / 2.0
if half_spread is not None:
    slippage = max(slippage, half_spread)   # 校準，不取代 close 基準
```

**紀律**：
* 撮合基準**仍為 `close`**（修訂 3.3 + 6.1 的 clamp 不變）。
* bid/ask 校準路徑須以開關控制（預設關），且**排除於確定性 hash 輸入之外**，標注
  「非確定性核心」。

**驗收**：`test_mock_broker.py::test_spread_calibration_optional`
* 開關開、tick 有 bid/ask 且 spread > 2*NORMAL_SLIP → 實際 slippage 提升至 half-spread。
* 開關關（預設）→ 撮合結果與 6.1 完全一致（確定性不受影響）。

### 6.8【P1】DAILY_SUMMARY Hash 正規化（強化 6.2）

**背景**：6.2 將 DAILY_SUMMARY 納入確定性 hash。review 建議 `sort_keys=True` 防 key
順序漂移。事實核對：`observability.py` 兩處 `json.dumps`（line 61、420）**均無
`sort_keys`**；惟 CPython 3.7+ 對 dataclass `asdict` 與 dict 的順序本就穩定且跨平台
一致，故「偶發碎裂」風險被高估。但作為**防未來重構迴歸**的零成本保險，採納。

**修訂（施作位置擇一，建議 A）**：
* **A（建議）**：在 `determinism_check.py` 攔截時**正規化後才 hash**——逐行 parse 回
  物件再 `json.dumps(obj, sort_keys=True)`。優點：hash 對 key 順序免疫，且**不更動生產
  log bytes**。
  ```python
  obj = json.loads(json_part)
  canonical = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
  hasher.update(canonical.encode("utf-8"))
  ```
* **B（選配）**：若要生產 log 本身即 canonical，則在 `observability.py` line 61、420
  的 `json.dumps` 加 `sort_keys=True`（會改動 log bytes，uat_report 解析不受影響）。

**驗收**：`test_determinism.py::test_hash_robust_to_key_order`
* 將某行 audit 的 key 順序人工打亂後，正規化 hash **不變**（驗證 A 路徑生效）。

---

## 總驗收清單（Definition of Done）

* [ ] 每個 Phase 的 `test_*.py` 全部通過；`unittest discover` 全綠（含既有 69 項）。
* [ ] 回測 log 能直接被 `uat_report.py` 解析，指標語意與實盤一致。
* [ ] 同資料連跑 3 次 SHA-256 一致（確定性閘門）。
* [ ] `man.py` 決策邏輯零改動（`git diff man.py` 僅含注入縫，不含策略數學）。
* [ ] 無 `time.time()` / `datetime.now()` / `date.today()` 出現在回測路徑。
* [ ] 無 `pandas` / `numpy` 依賴。

---

## 給實作模型的執行順序

1. 先 Phase 3 的 `MockBroker`（含 `_Trade`/`_KBars`/`resolve_contract`），寫
   `test_mock_broker.py` 跑綠。
2. 再 Phase 2 的 `backtester.py`（接上 MockBroker），寫 `test_backtester.py`。
3. 用 `data_loader.download_and_cache` 抓 2-3 個交易日真資料（或自製合成快取）做煙霧測試。
4. Phase 4 確定性 + uat_report 比對。
5. Phase 5 參數掃描。

每完成一步，跑全測試，確認 `man.py` 無策略邏輯改動，再進下一步。
