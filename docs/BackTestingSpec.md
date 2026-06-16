# 回測實作規格書（Phase 2–7）— Archive

> ⚠️ **Archive**：本檔為 monolith 時代規格。三 repo 拆分後，**新功能以 sibling `SPEC.md` 為準**：
> `trading-engine`、`trading-backtest`、`strategy-vwap-momentum`。  
> 執行清單見 [`DOC_MAP.md`](DOC_MAP.md)；UAT 見 [`UAT_CHECKLIST.md`](UAT_CHECKLIST.md)。

> 本文件是 `BackTesting.md` 的「可執行版」。目的：讓**任何模型（含較便宜的模型）**
> 能照本規格實作，**不需自行做架構決策**。每個 Phase 都有：要建立的檔案、精確函式
> 簽名、輸入/輸出、邊界情況、以及「驗收條件 + 具體測試案例與預期數值」。
>
> **2026-06-16 現況（v0.1.1）**：Phase 2–7 **均已落地**；決策邏輯在 `strategy-vwap-momentum`，
> 執行宿主為 `trading-engine.TradingEngine`；回測在 `trading-backtest`（app 薄層注入 ports）。
> 歷史段落中若出現 `man.py` / `backtester.py`，僅作重構前脈絡，以本文件「檔案對照表」為準。
>
> 黃金鐵律（違反即視為實作失敗）：
> 1. **決策邏輯**在 `src/strategy/`（`evaluate` / `manage_exit` 等）；**執行宿主**在
>    `src/runtime/`（`process_strategy`、pending、fills、session）。回測不重寫決策。
> 2. 回測只能**注入**外部依賴，允許的注入縫：
>    * `api`（=MockBroker）、`clock`（=VirtualClock）、`strategy=`（決策 plugin）
>    * `host._maybe_refresh_atr`（回測改 no-op；ATR 改由引擎同步刷新，見 7.1）
> 3. 不可引入 `pandas` / `numpy`，只用 Python 標準庫。
> 4. 不可使用 `time.time()` / `datetime.now()` / `date.today()`。時間一律來自 `tick.datetime`。
> 5. `python run_tests.py` 必須全綠（trading-app **69** 項；siblings 各自維護）。

---

## 既有可用介面（實作前必讀，不要重寫這些）

`runtime.TradingEngine` 已具備：

* 建構子：`TradingEngine(api: BrokerPort | None=None, clock=None, strategy=None)`。
  * `api`：券商縫，型別為 `core.ports.BrokerPort`（僅文件/型別用途，不強制）；回測注入 `MockBroker`，省略時 lazy 建 `shioaji.Shioaji`。
  * `strategy`：決策 plugin（`Strategy`）；省略時預設 `VWAPMomentumStrategy`。
  * Phase 8：`engine.py`/`session.py` 已無模組頂層 `import shioaji`（見 `docs/Architecture.md`）。
* `on_tick(tick)`：`tick` 只需具備 `.datetime`(datetime, 台北 naive)、`.close`(str)、
  `.volume`(int)、`.tick_type`(int)。`storage.tick_loader.ReplayTick` 已符合。
* `place_order(signal)`：經注入的 `order_adapter` 建單——live 為 `ShioajiOrderAdapter`（內部 `sj.FuturesOrder`），
  回測為 `MockOrderAdapter`（`SimpleNamespace` action 字串）。皆呼叫 `self.api.place_order(contract, order, timeout=0)`，
  期待回傳物件有 `.order.id`。**已驗證 `account=None` 可正常建構。**
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

`storage/tick_loader.py` 已具備：`ReplayTick`、`iter_replay_ticks(code, dates, cache_dir=)`、
`download_and_cache(...)`、`date_range(start, end)`；
`storage/kbar_loader.py`：`download_and_cache_kbars(...)`、`load_kbars_csv(...)`、
`iter_kbars_in_range(...)`。

---

## Phase 2：重放引擎 `backtest/engine.py`

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
        self.broker = MockBroker(clock=self.clock, cache_dir=cache_dir)
        self.host = TradingEngine(api=self.broker, clock=self.clock)
        self.host.contract = self.broker.resolve_contract(code)
        # 7.1：阻擋 on_tick 內的背景 thread ATR；改由 run() 同步刷新
        self.host._maybe_refresh_atr = _noop_maybe_refresh_atr
        self.code, self.dates, self.cache_dir = code, dates, cache_dir

    def run(self) -> None:
        for tick in iter_replay_ticks(self.code, self.dates, cache_dir=self.cache_dir):
            self.clock.set(tick.datetime.timestamp())      # 1. 推進虛擬時鐘
            self.broker.current_dt = tick.datetime         # 供 kbars 時間過濾
            self.broker.process_matching_queue(tick, self.host)  # 2. 撮合（先於 timeout）
            self.host._check_pending_timeout()       # 3. 超時（虛擬時鐘驅動）
            if is_trading_session(tick.datetime, SESSION_START, SESSION_END):
                _pre_tick_refresh_atr(self.host, int(tick.datetime.timestamp()))  # 4. 同步 ATR
                self.host.on_tick(tick)                # 5. 決策（同一份邏輯）
        if self.host._last_tick_exchange_dt is not None:
            self.host._emit_daily_summary(
                self.host._last_tick_exchange_dt.date()
            )
```

> **主迴圈語意（7.2 / 7.3 修訂後）**
> * **撮合先於 timeout**：冷清時段下一筆 tick 間隔 >8s 時，先嘗試 IOC 成交/取消，再判定
>   pending 超時，避免成交回報被 `_clear_pending` 後丟棄（見 `historical backtest review (git archive)` P2-1）。
> * **試撮隔離只擋 `on_tick`**：非交易時段 tick 仍跑撮合與 timeout（7.3），避免 in-flight
>   單卡在佇列；VWAP/動量不被 08:45 前 tick 污染（6.4）。
> * **timeout 先於 `on_tick`**：進決策前 `is_pending` 已反映超時解除（6.3）。
> * **ATR 在 `on_tick` 前同步算完**（7.1）：`refresh_atr()` 不可在 `on_tick` 持 lock 時呼叫
>   （會與 `refresh_atr` 內部 `with self.lock` 死鎖）。

### 2.3 邊界情況（必須處理）

* 若某日快取缺檔，`iter_replay_ticks` 已自動略過並 warning，引擎不需特別處理。
* 跨日：`iter_replay_ticks` 連續輸出，`on_tick` 內 `_maybe_reset_daily_state` 會自動
  觸發跨日重置與**前一日 DAILY_SUMMARY 輸出**（既有行為，不要重做）。
* 引擎結束時，最後一日的 DAILY_SUMMARY 由 `run()` 末端補發（見 2.2）。

### 2.4 驗收條件（Phase 2）
* `tests/backtest/test_backtester.py::test_engine_runs_empty`：無快取時 `run()` 不丟例外。
* `tests/backtest/test_backtester.py::test_clock_advances`：餵 2 筆人工 tick，`clock()` 等於最後一筆
  `tick.datetime.timestamp()`。
* `tests/backtest/test_backtester.py::test_pending_timeout_before_tick_processing`（6.3）：跨 tick 超時後，
  進入 `on_tick` 前 `is_pending` 已為 False。
* `tests/backtest/test_backtester.py::test_premarket_ticks_are_filtered`（6.4）：08:45 前 tick 不進 `on_tick`。
* `tests/backtest/test_backtester.py::test_premarket_tick_still_runs_matching`（7.3）：盤前 tick 仍撮合
  in-flight 單。

---

## Phase 3：啟發式撮合 `MockBroker`

### 3.1 必須實作的 `api` 介面（`TradingEngine` 在回測會用到的最小集合）

| 成員                                      | 簽名 / 回傳                                        | 說明                                    |
| ----------------------------------------- | -------------------------------------------------- | --------------------------------------- |
| `futopt_account`                          | 屬性 = `None`                                      | 讓 `sj.FuturesOrder(account=None)` 成立 |
| `place_order(contract, order, timeout=0)` | 回傳 `_Trade`，含 `.order.id`(str)                 | 推入 in-flight 隊列                     |
| `kbars(contract, start, end)`             | 回傳 `_KBars`，含 `.High/.Low/.Close`(list[float]) | 由 kbars 快取過濾 `ts <= current_dt`    |
| `update_status(trade=...)`                | no-op                                              | 超時補查呼叫；回測直接 pass             |
| `order_deal_records()`                    | 回傳 `[]`                                          | 同上                                    |
| `usage()`                                 | 回傳含 `bytes/limit_bytes/remaining_bytes` 的物件 | `refresh_atr` 末端會呼叫；建議 no-op 常數回傳（7.4） |
| `resolve_contract(code)`                  | 回傳簡單物件含 `.code`                             | 供引擎設定 `host.contract`          |

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

> 注意：`TradingEngine` 會在 `place_order` 回傳後，於 lock 內設 `pending_order_id = str(trade.order.id)`。
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
4. **撮合基準 = 成交價 `close`（與線上同構）**，且 **6.1 穿價 clamp**：
   ```python
   close = float(tick.close); limit = ord["limit_price"]; is_buy = ord["action"] == "Buy"
   if is_buy:
       if close <= limit: fill = min(limit, close + slippage)   # fill <= limit
       else:              fill = None
   else:
       if close >= limit: fill = max(limit, close - slippage)   # fill >= limit
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

回測的 `kbars(start, end)` **只能回傳已收盤且 `ts <= current_dt` 的 1 分 K**，否則 ATR 會偷看
未來。實作：
* `data_loader` 增加 `download_and_cache_kbars` / `load_kbars_csv`（仿 ticks 快取，
  欄位 `ts,Open,High,Low,Close,Volume`）。
* `MockBroker.kbars` 過濾：`bar_ts <= current_dt` **且** `bar_ts + 1min <= current_dt`
  （僅納入已收盤分鐘 K，7.9 / R-3），回傳含 `.High/.Low/.Close` 的 `_KBars`。
* 若快取無 kbars（UAT 初期），允許 `kbars` 回傳空 → `_compute_atr` 回 0.0 → 策略因
  `current_atr < MIN_ATR_THRESHOLD` 不進場（安全退化）。

### 3.5 可調參數（放 `MockBroker.__init__`，預設值如下）
`latency_ms=15`、`NORMAL_SLIP=0.5`、`BLOWOUT_VOL=MOMENTUM_VOL_1S`、`BLOWOUT_SLIP=2.5`、
`FLATTEN_SLIP=8.0`。

### 3.6 驗收條件（Phase 3）— 具體測試案例與預期值

`tests/backtest/test_mock_broker.py`：

1. `test_buy_fill_normal_slip`：limit=18003，餵 tick close=18000 vol=1，延遲後撮合 →
   產生 FuturesDeal，fill_price = `min(18000,18003)+0.5 = 18000.5`。
2. `test_buy_cancel_when_close_above_limit`：limit=18003，close=18010 →
   產生 FuturesOrder Cancel（`intent_cancelled`），不產生 deal。
3. `test_sell_fill`：sell limit=17997，close=18000 → `max(18000,17997)-0.5 = 17999.5`。
4. `test_blowout_slippage`：close 可成交且 `volume > MOMENTUM_VOL_1S` → 滑價用 2.5。
5. `test_latency_gate`：下單後同一 tick（未過 15ms）不成交；後續 tick 過延遲才成交。
6. `test_no_lookahead_kbars`：`current_dt` 設為某分鐘，`kbars` 回傳的最後一根 bar 的
   ts ≤ current_dt。
7. `test_fill_never_worse_than_limit`（6.1）：buy fill ≤ limit；FLATTEN_SLIP=8 時
   close=18000、limit=18003 → fill=18003（非 18008）。
8. `test_atr_available_on_first_tick`（6.5）：前日 kbars 快取存在時，08:45 首 tick 後
   `current_atr > 0`。
9. `test_spread_calibration_optional`（6.7）：`spread_calibration` 預設關；開啟時以
   half-spread 提升 slippage，撮合基準仍為 `close`。

---

## Phase 4：確定性閘門 + uat_report 語意比對

### 4.1 建立 `determinism_check.py`

```python
def run_hash(code, dates, cache_dir) -> str:
    """跑一次回測，蒐集 SIGNAL_AUDIT + FILL_AUDIT + DAILY_SUMMARY（6.2），
    正規化後串接 SHA-256。回傳 hexdigest。"""

def normalize_audit_for_hash(label: str, json_part: str) -> str:
    """json.loads → 剔除非確定性欄位（7.5）→ json.dumps(sort_keys=True)。"""
```

實作要點：
* 用 `logging.Handler` 攔截 `man` logger，收 `"SIGNAL_AUDIT "` / `"FILL_AUDIT "` /
  `"DAILY_SUMMARY "` 開頭的 message（取 JSON 部分）。
* **hash 前不可包含時間戳前綴**（`%(asctime)s`），只 hash JSON 內容。
* **6.8**：`sort_keys=True, separators=(",", ":")` 正規化（不更動生產 log bytes）。
* **7.5**：`DAILY_SUMMARY` hash 前剔除 `operational` 內掛鐘/遙測欄位：
  `lock_wait_max_ms`、`lock_wait_over_50ms`、`no_tick_resubscribe`、`atr_min`、`atr_max`
  （來自 `time.perf_counter()` 或背景緒污染；不屬決策語意 KPI）。
* JSON 內決策欄位已 round（`observability`），故跨平台穩定。

### 4.2 驗收條件（Phase 4）
1. `tests/sweep/test_determinism.py::test_three_runs_same_hash`：同資料連跑 3 次 hash 一致（無交易退化案例）。
2. `tests/sweep/test_determinism.py::test_three_runs_same_hash_with_kbars_and_fills`（7.6）：**有真 K 線
   且產生 FILL** 時，連跑 3 次 hash 仍一致——確定性閘門的真正驗收。
3. `tests/sweep/test_determinism.py::test_uat_report_parses_backtest_log`：`fill_count > 0` 且
   `momentum_to_entry_conversion` 不為 None。
4. `tests/sweep/test_determinism.py::test_daily_summary_in_hash`（6.2）：修改 DAILY_SUMMARY 決策欄位
   後 hash 必須改變。
5. `tests/sweep/test_determinism.py::test_hash_robust_to_key_order`（6.8）：key 順序打亂後 hash 不變。
6. `tests/sweep/test_determinism.py::test_hash_ignores_operational_wall_clock`（7.5）：僅
   `lock_wait_max_ms` 不同時 hash 不變。
7. 人工核對：回測 log 跑 `python src/uat_report.py <log>`，指標語意與實盤一致。

---

## Phase 5：AI-driven 參數掃描 `param_sweep.py`

### 5.1 規格

```python
def sweep(grid: dict[str, list], dates_train, dates_valid, code, cache_dir) -> list[dict]:
    """對 grid 的笛卡兒積，逐組：
      1. 以該組參數覆寫（⚠️ 見 6.6 / 7.7：必須 patch `man` + `config` + `observability`
         三個模組命名空間；只 patch config 對決策與 DAILY_SUMMARY.params 皆無效）
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
1. `tests/sweep/test_param_sweep.py::test_sweep_small_grid`：2×2 grid，回傳 4 列，每列含
   `params/train_kpi/valid_kpi`，且依 `valid_score` 排序。
2. `tests/sweep/test_param_sweep.py::test_config_restored`：sweep 後 `man.*`、`config.*`、
   `observability.*` 皆還原。
3. `tests/sweep/test_param_sweep.py::test_man_namespace_patched`（6.6）：`process_strategy` 讀到掃描值。
4. `tests/sweep/test_param_sweep.py::test_daily_summary_params_match_sweep`（7.7）：sweep 期間
   `DAILY_SUMMARY.params` 與掃描值一致。

### 5.4 KPI 聚合（7.8）
* `quick_stop_loss_rate` 用**加權**算法：`Σ quick_sl_count / Σ exit_count`（非各日簡單平均）。

---

## Phase 6：初版 Code Review 修訂（P0/P1）— 已實作

> 本章為 Phase 2–5 初版後的第一輪 review 修訂，**均已落地**。
> **7.x 章節**為第二輪 review（`historical backtest review (git archive)`）修訂，優先於 6.3/6.4 的初版敘述。
> 實作順序：6.1 → 6.3 → 6.4 → 6.6 → 6.2 → 6.8 → 6.5 → 6.7 → **Phase 7**。

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

**驗收**：`tests/backtest/test_mock_broker.py::test_fill_never_worse_than_limit`
* Buy：任何 `slippage` 下，`fill <= limit`。
* Sell：任何 `slippage` 下，`fill >= limit`。
* 具體：buy limit=18003、close=18000、slip=8 → `fill == 18003`（被 clamp，非 18008）。

### 6.2【P0】KPI 漂移防護（修訂 4.1 hash 範圍）

**問題**：determinism hash 僅涵蓋 `SIGNAL_AUDIT` + `FILL_AUDIT`。若未來修改
`_emit_daily_summary()` 使 KPI 計算邏輯改變，hash 不會發現。

**修訂**：`run_hash` 攔截範圍擴為 `SIGNAL_AUDIT` + `FILL_AUDIT` + `DAILY_SUMMARY`。

**前置條件（必須先滿足，否則確定性閘門會 flaky）**：
* 決策語意欄位已 round（`observability`）。
* `operational` 內掛鐘/遙測欄位**不納入 hash**（7.5）；生產 log 仍完整輸出，僅 hash
  正規化階段剔除。
* `params` 快照於 sweep 時須同步 patch `observability`（7.7），連跑下穩定。

**驗收**：
* `tests/sweep/test_determinism.py::test_daily_summary_in_hash`：修改任一 DAILY_SUMMARY 欄位值後，
  `run_hash()` 結果**必須改變**。
* 既有 `test_three_runs_same_hash` 仍須全綠（同資料連跑 3 次一致）。

### 6.3【P0】Pending Timeout 時序修正（修訂 2.2 主迴圈順序）

**問題**：原順序 `on_tick → 撮合 → timeout` 會讓 `on_tick` 看到線上不存在的 stale
`is_pending`（線上 `_timeout_loop` 獨立於 tick）。

**修訂（已實作，見 2.2 / 7.2）**：每 tick 順序為
`撮合 → timeout → (session) 同步 ATR → on_tick`。其中 **timeout 仍先於 `on_tick`**，
滿足「進決策前 pending 已刷新」；**撮合先於 timeout**（7.2）避免冷清間隔誤殺成交。

**驗收**：`tests/backtest/test_backtester.py::test_pending_timeout_before_tick_processing`
* 09:00:00 下單後，下一筆 tick 在 09:00:10（> `PENDING_TIMEOUT_SEC`）抵達時，
  進入 `on_tick` 前 `is_pending` 已為 False。

### 6.4【P0（原 P1，升級）】歷史試撮資料隔離

**問題**：歷史 `Ticks` 無 `simtrade` 旗標（見 BackTesting.md §3）。且 `on_tick`
（`runtime/engine.py` `on_tick`）**無條件先 `update_vwap`/`update_momentum`**，session 檢查
在更後面才發生 → 08:40-08:45 試撮 tick 會污染 VWAP/動量基準，造成虛假爆量/動量/進場。
KPI 必然失真，故升為 P0。

**修訂**：在 **feed 層**（`backtester` / `data_loader`）過濾非交易時段 tick，**不可改
`src/runtime/engine.py`**（違反黃金鐵律）。此舉與線上同構——線上 `simtrade` 亦於訂閱層就濾除、不進
`on_tick`。過濾沿用 `exchange_time.is_trading_session(dt, SESSION_START, SESSION_END)`，
**禁止硬編 08:45**。

```python
# backtester.run()：只跳過 on_tick，撮合/timeout 仍執行（7.3 修訂）
if is_trading_session(tick.datetime, SESSION_START, SESSION_END):
    _pre_tick_refresh_atr(self.host, ...)
    self.host.on_tick(tick)
```

**驗收**：`tests/backtest/test_backtester.py::test_premarket_ticks_are_filtered`
* 08:45 前的 tick 不得進入 `on_tick`（VWAP/動量不被污染）。
* `test_premarket_tick_still_runs_matching`（7.3）：盤前 tick 仍處理 in-flight 撮合。

### 6.5【P1】ATR 熱身資料（修訂 3.4 kbars 快取）

**問題**：空 kbars → ATR=0 → `current_atr < MIN_ATR_THRESHOLD` 不進場。開盤
08:45-09:15（最有價值區段）可能全失效，回測低估。

**修訂**：屬資料供給任務。`download_and_cache_kbars` 多預載「前一交易日 + 夜盤」最後
N 根 K 線（N ≥ ATR 週期），確保 08:45 第一筆 tick 即可算 ATR。預載 bar 的 `ts` 天然
< 當日 08:45，不破壞 no-look-ahead（3.4）。

**驗收**：`tests/backtest/test_mock_broker.py::test_atr_available_on_first_tick`
* kbars 快取含前一日/夜盤 bar 時，08:45 首筆 tick 觸發 `refresh_atr` 後
  `current_atr > 0`。

### 6.6【P0（致命）】模組 Import 固化 → 動態注入（修訂 5.1）

**問題（已解）**：早期版本決策邏輯直接讀 `man` 模組 global；現已改為
`StrategyParams.from_config()`（`src/strategy/params.py`），sweep 透過 patch
`config` + 還原機制影響新策略實例。

**驗收**：
* `test_config_restored`、`test_daily_summary_params_match_sweep`
* `test_sweep_params_affect_entry`

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

**驗收**：`tests/backtest/test_mock_broker.py::test_spread_calibration_optional`
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

**驗收**：`tests/sweep/test_determinism.py::test_hash_robust_to_key_order`
* 將某行 audit 的 key 順序人工打亂後，正規化 hash **不變**（驗證 A 路徑生效）。

---

## Phase 7：Code Review 落地修訂（`historical backtest review (git archive)`）

> Phase 2–6 初版實作後的 review 反饋，**已落地**。優先於初版 2.2 / 6.3 / 6.4 段落。

### 7.1【P0】同步 ATR 注入（修訂背景 thread 問題）

**問題**：`TradingEngine` 的 `_maybe_refresh_atr` 以 daemon thread 跑 `refresh_atr()`。
回測中 `MockBroker.current_dt` 隨主迴圈推進，背景緒讀取時可能 look-ahead 且非確定性。
若在 `on_tick` 持 lock 時同步呼叫 `refresh_atr()` 會死鎖（`refresh_atr` 內部再搶 lock）。

**修訂（不動決策邏輯）**：
1. `BacktestEngine.__init__`：`host._maybe_refresh_atr = _noop_maybe_refresh_atr`
2. `run()` 內、**`on_tick` 之前且無 lock 時**：`_pre_tick_refresh_atr(strategy, ts)`
   同步呼叫 `refresh_atr()`

**驗收**：`test_three_runs_same_hash_with_kbars_and_fills`——真 K 線、ATR≥門檻、有 FILL，
連跑 3 次 hash 一致。

### 7.2【P2】撮合先於 timeout

冷清 tick 間隔 > `PENDING_TIMEOUT_SEC` 時，先 `process_matching_queue` 再
`_check_pending_timeout`，避免成交回報因 pending 已清而被忽略。

> **已知偏差**：timeout 路徑不計 `intent_cancelled`（與線上 `FuturesOrder` Cancel KPI
> 略有差）；冷清時段成交率可能略高估。見 `historical backtest review (git archive)` P2-1。

### 7.3【P2】試撮隔離只擋決策

非 `SESSION` tick：**不** `continue` 整筆 tick；仍跑撮合與 timeout，僅跳過 `on_tick`。

### 7.4【P2】`MockBroker.usage()` no-op

避免 `refresh_atr` → `_log_api_usage` 洗版 warning。

### 7.5【P1】確定性 hash 剔除 operational 掛鐘欄位

`normalize_audit_for_hash` 對 `DAILY_SUMMARY` 剔除：
`lock_wait_max_ms`、`lock_wait_over_50ms`、`no_tick_resubscribe`、`atr_min`、`atr_max`。

### 7.6【P0】有交易路徑的確定性測試

`test_three_runs_same_hash`  alone 僅覆蓋「無交易退化」；必須另有 7.1 的真 K 線 + FILL 測試。

### 7.7【P1】sweep 三模組 patch

`_apply_params` / `_restore_params` 同步 patch `observability.*`（`build_config_snapshot` 來源）。

### 7.8【P2】加權 quick_stop_loss_rate

`param_sweep._aggregate_kpi`：`Σ count / Σ exit_count`，非各日 rate 簡單平均。

### 7.9【極低】僅納入已收盤 1 分 K（R-3）

`MockBroker.kbars` 排除當前未收完的分鐘棒（`bar.ts + timedelta(minutes=1) > current_dt`），
避免 within-minute look-ahead。`test_no_lookahead_kbars` 驗證 09:00:30 無 bar、09:01:00 含
09:00 棒。

### 7.10【低】P2-3 回歸測試修正（R-1）

`test_premarket_tick_still_runs_matching` 僅餵 **08:40** 盤前 tick（非 08:50），斷言 in-flight
單仍撮合且 `on_tick` 未被呼叫。

---

## 總驗收清單（Definition of Done）

* [x] 每個 Phase 的 `tests/**/test_*.py` 全部通過；`python run_tests.py` 全綠（trading-app **69** 項；歷史 monolith 基線曾為 155）。
* [x] 回測 log 能直接被 `uat_report.py` 解析，指標語意與實盤一致。
* [x] 同資料連跑 3 次 SHA-256 一致（含**有 K 線 + 有 FILL** 路徑，7.6）。
* [x] 決策邏輯在 `src/strategy/`（回測僅注入 `_maybe_refresh_atr` no-op）。
* [x] 回測路徑無 `time.time()` / `datetime.now()` / `date.today()`；hash 剔除 `perf_counter` 遙測欄位（7.5）。
* [x] 無 `pandas` / `numpy` 依賴。

---

## 實作狀態與檔案對照

| Phase | 狀態 | 主要檔案 |
|-------|------|----------|
| 2 | ✅ | `backtest/engine.py`, `tests/backtest/test_backtester.py` |
| 3 | ✅ | `backtest/mock_broker.py`, `tests/backtest/test_mock_broker.py`, `storage/kbar_loader.py` |
| 4 | ✅ | `sweep/determinism_check.py`, `tests/sweep/test_determinism.py` |
| 5 | ✅ | `sweep/param_sweep.py`, `tests/sweep/test_param_sweep.py` |
| 6 | ✅ | 穿價/timeout/試撮/hash/ATR熱身/bid-ask校準/StrategyParams sweep |
| 7 | ✅ | `strategy/base.py`, `strategy/vwap_momentum.py`, `tests/strategy/test_trend.py` (前身 test_strategy_phase6.py) |

### Phase 7 — Strategy interface（2026-06-16）

* **契約**：`strategy.base.Strategy` + `BaseStrategy`（momentum、`evaluate`、`reset`、
  `manage_exit`、audit builders、`session_force_flatten_signal`）。
* **注入**：`TradingEngine(strategy=...)`、`BacktestEngine(..., strategy=...)`。
* **命名**：執行宿主 = `TradingEngine` / `BacktestEngine.host`；**勿**使用已移除的
  `VWAPMomentumStrategy = TradingEngine` 別名。
* **測試**：`tests/strategy/test_trend.py`（原 test_strategy_phase6.py；包含 trend helpers + strategy interface injection）；
  `tests.test_helpers.make_host()` 建立 mock 宿主。
* **驗收**：自訂 `BaseStrategy` 子類注入後，`host.on_tick(tick)` 不拋 `AttributeError`。

**狀態**：Phase 7 已 merge 至 `main`（2026-06-16 前後）。P6-1 Level 2 + CAL A-class 見下方 SOP。

---

## P6-1 Trend Filter Calibration Workflow（A-class pre-UAT + B-class UAT）— CAL-5 SOP

> **本節為 P6-1-CAL-5 文件化**（accumulate → harness → sweep →  humans Go/No-Go）。  
> 所有 A-class（1-5）**僅 code + test + docs**；`trend_filter_enabled` 預設 `false`；**不開旗標、不跑 live、不碰 simulation**。真實校準數據來自 UAT 期間 `TICK_ARCHIVE=1` + `KBARS_ARCHIVE=1` 累積的 tick/kbar + SIGNAL_AUDIT（含 `reason=trend_veto`）。

### 流程（鐵律，違反即視為校準失敗）
1. **Accumulate（數據收集）**  
   - UAT 機：`TICK_ARCHIVE=1`（必）+ `KBARS_ARCHIVE=1`（強烈建議）。  
   - 連續數個交易日（目標 ≥5-10 日有 tick + 對應 kbars csv）。  
   - 每日收盤後自動落盤（P0-11）；無需手動下載歷史。

2. **Harness（條件期望值，P6-1-CAL-2）**  
   - 使用 `src/reporting/trend_calibration.compute_trend_veto_calibration(veto_audits, allowed_audits, get_forward_pnl=...)`。  
   - 輸入：從 uat_report / log parse 抽出的 SIGNAL_AUDIT（reason=="trend_veto" 為 veto 候選；其餘 entry 為 allowed）。  
   - forward PnL policy 必須**文件化**（e.g. 固定 30 根 1m bar、或至 session_force_flatten）。這是 hyperparam。  
   - 產出：`veto_rate`、`delta_expectancy`（allowed - veto_if_entered）、mean forward、counts。  
   - A-class 先用 synthetic scenario 驗 harness 正確性（`make_synthetic_veto_scenario` + 5 單測）；B-class 才餵真實 replay。

3. **Sweep（含趨勢參數，P6-1-CAL-3）**  
   - `sweep( grid_with_trend_min_strength + on/off , dates_train, dates_valid, ...)`。  
   - Grid 支援 snake_case（`trend_filter_enabled`）或 `TREND_*`；`apply_strategy_params` 正規化至 config 模組常數。  
   - `_run_backtest_summaries` 擷取 `SIGNAL_AUDIT`；當 params 含 trend 時附加 `veto_metrics`（`reason=trend_veto` vs allowed entry → harness）。  
   - **A 類**：`veto_rate` 可來自 backtest capture；`delta_expectancy` 須 B 類 `get_forward_pnl`（tick replay）才有決策價值。  
   - 排序仍用 valid survival KPI（net expectancy + MDD penalty）；veto 指標為決策輔助欄位。  
   - 目標：產生 `trend_min_strength` 敏感度表（0.0 / 0.3 / 0.5 / 0.8 / 1.0 / 1.5 ATR）。

4. **人類 Go/No-Go（§4.2 Pilot gate，P6-1-CAL-8）**  
   - **Go**：delta_expectancy 在多日/多參數下穩定為正 + veto_rate 合理（不極端 0 或 100%） + 對整體 net expectancy 有正面或中性貢獻 → 提出校準過的 `trend_min_strength`（非零）供人類核可後才開 `trend_filter_enabled`。  
   - **No-Go**：維持 `false` + `min_strength=0.0`；或重新設計（真正正交 HTF kbar、session-anchored 等，另開任務）。  
   - 決策必須有**可追溯的 harness + sweep 報表 + WeeklyStatus 紀錄**；禁止「看起來不錯就開」。

### 驗收條件（A-class 已完成，B-class 待 UAT）
- A-class：`tests/reporting/test_trend_calibration.py` 5 項全綠；`tests/sweep/test_param_sweep.py` 新增 trend grid 案例含 `veto_metrics` key；`python run_tests.py` 全綠（現行 trading-app 69 項）。
- 無任何地方把 `trend_filter_enabled` 設 true 或 `min_strength>0` 作為預設/測試行為。
- 文件同步：本節 + TODO.md 目前狀態 + `trend.py` / `config.yaml` 語意說明（effective scale + 0.0 最嚴格警告）。
- B-class 後：真實 UAT log 跑 harness 產出有意義的 sensitivity 表 + delta 穩定性；人類簽核後才改 config 並 re-sweep。

### 與既有章節關係
- 補充 Phase 5 sweep 與 Phase 6 旗標的「校準前置」說明。
- 不改變任何回測確定性 hash、kbar no-lookahead、或 ATR 熱身規則（CAL-1 切片已另處理）。
- 與 P6-2/3 ATR 動態成對：趨勢濾網（少做爛單）優先於動態停損（控每筆風險）。

更新日期：2026-06-16（A-class 1-5 + `d127f50` follow-up 已 merge `main`；B-class 待永豐模擬 API + tick 累積）。

---

## 給實作模型的執行順序

1. Phase 3 `MockBroker` + `tests/backtest/test_mock_broker.py`
2. Phase 2 `backtest/engine.py` + `tests/backtest/test_backtester.py`（含 7.1 ATR 注入、7.2/7.3 迴圈順序）
3. 合成或真實 tick/kbar 快取煙霧測試
4. Phase 4 確定性（含 7.5/7.6）
5. Phase 5 參數掃描（含 StrategyParams / config patch）
6. Phase 7 策略介面（可選 plugin；預設 VWAP 行為不變）

每完成一步跑全測試（`python run_tests.py`）。
