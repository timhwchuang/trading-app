# Code Review — 回測系統 Phase 2–5（依 `BackTestingSpec.md`）

> 審查範圍：`feat/backtest-phase3-mock-broker`（撮合核心）、`phase2-backtester`（重放迴圈）、
> `phase4-determinism`（確定性閘門）、`phase5-param-sweep`（參數掃描）。四個分支為線性疊加，
> HEAD = phase5 已含全部程式碼。
> 審查方法：對照 Spec 黃金鐵律與驗收條件，逐檔讀 `mock_broker.py` / `backtester.py` /
> `determinism_check.py` / `param_sweep.py` / `data_loader.py`，並回讀 `man.py` /
> `observability.py` 驗證「同構性」與「確定性」是否真的成立。實測 `89 tests OK`。

---

## 總評

實作面**乾淨且守規矩**：`man.py` 對 `main` **零 diff**（`git diff main..HEAD -- man.py` 為空），
全部變更落在新增檔案；6.1 穿價 clamp、6.3 timeout 時序、6.4 試撮過濾、6.6 `man` namespace
patch、6.8 canonical hash 都有對應實作與測試，純標準庫、無 pandas/numpy。就「照規格實作」而言
完成度高。

但站在**程式交易實戰**角度，目前的回測有一個**致命的系統性問題**與兩個會在真資料下浮現的
中高風險缺陷，且**現有 89 個測試完全沒有覆蓋到「真的會交易」的路徑**，因此「全綠」給出的是
*管線正確*的保證，而非*回測結果可信*的保證。以下依嚴重度排列。

---

## P0（致命）— 必須在用回測做任何決策前處理

### P0-1　背景執行緒 ATR：同時破壞「確定性」與「無未來函數」

**證據**
- `man.py:446` `_maybe_refresh_atr` 以 **背景 daemon thread** 跑 `refresh_atr()`：
  ```446:446:man.py
              threading.Thread(target=self.refresh_atr, daemon=True).start()
  ```
- `refresh_atr()`（`man.py:454-490`）在該執行緒內呼叫 `self.api.kbars(...)`。
- 回測的 look-ahead 防護**完全依賴** `MockBroker.current_dt`：
  ```85:91:mock_broker.py
          for bar in bars:
              if current is not None and bar.ts > current:
                  continue
  ```
- 而 `current_dt` 是被**主迴圈每一筆 tick 覆寫**的可變狀態：
  ```43:49:backtester.py
              self.clock.set(tick.datetime.timestamp())
              self.broker.current_dt = tick.datetime
              ...
              self.strategy.on_tick(tick)
  ```

**為什麼是致命的**
1. **未來函數（look-ahead leak）**：ATR thread 在 tick N 被 spawn，但它真正執行
   `kbars()`、讀取 `self.broker.current_dt` 的時間點，受 GIL/排程左右，可能已經是主迴圈處理到
   tick N+k 的時候。此時 `current_dt` 早已前移 → ATR 把**尚未發生的 K 線**算進去。3.4 宣稱的
   no-look-ahead 在多執行緒下並不成立。
2. **非確定性**：`current_atr` 由背景緒在**不可預測的時點**寫入，而 `process_strategy`
   （`man.py:805` `if self.current_atr < MIN_ATR_THRESHOLD: return None`）與量能門檻都吃它，
   進而影響 `SIGNAL_AUDIT` / `FILL_AUDIT` / `DAILY_SUMMARY`（含 `operational.atr_min/max`）
   → **連跑 3 次 hash 不保證相同**。Phase 4 的「確定性閘門」在有真 K 線時是 flaky 的。

**為什麼目前測試「看起來」沒事（這才是最危險的）**
- 所有 Phase 2/4/5 測試用的是空的 `TemporaryDirectory` 快取 → `kbars()` 回空 → `_compute_atr`=0。
- `MIN_ATR_THRESHOLD=25`（`config.yaml:61`），ATR=0 時 `process_strategy` 在 `man.py:805`
  **一律不進場**。
- 換言之：`test_three_runs_same_hash`、`test_sweep_small_grid` 等，**從頭到尾沒有產生過任何一筆
  真實進出場**（`test_uat_report_parses_backtest_log` 是 monkeypatch 強塞 signal 才有 fill）。
  測試日誌可見 `ATR(20) 更新: 0.00`、`MockBroker has no attribute 'usage'` 反覆出現，正是這條
  背景緒在空轉。

  **結論：確定性閘門與參數掃描的綠燈，只證明了「沒有交易時三次都一樣」。真正會交易的路徑
  （ATR≥25 + 動量 + pullback）從未被任何測試驗證過確定性。**

**修正建議（需 spec owner 拍板，因為觸及黃金鐵律）**
- 黃金鐵律「回測只能注入 api 與 clock」**不足以**解決此問題——病灶是 `man.py` 的 thread spawn，
  不是 api/clock。請在 Spec 增列一個**最小注入縫**，二擇一：
  - (A) 注入「執行器」：`_maybe_refresh_atr` 改為呼叫 `self._run_async(self.refresh_atr)`，
    線上預設 `Thread(...).start()`，回測注入**同步直跑**版本。如此 ATR 在 tick N 當下、以
    tick N 的 `current_dt` 同步算完，確定且無 look-ahead。
  - (B) 若堅持 `man.py` 一字不改：在 `BacktestEngine` 把 `strategy._maybe_refresh_atr` 換成
    一個「同步呼叫 `refresh_atr`」的 bound method（屬注入縫，不動策略數學）。
- 無論採哪個，**請補一個「有真 K 線 + 會進場」的確定性測試**（連跑 3 次同 hash），否則 Phase 4
  形同未驗收。

---

## P1（高）— 真資料 / 真掃描時會出錯或誤導

### P1-1　DAILY_SUMMARY 內含 wall-clock 欄位，違反 6.2 的明示前置條件

**證據**
- 6.2 前置條件白紙黑字要求：「確認 DAILY_SUMMARY **不含 wall-clock**」。
- 但 `observability.build_summary` 把 `lock_wait_max_ms` 放進 summary：
  ```354:360:observability.py
                  "tick_type0_pct": round(type0_pct, 2) if type0_pct is not None else None,
                  "lock_wait_max_ms": self.lock_wait_max_ms,
                  "lock_wait_over_50ms": self.lock_wait_over_50ms,
                  "no_tick_resubscribe": self.no_tick_resubscribe,
                  "atr_min": self.atr_min,
                  "atr_max": self.atr_max,
  ```
- `lock_wait_max_ms` 來自 **`time.perf_counter()`**（`man.py:416-418` 量測 lock 等待），是純掛鐘量。
- `determinism_check._AUDIT_PREFIXES` 把整段 `DAILY_SUMMARY` 納入 hash（6.2 已實作）：
  ```14:14:determinism_check.py
  _AUDIT_PREFIXES = ("SIGNAL_AUDIT ", "FILL_AUDIT ", "DAILY_SUMMARY ")
  ```

**為什麼會咬人**
- `test_three_runs_same_hash` 現在會過，**純屬僥倖**：單執行緒、無競爭的 lock，量到的等待
  趨近 0，`round(x,3)` 多半收斂到 `0.0`。一旦 CI 機器有負載、GC、或 tick 數量變多，某一筆量到
  0.05ms → `lock_wait_max_ms` 改變 → **三次 hash 不一致，確定性閘門無預警裂開**。
- `atr_min/atr_max` 同樣受 P0-1 的背景緒非確定性污染。

**修正建議**
- 在 `determinism_check` 的正規化階段，hash 前**剔除 operational 內的非確定性欄位**
  （`lock_wait_max_ms`、`lock_wait_over_50ms`、`no_tick_resubscribe`，以及在 P0-1 修好前的
  `atr_min/atr_max`）；或把 hash 範圍限定在 summary 的「決策語意子集」（signals/fills/pnl/
  quick_stop_loss/near_miss）。不要把運維遙測欄位混進確定性指紋。

### P1-2　參數掃描漏 patch `observability` namespace → DAILY_SUMMARY.params 參數歸因錯誤

**證據**
- `observability.py` 於 import 時就把參數**綁進自己的模組命名空間**：
  ```10:40:observability.py
  from config import (
      ...
      ENTRY_BAND_POINTS,
      EXHAUSTION_VOL,
      ...
      VWAP_STOP_POINTS,
      ...
  )
  ```
- `build_config_snapshot()`（= DAILY_SUMMARY 的 `params` 快照）讀的就是這些 observability 自身的
  全域：`observability.py:390 "entry_band_points": ENTRY_BAND_POINTS` 等。
- 但 `param_sweep._apply_params` **只** patch `man.*` 與 `config.*`：
  ```30:36:param_sweep.py
  def _apply_params(params: dict[str, Any]) -> dict[str, tuple[Any, Any]]:
      saved: dict[str, tuple[Any, Any]] = {}
      for k, v in params.items():
          saved[k] = (getattr(man, k, None), getattr(config, k, None))
          setattr(man, k, v)
          setattr(config, k, v)
  ```

**影響**
- 6.6 的本意是「patch `config` 讓 DAILY_SUMMARY.params 同步反映掃描值」。但快照其實取自
  **`observability` 命名空間**，patch `config` 對它無效——這正是 6.6 自己警告過的同類陷阱，
  只是真正該打的第三個 namespace 被漏掉。
- 結果：掃描時 log 出的 `DAILY_SUMMARY.params.entry_band_points` 等，會顯示**舊值**，與該回合
  實際使用的決策值不一致。
- **緩解事實**：排序/選參**不受影響**——`sweep` 是用自己組出的 `params` dict 搭配
  `pnl`/`quick_stop_loss` 做歸因（`param_sweep.py:62-65, 121-128`），不讀 `DAILY_SUMMARY.params`。
  所以是「稽核軌跡誤導」而非「選錯參數」。但 `test_config_restored` 只驗 `man`/`config` 還原
  （`test_param_sweep.py:49-55`），完全沒測到這個 gap。

**修正建議**
- `_PATCH_TARGETS` 同步 patch `observability.*`（`setattr(observability, k, v)` 並一併還原），
  或讓 `build_config_snapshot()` 改讀 `config.*`（單一真相源）。並補一條測試：sweep 期間
  `DAILY_SUMMARY.params` 必須等於該回合掃描值。

---

## P2（中 / 觀念）— 不擋路但建議修

### P2-1　timeout-先於-撮合 在「冷清時段」會吃掉本該成交的單

- 主迴圈順序（6.3）為 `_check_pending_timeout()` → `on_tick()` → `process_matching_queue()`
  （`backtester.py:47-49`），`PENDING_TIMEOUT_SEC=8`（`config.yaml:70`）。
- 場景：tick N 下單，下一筆 tick N+1 在 **>8 秒**後才到（盤中冷清窗）。N+1 進迴圈時，
  `_check_pending_timeout` 先用新時鐘判定超時 → `_clear_pending()`；接著 `process_matching_queue`
  撮出成交，餵回 `FuturesDeal`，但 `man.py:1142` `if not self.is_pending: 忽略非 pending 成交回報`
  → **這筆成交被丟棄**。
- 6.3 的註記只證明了「同一 tick 內 timeout 不誤殺」，跨 tick 大間隔的情況沒涵蓋。線上 IOC 是
  毫秒級即成即撤，根本不會「等到下一筆 tick」；故此處兩邊行為都不算完全寫實，但回測會**系統性
  少算冷清時段的成交/取消**，且走 timeout 路徑不會累計 `intent_cancelled`（與線上 `FuturesOrder`
  Cancel 的 KPI 計數不一致，`man.py:1108-1127`）。
- 建議：在 Spec 補一句「撮合應先於 timeout 嘗試一次，僅在仍未成交時才交給 timeout」，或明確接受
  此偏差並記錄為已知 KPI bias。

### P2-2　`MockBroker` 缺 `usage()` → 每次 ATR refresh 噴 warning

- `refresh_atr` 末端呼叫 `_log_api_usage` → `api.usage()`，`MockBroker` 未實作 → 測試日誌反覆出現
  `API usage 查詢失敗 (atr_refresh): 'MockBroker' object has no attribute 'usage'`。
- Spec 3.1 雖標 `usage()` 可省略，但 `refresh_atr` 實際會打它。建議補一個 no-op
  `def usage(self): return SimpleNamespace(bytes=0, limit_bytes=0, remaining_bytes=0)` 降噪，
  避免真回測時 log 被洗版、也避免誤導判讀。

### P2-3　非交易時段 tick 被 `continue` 同時跳過撮合佇列

- `backtester.py:45-46`：非 session tick 直接 `continue`，連 `process_matching_queue` 都跳過。
- 6.4 要的是「不讓試撮 tick 污染 VWAP/動量」，這點達成；但副作用是：若有 in-flight 單卡在
  session 邊界、之後只剩非 session tick，該單永遠不被撮合/取消。實務上 13:44 強制平倉多半已收尾，
  風險低，但邏輯上留了個不會清空的佇列。建議：過濾只跳過 `on_tick`（決策），撮合/timeout 仍照跑。

### P2-4　KPI 聚合用未加權平均

- `param_sweep._aggregate_kpi`（`param_sweep.py:78-83`）對 `quick_stop_loss_rate` 做**各日簡單平均**，
  未用各日 exit 筆數加權。少交易日會被放大權重。對掃描排序影響通常不大，但建議改成
  「總 quick_sl 數 / 總 exit 數」較精確。

---

## 做得好的地方（保留）

- **黃金鐵律遵守**：`man.py` 對 `main` 零 diff；全部為新增檔案、純標準庫、無 `time.time()`/
  `datetime.now()`/`date.today()` 出現在新檔。
- **6.1 穿價 clamp 正確**：`mock_broker.py:128-137` 買單 `min(limit, close+slip)`、賣單
  `max(limit, close-slip)`；`test_fill_never_worse_than_limit` 用 `FLATTEN_SLIP=8` 驗到 18003 而非
  18008，語意對。
- **6.8 canonical hash 正確**：`determinism_check.canonical_audit_json` 先 `json.loads` 再
  `sort_keys=True` 重序列化，不動生產 log bytes，`test_hash_robust_to_key_order` 有效。
- **延遲閘門 / 滑價分層 / no-lookahead 過濾**邏輯與 Spec 一致（在「單執行緒、有 `current_dt`」前提
  下；race 見 P0-1）。
- **walk-forward 紀律正確**：`sweep` 只用 `valid_score` 排序（`param_sweep.py:132`），train 僅參考。
- **bid/ask 只做滑價校準、預設關**：`spread_calibration=False`（`mock_broker.py:38`），符合 6.7
  「不得當撮合基準」。

---

## 對照「Definition of Done」逐項判定

| DoD 項目 | 判定 | 說明 |
| --- | --- | --- |
| 各 Phase `test_*.py` 全綠（含既有） | ✅ | 實測 `89 tests OK`。 |
| 回測 log 可被 `uat_report.py` 解析 | ✅ | `test_uat_report_parses_backtest_log` 通過。 |
| 同資料連跑 3 次 SHA-256 一致 | ⚠️ **未真正驗收** | 僅在「無交易」案例驗過；有 ATR/交易時因 P0-1 + P1-1 為 flaky。 |
| `man.py` 決策邏輯零改動 | ✅ | `git diff main..HEAD -- man.py` 為空。 |
| 回測路徑無 `time.time()`/`now()`/`today()` | ⚠️ | 新檔無；但 hash 經由 `DAILY_SUMMARY.lock_wait_max_ms` **間接吃到 `perf_counter`**（P1-1）。 |
| 無 pandas / numpy | ✅ | 純 stdlib。 |

---

## 建議處理順序

1. **P0-1**（與 spec owner 確認注入縫）：ATR 改為回測可同步執行 → 同時解掉 look-ahead 與非確定性，
   並補「有真 K 線且會進場」的三跑同 hash 測試。**這是回測能不能信的前提。**
2. **P1-1**：把運維/掛鐘欄位排除在確定性 hash 之外。
3. **P1-2**：sweep 一併 patch `observability.*`（或快照改讀 `config.*`），補測試。
4. **P2** 各項視時間擇優處理（P2-1 KPI bias 至少要在文件標注為已知偏差）。

> 一句話總結：**程式碼很守規矩，但「確定性閘門」目前是在沒有交易的情況下自證清白。**
> 在把 P0-1 的 ATR 執行緒問題解掉、並用真 K 線跑出一次「會交易且三跑一致」之前，
> 不建議用這套回測的 KPI 或參數掃描結果去做任何上線決策。
