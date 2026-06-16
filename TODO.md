# VWAP Momentum 策略 — 上線迭代 TODO

> 目標：從 prototype 迭代為可上實戰的 production trading system。
> **目標執行環境：Windows**（開發、UAT、Pilot 皆以 Windows 為準；見 [`README.md`](README.md)）。
> 原則：**UAT 驗的是狀態機與對帳，不是看有沒有賺錢。**

### 目前狀態（2026-06-16）

| 階段                   | 狀態                                                                                                                                                                                                                       |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Phase 0 Blocker        | P0-1～P0-11 ✅（**P0-11** tick 落盤已實作；UAT hard gate 已解除）                                                                                                                                                           |
| Phase 1 訊號品質       | ✅ P1-1 / P1-2 / P1-5 / **P1-6 保護期** 完成；P1-3 UAT 觀測；P1-4 / P1-7 可選                                                                                                                                               |
| Phase 2 狀態機         | ✅ P2-3/4/5/6/7/8 完成；P2-2 核心；P2-1 待補（qty>1）                                                                                                                                                                       |
| **Phase 3 UAT**        | **可開跑**（待永豐模擬 API）— 見 [`docs/UATReminder.md`](docs/UATReminder.md)、[`docs/WeeklyStatus.md`](docs/WeeklyStatus.md)                                                                                              |
| Phase 4 運維           | P4-1/2/5/6/8/9/10 完成；**P4-3/4/11/12 ✅ 骨架已落地**（[`docs/WindowsOps.md`](docs/WindowsOps.md)；告警非同步派送）；Pilot 前實機驗證 Telegram                                                                             |
| Phase 5 Pilot          | 待 UAT 全過 + CA 憑證；**秒停損率（P2-7）為硬指標**                                                                                                                                                                        |
| **Phase 6 策略真實化** | **骨架已落地（旗標預設全關）**：P6-1～P6-3 + **P6-6 ✅**；**P6-1-CAL A 類 1～5 ✅ 已 merge `main`**（B 類 6～8 待 UAT tick；**非 UAT Blocker**）；**Live 前須 B 類校準 + 人類 Go/No-Go 才開旗標**；P6-4/5 待做 — 見 [`docs/CodeReview#2.md`](docs/CodeReview%232.md) |
| **Phase 7 策略介面**   | **✅ 已落地**：`Strategy` Protocol + `BaseStrategy`；host=`TradingEngine` / `BacktestEngine.host`；可注入自訂策略並 survive tick — 見 [`src/strategy/base.py`](src/strategy/base.py)                                        |
| **Phase 8 引擎抽離 / 事件**   | **✅ 全量 extraction + merge fix 落地**：`trading-engine/` vendored + CI `pip install -e`；`ShioajiOrderAdapter` / `MockOrderAdapter` 顯式接線；`strategy/base.py` re-export；`LOG_FILE`/`obs` 接回。🔜 事件層（NDJSON sink）待第一段乾淨 UAT 後；`session.sync_positions` Action 字串化 — 見 [`docs/Architecture.md`](docs/Architecture.md) |

> **UAT Ready ≠ Live Ready**。工程體質（狀態機 / 對帳 / 觀測）已達 UAT 標準（Review #2 評 8.5/10）；但 **Phase 6 策略真實化是「進正式盤」的 gate，不是「進 UAT」的 gate**。UAT 仍依本檔核心原則：**驗狀態機與對帳，不是看績效**。Phase 6 須在 **UAT 收集到足夠 tick / SIGNAL_AUDIT 數據後**校準，禁止憑空調參上線。

單元測試：`tests/test_*`（`python run_tests.py` **155** 項；mock API，見 P2-8 `test_helpers.make_host`）

---

## 外部 Code Review #1 — 評估摘要

> 完整原文：[`docs/CodeReview#1.md`](docs/CodeReview%231.md)（2026-06-10）

### 整體結論：可上線體質，工程面已防住多數實戰翻車點

| 面向                  | Review 評價                                           | 本地評估                                                                                                                                                                                       |
| --------------------- | ----------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Lock / 網路 I/O 邊界  | ✅ 正確                                                | 與 P2-2 一致，無需改動                                                                                                                                                                         |
| 非同步 log            | ✅ 正確                                                | P0-7 已落地                                                                                                                                                                                    |
| 交易所時間驅動        | ✅ 正確                                                | P0-6 已落地                                                                                                                                                                                    |
| Pending 狀態機        | ✅ 順序與防禦對                                        | P0-4 / P0-5 已落地                                                                                                                                                                             |
| 測試架構              | ⚠️ 每 test `new Shioaji()`，32 tests ~12s              | **同意**；應可注入 mock api（P2-8）                                                                                                                                                            |
| `futopt_account` None | ⚠️ 第一筆單才爆                                        | **同意，高優先** → P0-10                                                                                                                                                                       |
| No-tick 靜默斷流      | ❌ 目前只靠斷線 event                                  | **同意** → P4-8                                                                                                                                                                                |
| 委託回報欄位          | ⚠️ `status.status` / `deal_quantity` 可能不存在於 stub | **同意，UAT hard gate** → P0-9                                                                                                                                                                 |
| ATR 語意 / kbars 流量 | ⚠️ 20 根 1 分 K = 20 分鐘 ATR；盤中重複抓 10 天        | **同意** → 註解修正 + P4-9                                                                                                                                                                     |
| 策略：VWAP-3 停損     | 🔴 進場在 VWAP 附近 → 有效 SL ≈ 3 點                   | **同意，與 IOC±3 同類陷阱** → P1-6 / P2-7                                                                                                                                                      |
| 策略：進場條件        | 🟠 動量後等 pullback 到 VWAP，次數少、邏輯張力         | **UAT 階段視為設計取捨，非 bug**；用 SIGNAL_AUDIT 量化。**Review #2 進一步指出**：`near_vwap + exhausted` 雙條件在強勢單邊趨勢中等不到量縮回踩 → 錯過主升段 → 見 P6-1 趨勢濾網 + P6-5 追價進場 |
| `dynamic_threshold`   | 0.0001 × 20000 ≈ 2，動態項無效                        | **同意** → P1-7（可選）                                                                                                                                                                        |
| 命名：VWAP            | 實為 5 分鐘滾動 VWMA，會跟價漂移                      | **文件化**；停損跟漂加劇 P1-6                                                                                                                                                                  |
| `daily_pnl`           | 毛點數，未扣費稅滑價                                  | Pilot 對帳時以券商為準                                                                                                                                                                         |

---

## 外部 Code Review #2 — 策略升級評估（2026-06-12）

> 主題：**工程已達 UAT 體質，但「交易邏輯」仍是 prototype**。Review #2 的重點不在系統穩定性（那塊已給 8.5/10、UAT Ready = 是），而在「這套進出場邏輯放進真實血淋淋戰場會被巴成什麼樣」。

### 結論

| 項目                | 評價                                                                                    |
| ------------------- | --------------------------------------------------------------------------------------- |
| 程式品質（工程面）  | **8.5 / 10**                                                                            |
| UAT Ready           | **是**（驗狀態機 / 對帳 / 觀測，不看績效）                                              |
| Live / 正式盤 Ready | **否** — P6-1～3 / P6-6 **骨架已落地**；須 UAT tick 回測**校準 k 並開旗標**後才可 Pilot |

> Reviewer 原話：補上趨勢濾網 + ATR 動態 trailing / VWAP 停損後，「這其實已經是**新策略**，不是修策略」。因此另闢 **Phase 6**，與既有 Phase 0-5 的「修 prototype bug / 上 UAT」明確區隔。

### 三大核心診斷

| #   | 診斷                                      | 根因（對應現行碼）                                                                                                                                                                                                                              | 對策                                                                                |
| --- | ----------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| 1   | **進場過於嚴苛 → 與大波段無緣**           | `process_strategy` 要求 `near_vwap and exhausted` 同時成立（`man.py:843-852`）。強勢單邊量能持續高企，永遠等不到 `vol_1s <= EXHAUSTION_VOL` 的量縮回踩                                                                                          | **P6-1** 趨勢濾網（順勢才做）＋ **P6-5** 趨勢追價進場（第二套進場，不等回踩）       |
| 2   | **停損 / 停利未與 ATR 連動（最諷刺）**    | 已有 `refresh_atr()` 且 `current_atr` 用於量能門檻 `_vol_threshold`（`man.py:492`），卻在價格停損用固定 `HARD_STOP_POINTS` / `VWAP_STOP_POINTS` / `TRAIL_POINTS`（`man.py:913-917`、`932/952`）。波動大時固定點數易被掃，波動小時又讓出過多回撤 | **P6-2** `TRAIL_POINTS → ATR×k`、**P6-3** `VWAP_STOP_POINTS → current_vwap ± ATR×k` |
| 3   | **缺乏大週期趨勢濾網（Macro Blindness）** | 微觀量能只看 1 秒窗口（`vol_1s`），無更高時間框架定義「當日主趨勢」 → 盤整盤被來回雙巴、連續止損                                                                                                                                                | **P6-1** 5m/15m EMA 或 price slope + min_strength（Level 2）                        |

### Reviewer 優先級（→ 映射到本檔 Phase 6 ID）

| Reviewer 優先級 | 項目                                                       | 本檔 ID  |
| --------------- | ---------------------------------------------------------- | -------- |
| **P0**          | Trend Filter（5m EMA / price slope + Level2 min_strength） | **P6-1** |
| **P1**          | ATR Trailing（`TRAIL_POINTS → ATR×k`）                     | **P6-2** |
| **P1**          | ATR VWAP Stop（`VWAP_STOP_POINTS → ATR×k`）                | **P6-3** |
| **P2**          | Position Sizing（Risk based / 1% 法則）                    | **P6-4** |
| **P3**          | 第二套追價進場（Trend Entry）                              | **P6-5** |

> Reviewer 明確強調：**P6-1 / P6-2 / P6-3 對績效的影響遠大於 Position Sizing（P6-4）**。Position sizing 是「贏了之後賺更多」，趨勢濾網是「先不要一直輸」。

### 與既有 TODO 的關係（避免重工）

- **P1-4（SL/TP 與 ATR 掛鉤，原標可選）**：與 P6-2 / P6-3 重疊，**正式由 Phase 6 接手並升級**；P1-4 保留為歷史脈絡，實作以 P6-2 / P6-3 為準。
- **P1-6（進場保護期停損解耦）**：保護期內仍只看硬停損的設計不變；P6-3 只改「保護期結束後」VWAP 停損的點數來源（固定 → ATR 動態）。
- **核心原則不變**：Phase 6 屬 **Live 前** gate，**不阻擋 UAT**。且須以 **P0-11 累積的 tick + P2-7 / SIGNAL_AUDIT 數據** 校準 `k` 係數，不憑感覺設參數。

---

## 外部 Code Review #3 — Live 前防護網盤點（2026-06-15）

> 主題：reviewer 從「真槍實彈」角度列了四個 Live blocker。盤點後 **多數已落地**，但點出兩個真實缺口，已轉為 P4-11 / P4-12。

### 四點對照（reviewer 提出 → 現況）

| #   | Reviewer 提出                                  | 現況（對應碼）                                                                                                                                                                           | 結論                                          |
| --- | ---------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------- |
| 1   | 斷線重啟後狀態恢復與倉位對帳（Reconciliation） | ✅ 已落地 P0-3：`login()` → `sync_positions()`（`man.py:282`）重建 `position_dir`/`entry_price`/`trailing_peak`；首 tick `_calibrate_trailing_peak_after_resync` 重算停損（`man.py:510`） | **已完成**，無新工                            |
| 2   | 下單 API 異常捕獲（Exception Handling）        | ✅ 已落地 P4-11：`order_errors.py` 分類 + entry/exit 分流；exit 退避重試；`alerts.py` 非同步派送（`d5e2091` + review fix）                                                                | **已完成**（單元測試；實戰注入驗收 Pilot 前） |
| 3   | 斷線重連機制（Session Recovery）               | ✅ 已落地 P4-12：session watchdog 指數退避 `api.login()` → `_on_reconnected()`（`d5e2091`）                                                                                               | **已完成**（單元測試；斷網手測 Pilot 前）     |
| 4   | 複數口數與部分成交（Partial Fills）            | ✅ 防禦層已落地 P2-1：`pending_qty` 追蹤、`deal_qty < expected` → `CRITICAL` + 解鎖 + `sync_positions`（`man.py:1162-1177`）；完整多口管理 Phase 6（P6-4 前置）                           | **已有防禦**，完整實作見 P2-1 / P6-4          |

### 我的評估

- **這份 review 的價值不在「找到新 bug」，而在「驗收心態」**：它把 UAT-Ready 與 Live-Ready 的界線講清楚——模擬環境不會給你斷線、部分成交、API timeout，所以這些保護網在 UAT 不會被測到，卻是 Pilot 第一天的生死線。這與本檔既有的「UAT Ready ≠ Live Ready」原則完全一致。
- **多數點子工程面已防住**（P0-3 / P0-4 / P0-5 / P4-1 / P4-8 / P2-1），代表前面的迭代方向是對的。
- **兩個缺口已補（2026-06-15）**：① P4-11 下單異常分類 + 降級；② P4-12 session 退避重登。皆屬 **Live hard gate**（單元測試已過），**不阻擋 UAT**；Pilot 前建議手動斷網 / 注入 timeout 再驗一次。
- reviewer 的直球問題（「`place_order` 送出後 >5s 全無回報該怎麼降級」）已併入 **P4-11** 的降級風控政策。

---

## 你的三點診斷 — 評估

| #   | 問題                                 | 評估                                               | 優先級 |
| --- | ------------------------------------ | -------------------------------------------------- | ------ |
| 1   | 秒進秒出（`momentum_peak` 停利失效） | ✅ 已修（P0-1，momentum_peak / trailing_peak 分離） | —      |
| 2   | 週一 / 連假後 ATR 斷層               | ✅ 已修（P1-1，`atr_kline_lookback_days=10`）       | —      |
| 3   | 部分成交追蹤缺失                     | ✅ 正確，qty=1 時暫不顯性，但架構必須預留           | P2     |
| 4   | 開盤前 15 分鐘 ATR 量能閾值失效      | ✅ 已修（P1-2，Time Windows 階梯）                  | —      |

### 優化建議評估

| 建議                                                               | 評估                                                              |
| ------------------------------------------------------------------ | ----------------------------------------------------------------- |
| `momentum_peak` 改為 Trailing Stop（從高點回落 X 點）或只用固定 TP | ✅ 推薦 Trailing Stop + 固定 TP 並存，語意最清楚                   |
| K 線 `start` 往前推 7-10 天                                        | ✅ 推薦，Shioaji 會過濾非交易日                                    |
| 量能閾值 = ATR 動態基底 × 開盤時間階梯係數                         | ✅ **強烈推薦**；單純 `ATR × 固定係數` 在 08:45-09:15 會大量假突破 |
| 開盤量比（Volume Ratio）平滑曲線                                   | ⏸ 留作 Phase 2 優化；首版用 Time Windows，好維護、可預期          |
| 開盤放大 IOC 讓價以提高成交率                                      | ❌ **禁止**；與固定 6 點 SL 數學衝突，見下方「進場滑價 vs 停損」   |
| 開盤漏單（IOC Cancelled）                                          | ✅ **可接受甚至預期**；用 P1-2 量能階梯減少訊號，而非硬咬單        |

### 設計原則：寧可漏單，不硬咬（上線初期）

進場與出場參數必須**成對設計**。目前風控：

- 停損：保護期內僅 `entry ± 6`；之後 `entry ± 6` 或 `VWAP ± 3`（見 P1-6）
- 進場 IOC 讓價：固定 `ref_price ± 3`

若在 08:45 / 09:00 為求成交將 IOC 放大到 ±5～±8，流動性空洞時極易成交在極端價：

```
有效停損緩衝 ≈ SL(6pt) − 進場滑價(5pt) = 1pt
→ 反向跳 1 點即「進場即秒停損」，手續費 + 滑價雙重失血
```

**結論**：開盤亂流期的正確防禦是 **P1-2 提高量能門檻（少做）**，不是 **放大 IOC 讓價（硬做）**。漏單是成本；阿呆價進場是結構性虧損。

> 若未來真要提高開盤成交率，須先走 **P1-4（SL/TP 與 ATR 掛鉤）** 等比例放寬出場，**禁止單獨**放大 IOC。

### 坑十：VWAP 停損與「在 VWAP 進場」交互 — ✅ 已用保護期解耦

進場時 `price ≈ vwap ≈ entry` 會使 `vwap-3` 比 `entry-6` 更緊 → 有效停損約 3 點。

**已落地（進場保護期）**：`exit_grace_ticks` + `exit_grace_sec` 內僅 `hard_stop_points`；兩者皆滿足後才啟用 `vwap_stop_points`（audit `stop_loss_vwap`）。重啟對帳持倉跳過保護期。

- **UAT**：P2-7 觀測秒停損率是否下降；`stop_loss` vs `stop_loss_vwap` 分布
- **P1-6**：若仍偏高，再調 `exit_grace_*` / `vwap_stop_points`（有數據再動）

---

## 實戰 Production 踩坑與防禦

> 台指期 + Shioaji 實戰最常半夜被叫醒的隱性致命傷。

### 坑一：時間扭曲（Exchange Time vs System Time）

| 現況（`man.py` + `exchange_time.py`）                                          | 風險                             |
| ------------------------------------------------------------------------------ | -------------------------------- |
| `process_strategy` / `is_trading_session` 用 `tick.datetime`                   | ✅ 正確                           |
| `pending_since` / `_check_pending_timeout` 用 `time.time()` 算經過秒數         | ✅ 相對耗時可接受（僅背景執行緒） |
| `last_exit_time` 存 exchange `ts`；cooldown 同用 tick `ts`                     | ✅ 已統一（P0-6）                 |
| P1-2 開盤階梯用 `tick.datetime` → `exchange_time.opening_session_multiplier()` | ✅ 已統一（P0-6 + P1-2）          |

- [x] **P0-6 策略內時間源統一（Exchange Time）**
  - 原則：**所有「幾點幾分」判斷與 tick 驅動的時間差，一律用 `tick.datetime`（交易所時間）**；`time.time()` 僅限背景執行緒的相對耗時（如 pending 超時秒數）。
  - 方案：
    - `last_exit_time` 改存 exchange `ts`（與 `COOLDOWN_SEC` 比較一致）
    - P1-2 `_opening_session_multiplier(dt)` 參數來源固定為 `tick.datetime`（台灣時區），禁止 `datetime.now()`
    - **交易時段邊界**單元測試（exchange time）：
      - `08:44:59` → 非交易時段；`08:45:00` → 進入
      - `13:44:59` → 仍可交易；`13:45:00` → `SESSION_END` 擋新信號（與 P2-3 flatten 連動）
      - P1-2 階梯邊界：`08:59:59` / `09:00:00` / `09:14:59` / `09:15:00`
    - 邊界語意寫死：`SESSION_START <= t <= SESSION_END`（inclusive）
  - 運維：上線前伺服器必裝 **chrony** 硬核對時（log 對帳、告警時間戳仍依賴系統鐘）
  - 驗收：人為 offset 系統鐘 ±2s，開盤階梯與 cooldown 行為不變。

### 坑二：Lock 內包了網路 I/O（Network I/O inside Lock）

| 現況                                                                          | 評估                                 |
| ----------------------------------------------------------------------------- | ------------------------------------ |
| `place_order`：`api.place_order` 在 lock **外**                               | ✅ 正確                               |
| `on_tick`：signal 產生後 lock 內 `_arm_pending()`，再出 lock 下單             | ✅ 已修（P2-2 核心）                  |
| `_reconcile_pending_trade`：`update_status` / `order_deal_records` 在 lock 外 | ✅ 正確                               |
| `on_tick`：整段 `process_strategy` 仍在 `with self.lock` 內                   | ⏸ UAT 後視延遲決定是否縮小 lock 範圍 |

- [x] **P2-2 下單路徑與 Lock 邊界（核心）**
  - 原則：**Lock 內只做狀態讀寫與 signal 組裝；任何 `api.*` 網路呼叫一律在 lock 外。**
  - 已落地：
    - `on_tick` lock 內：產生 signal → `_arm_pending(signal)` → `_log_signal_audit(signal)`
    - `place_order`：不再重複設 pending，僅負責 `api.place_order` 與寫入 `pending_order_id`
  - 待 UAT 後視需要：
    - 縮短 `on_tick` lock 範圍（策略計算移出 lock，僅 commit 時加鎖）
  - 驗收：開盤高頻區間無雙單；UAT 觀測 lock 等待是否 > 50ms

### 坑三：開盤 IOC Cancelled — 症狀，不是待修 bug

- 現況：進場限價固定 `ref_price ± 3`（IOC），**全日不變**。
- 現象：08:45:01 / 09:00:05 流動性空洞時，單 tick 可跳 4-6 點 → IOC 未成交 → Log「訊號→下單→補查未成交→解鎖」。
- **正確解讀**：這是 IOC ±3 在保護你不在極端價進場；P0-4 確保不留幽靈倉。**漏單是預期行為，不是系統故障。**
- ❌ **已否決**：開盤放大 IOC 讓價（原 P2-5）— 與 6 點固定 SL 數學衝突，實戰等於送手續費。
- ✅ **正確槓桿**：
  - **P1-2** 開盤量能階梯 → 從源頭減少低品質訊號（少下單，而非硬成交）
  - **P0-4** 超時解鎖 → Cancelled 後狀態機正常恢復
- [x] **P2-5 開盤漏單監控（僅觀測，不改讓價）**
  - 已落地：`tag=intent_cancelled`；08:45-09:15 為 `intent_cancelled_open_session`
  - UAT / Pilot：grep log 統計開盤 vs 中盤取消率；成交滑價 < 2 點

### 坑四：同步 Log I/O 阻塞 Callback（Python 隱形惡魔）

| 現況（`man.py` 修復前）                               | 風險                                                       |
| ----------------------------------------------------- | ---------------------------------------------------------- |
| `logging.basicConfig` → `StreamHandler` 同步寫 stdout | 每次 `logger.info()` 觸發 syscall，幾 ms 延遲              |
| `on_tick` / `process_strategy` 熱路徑直接 `logger.*`  | 08:45 tick 暴雨時 Callback 執行緒排隊 → P2-2 Lock 優化失效 |
| Phase 4-2 若再加 `FileHandler` 到 root                | 磁碟 write 直接進熱路徑，雪上加霜                          |

- [x] **P0-7 非同步佇列日誌（UAT 前必做）**
  - 方案（已落地 `man.py`）：
    - **`QueueHandler` + `QueueListener`**（標準庫）：Callback 僅 `put_nowait` 入隊，O(1) 非阻塞
    - 背景執行緒專職 `StreamHandler`（＋可選 `LOG_FILE`）磁碟 I/O
    - `shutdown_async_logging()` 於程序結束時 flush
    - 生產環境維持 `LOG_LEVEL=INFO`，**禁止**在 `on_tick` 熱路徑開 DEBUG 逐 tick log
  - 驗收：
    - 開盤高頻 tick 期間 Callback 無可觀察延遲堆積
    - 關閉進程後 log 完整落盤（listener stop flush）
  - 與 P4-2 分工：P0-7 負責**非阻塞架構**；P4-2 僅在 Listener 端加 `TimedRotatingFileHandler`

### 坑五～九：實戰常見但尚未踩的坑（預防性）

| 建議                          | 是否納入 TODO  | 歸類  |
| ----------------------------- | -------------- | ----- |
| Shioaji Callback 執行緒安全   | ✅              | P2-6  |
| API 斷線 / Rate Limit         | ✅ 強化 P4-1    | P4-1  |
| 交易時間邊界（08:45 / 13:45） | ✅ 併入 P0-6    | P0-6  |
| 週一 / 連假第一根 K 缺失      | ✅ 已有         | P1-1  |
| 模擬 vs 實盤差異              | ✅ 強化 Phase 5 | Pilot |
| 日虧隔日重置                  | ✅ 已完成       | P0-8  |
| 每筆 signal 結構化 log        | ✅              | P1-5  |
| Prometheus / InfluxDB         | ✅ 未來項       | P4-7  |

---

## Phase 0 — Blocker 修復（UAT 前必做）

這些不修，UAT 結果不可信。

- [x] **P0-1 修正停利 / 停損邏輯**
  - 問題：`_update_momentum_peak` 在 `process_strategy` 之前執行，導致 `price >= momentum_peak` 進場後下一 tick 即觸發。
  - 方案（擇一或並存）：
    - A) `momentum_peak` 僅用於 Trailing Stop：`price <= momentum_peak - TRAIL_POINTS`（多單）
    - B) 固定 TP 保留 `entry_price ± 20`，移除 `price >= momentum_peak` 比較
  - 驗收：進場後價格持平至少 N 個 tick 不應觸發 TP。

- [x] **P0-2 日虧上限仍須允許平倉**
  - 問題：`daily_pnl <= -MAX_DAILY_LOSS` 在 `has_position` 判斷之前 return，持倉卡死。
  - 方案：日虧觸發時 `block_new_entry = True`，但 `has_position` 時仍執行 `manage_exit`。
  - 驗收：模擬觸發日虧後，持倉仍可正常出場。

- [x] **P0-3 啟動時持倉對帳**
  - 問題：`has_position` 僅存於記憶體，重啟後與券商脫節。
  - 方案：`login()` 後呼叫 `api.list_positions()`，同步 `has_position` / `entry_price` / `position_dir`。
  - **Invariant**：對帳後 `trailing_peak = entry_price`，設 `_resynced_position`；首 tick 校準為多 `max(entry, tick)` / 空 `min(entry, tick)`。
  - 驗收：人工在券商端有倉 → 重啟程式 → 策略正確識別並管理出場；log 見 `peak 待首 tick 校準` → `持倉 peak 校準`。

- [x] **P0-4 Pending 超時與補查**
  - 問題：IOC 未成交或回報遺失 → `is_pending` 永久 True，策略癱瘓。
  - 方案：
    - 設定 `PENDING_TIMEOUT_SEC`（建議 5-10 秒）
    - **`_timeout_loop` 背景執行緒每秒 kick `_check_pending_timeout()`**（`start()` 內 `threading.Thread` 啟動；僅寫函式不啟動執行緒 = 仍會卡死）
    - 超時後 `update_status()` 或 `order_deal_records()` 補查（網路 I/O 在 lock 外）
    - 超時仍無成交 → `_clear_pending()`
  - 驗收：
    - 模擬回報遺失，策略在超時後恢復可交易。
    - 確認 log 有週期性 timeout loop 存活（或 pending 期間有超時檢查觸發紀錄）。

- [x] **P0-5 成交回報綁定 order id**
  - 問題：任何 `FuturesDeal` 在 `pending_intent == "entry"` 時都更新持倉。
  - 方案：下單時記錄 `trade.order.id`，deal 回報比對後才更新狀態。
  - 驗收：舊單遲到成交不影響當前狀態。

- [x] **P0-6 策略內時間源統一（Exchange Time）**
  - 模組：`exchange_time.py`；`last_exit_time` / cooldown / 時段邊界 / P1-2 階梯皆用 tick 時間
  - 測試：`test_exchange_time.py`

- [x] **P0-7 非同步佇列日誌**
  - `QueueHandler` + `QueueListener`；`LOG_FILE` env 可選啟用檔案 log

- [x] **P0-8 日虧 / 風控狀態隔日重置**
  - 問題：`daily_pnl`、`block_new_entry`、`consecutive_loss` 目前**無隔日重置**；跨日運行會沿用昨日虧損，可能開盤即被誤鎖。
  - 已落地：`exchange_time.trading_day_for_daily_reset()` — **日盤假設交易日 = 台灣日曆日**；夜盤擴展前須改為 TAIFEX 15:00 切換。
  - `_reset_daily_state()` 重置：`daily_pnl=0`、`block_new_entry=False`、`consecutive_loss=0`
  - 驗收：模擬跨日運行 → 新交易日可正常進場；昨日觸發日虧不影響今日。

- [x] **P0-9 UAT 第一天：dump 原始 order/deal 回報 dict** — **UAT hard gate**
  - 問題：`_handle_futures_order` 讀 `msg["status"]["status"]`、`deal_quantity`，但 Shioaji `_core.pyi` 的 `EventOrderStatusDict` **無這兩欄**；若 runtime 亦無，則 `status` 永遠 `""`、`deal_qty` 永遠 `0`，委託回報分支靜默失效（目前靠 `operation.op_type` + `FuturesDeal` 撐住）。
  - 已落地：`DUMP_ORDER_EVENTS=1`（env）→ `handle_order_event` 對每種 `OrderState` **各 dump 一次**（`RAW_ORDER_EVT` log）。
  - UAT 待辦：啟用 env 跑一筆委託/成交 → 確認真實欄位名 → 修正或簡化 `_handle_futures_order`

- [x] **P0-10 `futopt_account` None 防呆**
  - 已落地：`login()` 後 `_require_futopt_account()`，無期貨戶即 `RuntimeError`。
  - 驗收：無期貨戶登入 → 啟動即失敗；有期貨戶 → 正常對帳

- [x] **P0-11 UAT 盤中非同步 tick 落盤** — **UAT hard gate（已實作，2026-06-15）**
  - 背景：決策**不再**用 API 批量下載過往 tick；改在 UAT 模擬盤中累積推播 tick → `tick_cache/`，作為日後回測樣本（見 [`docs/WeeklyStatus.md`](docs/WeeklyStatus.md)）。
  - 問題：策略已訂閱 tick 推播，但未落地；UAT 開跑卻不存檔 → 無法累積回測資料，且錯過唯一低成本取樣窗口。
  - 原則（[`CALLBACK_GUARDRAILS.md`](docs/CALLBACK_GUARDRAILS.md)）：**禁止**在 `on_tick` 內同步磁碟 I/O；與 **P0-7** 同構——callback 僅 `put_nowait` 入隊，背景執行緒負責寫檔。
  - 方案：
    - `on_tick`：在 `with self.lock` **之前**複製 `datetime/close/volume/tick_type/bid/ask` → 非阻塞 queue
    - 背景 `TickArchiver`：盤中**只 append plain** `.csv`（欄位與 `data_loader.save_ticks_csv` 同構）
      - 路徑：`tick_cache/{product_code}_{YYYY-MM-DD}.csv`
      - 批次 flush（例如每 500 筆或每 2s）；**盤中不做 gzip**（crash 時逐行可讀、不拖 trading CPU）
    - **gzip 與落盤分離**（二擇一或並用，與 P4-2 log rotate 同哲學）：
      - **A) Rotate（建議內建）**：跨日換檔或 `shutdown` 時，背景執行緒對**已關閉**的昨日 `.csv` → `gzip` → `.csv.gz` 並刪除原檔；當日檔維持 plain 直到收盤
      - **B) 排程器（建議並用）**：`src/compress_tick_cache.py`（或同級腳本）掃 `tick_cache/*.csv`（排除當日進行中檔）→ 壓成 `.csv.gz`；Windows **工作排程器**每日 15:30 / 16:00 執行（補 crash 未 rotate 的檔）
      - `data_loader`：`load_ticks_csv` / `iter_replay_ticks` **同時支援** `.csv.gz` 與 `.csv`（優先 `.gz`）
    - 跨日自動換檔；程序結束 `atexit` / `shutdown` 時 drain queue、flush 當日 `.csv`，並觸發 A) rotate
    - UAT 啟用：`TICK_ARCHIVE=1`（env）；queue 滿則丟棄並計數，**絕不阻塞** callback
    - 選配（建議同輪）：kbars 同策略 — `KBARS_ARCHIVE=1` → `kbar_archiver.py` 寫 `{code}_kbars_{date}.csv`（**✅ 已落地 `bd142f5`**）
  - 驗收：
    - `TICK_ARCHIVE=1` 跑滿交易時段 → 當日 `.csv` 可讀；收盤後 rotate 或排程器執行後 → `.csv.gz` 可 `iter_replay_ticks`
    - 關閉進程後檔案完整、無截斷列
    - 開盤高頻區間策略行為與未啟用時一致（落盤不得拖慢 `on_tick`）
  - 測試：archiver 單元測試（入隊、換日、shutdown flush、rotate→gzip）；`compress_tick_cache` 單元測試；不依賴真 API

---

## Phase 1 — 資料與訊號品質

- [x] **P1-1 修正 ATR K 線請求範圍**
  - 問題：週一 / 連假後 `yesterday = today - 1 day` 可能無交易資料，**當日第一根 K 尚未生成** → ATR = 0，整天不進場。
  - 方案：`start = today - timedelta(days=10)`，`end = today`；取最後 `ATR_PERIOD` 根計算（Shioaji 自動過濾非交易日）。
  - **語意澄清（Review #1）**：`api.kbars` 預設 **1 分 K** → `ATR_PERIOD=20` = **最近 20 分鐘 TR 平均**（日內波動濾鏡），**非** 20 日。`min_atr_threshold=25` = 「20 分鐘 ATR ≥ 25 點才交易」。`config.yaml` 註解應改為「1 分 K 根數」避免誤解。
  - 驗收：週一 08:44 前啟動、連假後首日啟動，ATR > 0 且合理。

- [x] **P1-2 動態量能閾值（ATR 基底 + 開盤時間階梯）**
  - 問題：
    - `MOMENTUM_VOL_1S = 150` 固定值，平淡市易假突破。
    - **單純 `ATR × 固定係數` 在開盤前 15 分鐘失效**：台指期「雙開盤」（08:45 期貨、09:00 現貨）tick 密集度與成交量可達中盤數倍～數十倍，滾動 ATR 跟不上瞬間爆量 → 閾值過低 → 開盤亂流假突破、來回洗盤。
  - 設計決策：**首版採 Time Windows 階梯式**（非 Volume Ratio 平滑曲線）
    - 理由：邏輯透明、參數可審計、UAT 好對帳；量比曲線留待有足夠 tick log 後再校準。
  - 方案：
    ```python
    base_vol = max(BASE_VOL, current_atr * ATR_VOL_MULT)
    vol_threshold = base_vol * opening_session_multiplier(now)

  # opening_session_multiplier 建議初值：
  #   08:45-09:00  期貨開盤爆量期  → 2.5 ~ 3.0
  #   09:00-09:15  現貨開盤衝擊期  → 1.5 ~ 2.0
  #   09:15 之後   常態流動性      → 1.0
    ```
  - 已落地：
    - `exchange_time.py`：`opening_session_multiplier()`、`compute_vol_threshold()`
    - `man.py`：`_vol_threshold(dt)` 取代 `MOMENTUM_VOL_1S`；動量觸發 log 含 base/mult/threshold
    - 測試：`test_volume_threshold.py`（階梯邊界 `08:59:59` / `09:00:00` / `09:14:59` / `09:15:00`）
  - 驗收：
    - 09:15 前後各 30 分鐘：對比「僅 ATR 基底」vs「ATR + 階梯」，開盤假訊號數應明顯下降。
    - 09:15 後常態時段：訊號頻率與現行固定 150 或純 ATR 基底相近，不應過度緊縮。
    - 週一 / 連假後開盤：階梯係數仍生效（與 P1-1 ATR 斷層修復連動測）。

- [ ] **P1-3 檢視 tick_type 推斷品質** — UAT 觀測項（非 blocker）
  - 問題：`tick_type == 0` 時用價格方向推內外盤，可能扭曲 buy/sell ratio。
  - 方案：UAT 期間以 `LOG_LEVEL=DEBUG` 統計 `tick_type` 分布；若 0 佔比高，考慮改用 Shioaji 原生欄位或降低依賴。
  - 驗收：開盤 30 分鐘統計 type 0/1/2 比例。

- [ ] **P1-4 SL/TP 與 ATR 掛鉤（可選）** — ⤴ **已由 Phase 6（P6-2 / P6-3）接手升級**
  - 問題：進場用 ATR 濾鏡，出場卻固定 6/3/20 點。
  - 方案：例如 `sl_points = max(6, atr * 0.25)`，`tp_points = max(20, atr * 0.8)`。
  - 驗收：高低波動日風險報酬比趨於一致。
  - 備註：可與 **P1-6** 合併設計（VWAP 停損 + entry 停損成對調整）。
  - **2026-06-12（Review #2）**：本項正式由 **P6-2（ATR Trailing）** + **P6-3（ATR VWAP 停損）** 取代並細化；此處保留歷史脈絡，實作以 Phase 6 為準。

- [x] **P1-6 進場保護期停損解耦（核心）**
  - 已落地：`exit_grace_ticks=60`、`exit_grace_sec=30`；保護期內僅 `hard_stop_points`；之後 `vwap_stop_points` + 硬停損
  - 測試：`test_exit_grace.py`
  - **UAT 後可選微調**：`vwap_stop_points`、grace 參數（須 P2-7 數據）

- [x] **P1-7 進場帶寬參數化**
  - 已落地：`entry_band_points: 2.0`（取代無效 `vwap * 0.0001`）

- [x] **P1-5 結構化 Signal Audit Log**
  - 模組：`signal_audit.py`；log 前綴 `SIGNAL_AUDIT` + JSON 一行
  - 欄位：`ts`、`intent`、`direction`、`price`、`vol_1s`、`buy_ratio`、`sell_ratio`、`atr`、`multiplier`、`vol_threshold`、`vwap`、`reason`
  - 出場 reason：`stop_loss` / `take_profit` / `trailing_stop` / `session_force_flatten`
  - 驗收：隨機抽 5 筆 signal，人工可還原當下濾鏡狀態

---

## Phase 2 — 委託與持倉狀態機

- [ ] **P2-1 部分成交支援** — qty=1 時非 UAT blocker
  - 問題：qty > 1 時部分成交會立刻 `is_pending = False`，剩餘委託失去追蹤。
  - **已落地防禦層**：`pending_qty` 追蹤；`deal_qty < expected` → `CRITICAL` log、解鎖 pending、`sync_positions()` 以券商為準（不 crash）。
  - 待完整實作：`filled_qty` 累計、IOC 結束前不全解鎖、多口持倉管理
  - 驗收：模擬 3 口僅成交 1 口，狀態正確。

- [x] **P2-3 收盤強制平倉**
  - 已落地（`config.yaml` → `session`）：
    - `flatten_time: "13:40"` 後禁止新進場
    - `force_flatten_time: "13:44"` 仍有倉 → aggressive IOC（`flatten_slippage_points: 8`）
  - Log：`收盤強制平倉 | ...`；audit `reason=session_force_flatten`
  - 測試：`test_session_flatten.py`
  - 驗收：收盤前持倉必定清空。

- [x] **P2-4 進場後 peak 更新時機**
  - 與 P0-1 連動：明確區分
    - **進場前 momentum peak**（突破偵測用）
    - **持倉後 trailing peak**（出場用，僅在 manage_exit 內更新或獨立變數）

- [x] **P2-6 Shioaji Callback 執行緒安全守則**
  - 已落地：[`docs/CALLBACK_GUARDRAILS.md`](docs/CALLBACK_GUARDRAILS.md)

- [x] **P2-7 秒停損率量化（UAT / Pilot 硬指標）**
  - 已落地：`uat_report.py` 解析 log 中 `SIGNAL_AUDIT` + `MOMENTUM` 行。
  - 用法：`python src\uat_report.py C:\logs\theman-uat.log`（`--json` / `--quick-sl-sec 5`）
  - 輸出：動量觸發數、進場數、轉換率、秒停損筆數與比例、出場 reason 分布
  - Pilot 通過標準：**秒停損率趨近 0**（比成交率更重要）；偏高則觸發 P1-6

- [x] **P2-8 測試可注入 mock API**
  - 已落地：`TradingEngine(api=...)`、`test_helpers.make_host()`、`test_deal_state_machine.py`

---

## Phase 3 — UAT 測試清單

> **開發端 blocker：P0-11 已完成（2026-06-15）。** 驗收步驟見 [`docs/UATReminder.md`](docs/UATReminder.md)。

UAT 通過標準：**每項有 log 證據 + 人工對帳一致**。

### 3.0 UAT 第一天（Review #1 最小檢查清單）

- [ ] **P0-11** 設 `TICK_ARCHIVE=1`，確認當日 `.csv` 落盤；rotate / 排程器後 `.csv.gz` 可 `iter_replay_ticks` 重放
- [ ] **P0-9** 設 `DUMP_ORDER_EVENTS=1`，跑一筆委託/成交 → 依 `RAW_ORDER_EVT` 確認欄位名
- [x] **P0-10** `futopt_account` 啟動時檢查（已落地）
- [x] **P4-9** `api.usage()` 於 login / atr_refresh log；盤中 ATR 改抓當日 K（已落地）
- [x] **P2-7** `uat_report.py` 後處理腳本（已落地）；UAT 期間每日對 log 跑報表

### 3.1 冒煙測試（模擬環境）

- [ ] 登入、訂閱 tick、收到 order callback
- [ ] 進場 → 成交 → `has_position` / `entry_price` 正確
- [ ] 出場 → `daily_pnl` / `consecutive_loss` 正確
- [ ] IOC 未成交 → pending 正確解鎖
- [ ] 進場後價格持平 **不會** 秒出（P0-1）

### 3.2 狀態機壓力測試

- [ ] 日虧觸發後仍可平倉（P0-2）
- [ ] 程式重啟後 `list_positions` 對帳（P0-3）
- [ ] pending 超時恢復（P0-4）
- [ ] 跨日日虧狀態重置（P0-8）
- [ ] 時段邊界 08:44:59 / 08:45:00 / 13:44:59 / 13:45:00（P0-6）
- [ ] 斷線 30s / 5min 後重連行為（P4-1，可選手動測；未自動化）
- [x] 下單拋 timeout / 拒單 → 分類 + 降級（P4-11；**程式已落地 + 單元測試**；UAT 非 blocker，Pilot 前可模擬注入）
- [x] session down 後內建重連不觸發 → watchdog 退避重登（P4-12；**程式已落地 + 單元測試**；UAT 非 blocker）
- [ ] 收盤前強制平倉（P2-3）

### 3.3 市況覆蓋

- [ ] 週一開盤 ATR 正常（P1-1）
- [ ] 平淡市況（09:15 後）：動態量能閾值減少假訊號（P1-2）
- [ ] **08:45-09:00** 期貨開盤：高 tick 密度下訊號不過度頻繁（階梯 2.5-3.0×）
- [ ] **09:00-09:15** 現貨開盤：第二波波動不引發洗盤（階梯 1.5-2.0×）
- [ ] **09:15 邊界**：multiplier 切換瞬間無異常訊號暴增
- [ ] 連續 10+ 交易日模擬，記錄每筆 signal vs fill

### 3.4 對帳

- [ ] 每日策略 log vs 券商成交明細一致
- [ ] 滑價統計（信號價 vs 成交價）
- [ ] 成交率統計（IOC 送出 vs 實際成交）；**開盤 Cancelled 高於中盤視為正常**
- [ ] 開盤 30 分鐘：成交筆進場滑價分布（P2-5 觀測）；確認未為成交率放大 IOC
- [ ] 系統鐘 offset ±2s 時，開盤階梯 / cooldown 行為不變（P0-6）

---

## Phase 4 — 運維與實戰準備（Windows）

> 以下以 **Windows 10/11 或 Windows Server** 為部署目標。Linux 替代方案附註供參考。

- [ ] **P4-0 Windows 上線檢查清單**
  - [ ] Python venv 已建立，`.venv\Scripts\activate` 可正常啟動
  - [ ] 環境變數 `SJ_API_KEY` / `SJ_SEC_KEY`（＋正式模式 `SJ_CA_*`）已設定
  - [ ] 系統時區為 **台北 (UTC+8)**；自動對時已開啟
  - [ ] 交易時段電腦不睡眠、不自動重開（Windows Update 延後）
  - [ ] `LOG_FILE` 目錄（如 `C:\logs\`）已建立且執行帳號可寫入
  - [ ] 開機自動啟動：工作排程器或 NSSM 服務（見 README.md）

- [x] **P4-1 API 斷線重連與 API 呼叫節流**（核心已落地，UAT 手動斷網驗證）
  - `set_event_callback`：event 12 重連中 / 13 重連成功；`set_session_down_callback` 斷線
  - 斷線期間：`_api_connected=False`，禁止新進場，持倉仍可 `manage_exit`
  - 重連後 `_on_reconnected()` 順序：**① pending 補查 → ② sync_positions → ③ subscribe → ④ refresh ATR**
  - **Rate Limit 紀律**：
    - `update_status` / `order_deal_records` **僅**在 pending 超時補查時呼叫（現行 `_timeout_loop` 已 ok）
    - 禁止在 `on_tick` 或高頻路徑輪詢 API
    - 斷線期間：停止新進場，持倉僅嘗試平倉（若連線允許）
  - 驗收：人為斷網 30s / 5min 恢復後狀態正確；log 無 API 轟炸

- [x] **P4-2 日誌持久化與輪替**
  - 已落地：`LOG_FILE` → `TimedRotatingFileHandler`（midnight，保留 14 天）；I/O 在 QueueListener

- [x] **P4-3 告警**
  - 已落地：`alerts.py` Telegram + webhook；**非同步 queue 派送**（不阻塞 callback / `_timeout_loop`）
  - 觸發：exit 重試耗盡、pending 超時、session 重登失敗、entry 致命拒單
  - Pilot 前：設定 `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` 實機驗收（見 [`docs/WindowsOps.md`](docs/WindowsOps.md)）

- [x] **P4-4 進程守護（Windows）**
  - 已落地：[`docs/WindowsOps.md`](docs/WindowsOps.md)、`scripts/windows/start-theman.ps1`、`register-task.ps1`
  - UAT：工作排程器開機觸發 + 收盤後 `compress_tick_cache.py`

- [x] **P4-6 系統對時觀測**
  - 已落地：tick 路徑偵測 `|系統時間 − 交易所時間| > clock_skew_warn_sec` → WARNING（每 5 分鐘最多一筆）
  - Windows：仍須手動確認 NTP（`w32tm /resync`）；策略決策以 tick 時間為準（P0-6）

- [x] **P4-5 設定外部化（YAML）**
  - `config.yaml`：策略參數、時段、開盤階梯預留欄位
  - `config.py`：`load_config()` → `Settings` dataclass
  - **密鑰不進 YAML**：`SJ_API_KEY` / `SJ_SEC_KEY` / `SJ_CA_*` 僅 env
  - 覆寫：`CONFIG_PATH` 指向自訂 yaml；`LOG_LEVEL` / `LOG_FILE` env 優先於 yaml
  - 驗收：改 yaml 重啟後參數生效，無需改 `man.py`

- [ ] **P4-7 指標匯出（未來，非 UAT blocker）**
  - 將 P1-5 關鍵決策變數匯出為時序資料，便於事後分析與儀表板
  - 候選：Prometheus gauge/counter、InfluxDB line protocol、或每日 parquet
  - 指標範例：`vol_1s`、`vol_threshold`、`signal_count`、`ioc_cancel_rate`、`callback_lag_ms`
  - 前提：P0-7 非同步 log 已穩定；匯出寫入亦不得阻塞 callback

- [x] **P4-8 No-tick 心跳看門狗**
  - 已落地：`no_tick_timeout_sec=45`；`_timeout_loop` 內告警 + 重訂閱（60s 節流）
  - UAT：觀測 log `No-tick 看門狗`

- [x] **P4-9 kbars 流量控管（Pilot 前）**
  - 已落地：
    - `refresh_atr`：ATR=0 或當日首次 → 長 lookback（P1-1）；之後僅抓**當日** K 線
    - `_log_api_usage`：`login` / `atr_refresh` 後 log bytes/limit/remaining；剩餘 < 10% 時 WARNING
  - UAT 驗收：log 見 `lookback=當日`；`API usage` 行可審計全日流量

- [x] **P4-10 `activate_ca` person_id 容錯**
  - 已落地：先無 person_id；失敗則 `SJ_CA_PERSON_ID` 或 `futopt_account.person_id` 重試

- [x] **P4-11 下單 API 異常分類與降級風控** — ✅ **已落地（Live hard gate；UAT 非 blocker）**
  - `order_errors.py`：retryable / fatal / unknown；`should_retry_order`（entry 永不重試、exit 才退避）
  - `man.py`：exit 重試耗盡 → CRITICAL + 告警 + `block_new_entry` + `sync_positions`；entry fatal → 清 pending
  - pending 超時無回報 → 強制對帳 + `block_new_entry` + 告警（entry / exit 皆發）
  - 驗收：**單元測試** `test_live_guards.py`；Pilot 前建議模擬 timeout / 拒單注入

- [x] **P4-12 Session 看門狗（主動重登入 + 退避）** — ✅ **已落地（Live hard gate；UAT 非 blocker）**
  - `_disconnect_since` 超門檻 → 指數退避 `api.login()`；成功走 `_on_reconnected()`；連續失敗 CRITICAL 告警
  - 驗收：**單元測試** `test_live_guards.py`；Pilot 前建議手動斷網驗 session down

---

## Phase 5 — 小資金實戰（Pilot）

> UAT 全過 ≠ 可實戰。此階段用真錢驗證滑價與成交率。

### 模擬 vs 實盤：預期落差（必讀）

| 維度        | 模擬環境           | 實盤                               |
| ----------- | ------------------ | ---------------------------------- |
| 流動性      | 理想化，IOC 易成交 | 開盤空洞、Cancelled 明顯增多       |
| 滑價        | 偏小               | 08:45-09:15 可能遠大於 ±3          |
| 回報速度    | 穩定               | callback 延遲、偶發遺失（靠 P0-4） |
| 心理 / 操作 | 無                 | 1 口也會影響參數調整節奏           |

**Pilot 第一天重點**：固定 1 口，**只觀察不調參**，專看 08:45-09:15 實際滑價與 Cancelled 率（P2-5）。

- [ ] `SIMULATION = False`，CA 設定完成
- [ ] 固定 1 口，連續 2-4 週（**禁止** UAT 剛過即加大口數）
- [ ] 每日人工對帳（策略 PnL vs 券商損益）
- [ ] 統計：成交率、平均滑價、最大回撤、連續虧損、**開盤漏單率**（Cancelled / 訊號數）
- [ ] Pilot 通過標準（建議，可調整）：
  - 無未預期持倉 / 幽靈單
  - 無收盤留倉
  - 對帳差異 = 0
  - 成交筆平均進場滑價 < 2 點（開盤時段尤須審計）
  - **開盤漏單率高可接受**；**P2-7 秒停損率趨近 0** 才是硬指標
  - `daily_pnl` 為毛點數；Pilot 對帳以券商成交明細為準（含手續費 / 稅）

### 策略預期管理（Review #1）

- 進場需：動量觸發 → 180s 內 pullback 到 VWAP ±~2 且 `vol_1s <= 15` → **進場次數少是設計使然**
- 動量強時價格常不回 5 分 VWMA（落後）→ 錯過主升；回到 VWAP 時常代表動量轉弱 → **動量訊號 + 均值回歸進場** 方向假設需 UAT 驗證
- 用 SIGNAL_AUDIT 統計：**動量觸發數 / 實際進場數 / 秒停損率**，作為 P1-6 校準依據

---

## Phase 6 — 策略真實化（Live / 正式盤前必補）

> 來源：[`docs/CodeReview#2.md`](docs/CodeReview%232.md)。**這是把 prototype 交易邏輯升級為「能進真實戰場」的新策略層**，不是修 bug。
>
> **Gate 定位**：
> - **不阻擋 UAT**（UAT 驗狀態機 / 對帳，見核心原則）。
> - **阻擋 Pilot / 正式盤**：P6-1（P0）、P6-2 / P6-3（P1）為 **Live hard gate**。
> - **校準紀律**：所有 `k` 係數、EMA / slope 門檻一律以 **P0-11 累積 tick + UAT 期間 SIGNAL_AUDIT / P2-7 數據** 回測校準後才設定；**禁止憑感覺直接上線**。
> - **回測前提**：依賴 P0-11 的 `tick_cache/` 與 [`docs/BackTestingSpec.md`](docs/BackTestingSpec.md) 重放管線；先有資料，再談調參。

### 設計原則：先求不被巴死，再求賺更多

進出場參數仍須**成對設計**（延續「進場滑價 vs 停損」紀律）。Phase 6 的順序刻意是 **濾網（少做爛單）→ 動態停損（控制每筆風險）→ 口數（放大已驗證的優勢）**，與 reviewer「趨勢濾網 ≫ position sizing」一致。

- [x] **P6-1 大週期趨勢濾網（Trend Filter）** — ✅ **骨架已落地（`trend_filter_enabled: false`）**；🔴 **校準後才開（Live hard gate）**
  - 已落地：`strategy/trend.py`（`compute_trend` + `min_strength` Level 2）；`config.yaml` 參數齊全；entry / veto audit `trend_dir` / `trend_strength`；ATR 正規化 gating（`3573ef7`）；開盤跨日緩解 + end-aligned resample（`1773fbc`）；SMA-seed EMA（`31881ca`）
  - **逐步校準清單**：見下方 **「P6-1-CAL 趨勢濾網校準工作流」**（一項一項勾，勿跳步）

#### P6-1-CAL 趨勢濾網校準工作流（2026-06-16，策略 + 量化雙 Review 合併）

> **Gate 定位（請勿誤判）**
>
> | 分類 | 是否 UAT Blocker | 說明 |
> | ---- | ---------------- | ---- |
> | **UAT 開跑** | **否** | `trend_filter_enabled: false` 預設；UAT 驗狀態機 / 對帳，不要求濾網有 edge |
> | **A 類（金鑰前）** | **否** | 工程衛生 + 校準工具；安全 merge，不碰 live / 不開旗標 |
> | **B 類（UAT 期間）** | **否（阻擋 UAT）／是（阻擋開旗標）** | 需模擬 API + `TICK_ARCHIVE=1`；**完成前不得開 `trend_filter_enabled` 或設 `min_strength > 0`** |
> | **Pilot / Live** | **是（Live hard gate）** | B 類決策 gate 未過 → 維持旗標關閉 |
>
> **Review 共識**：濾網目前是「與微動量同尺度的短窗啟發式」，**不構成統計驗證過的 edge**；價值在於「可量測的否決器」——必須用 `reason=trend_veto` 的 SIGNAL_AUDIT 做條件期望值分析，否則禁止憑參數上線。

**已完成（骨架 + review 回饋第一輪）**

- [x] **P6-1-CAL-0a** `trend_veto` SIGNAL_AUDIT + `obs.record_trend_veto()`（`a66b183`）— 被擋候選可追蹤
- [x] **P6-1-CAL-0b** ATR 正規化 `min_strength`（strength/ATR；raw strength 保留 audit）（`3573ef7`）
- [x] **P6-1-CAL-0c** 開盤跨日污染緩解（`closes[-800:]` 啟發式）+ end-aligned `resample_closes`（`1773fbc`）
- [x] **P6-1-CAL-0d** EMA SMA seed + 邊界測試（choppy / gap / latest bar）（`31881ca`）
- [x] **P6-1-CAL-0e** `min_strength=0` 語意警告（docstring + config 註解：0 = 最嚴格否決，非最寬鬆）

**A 類 — 金鑰前可逐步完成（不阻擋 UAT；建議 merge 前做完 1→2）**

- [x] **P6-1-CAL-1 交易所時間切片** — ✅ 取代 `engine.py` `approx_bars_per_trading_day=400`（`a9613df` + review fix）
  - 用 kbar `Datetime` + `exchange_time.trading_day_for_daily_reset` + `select_recent_trading_days_closes` 保留最近 **1～2 個完整交易日** 的 1m closes 餵 `compute_trend`
  - 驗收：單測涵蓋跨夜跳空、早收、連假後開盤；**定量 regression guard 證明未切片輸入會產生錯誤 regime**（sparse recent day → Flat vs polluted full → fabricated direction）
  - 檔案：`src/runtime/engine.py`、`src/exchange_time.py`（新 helper + _ts_ns_to_naive_dt）、`src/backtest/mock_broker.py`（_KBars.ts 對稱）、`tests/strategy/test_trend.py` + `tests/test_exchange_time.py`
  - CQR review（persona）已執行並 address 完 High 項（guard 真正證明、doc 誠實、max_days 說明、無 bare except）。

- [x] **P6-1-CAL-2 校準 harness（條件期望值）** — ✅ 濾網能否被誠實校準的關鍵基建（`e191774` + CQR fix）
  - `src/reporting/trend_calibration.py`：`compute_trend_veto_calibration` + `make_synthetic_veto_scenario`（pure，注入式 forward）
  - 產出 **veto_rate**、**delta expectancy**、forward stats；idx 語意正確（用 synthetic ts 作為原始 price index）
  - 先用 synthetic 驗 harness（5 單測：choppy/強逆勢/empty/邊界）；真實 delta 待 B-class UAT log + replay
  - 檔案：`src/reporting/trend_calibration.py`、`tests/reporting/test_trend_calibration.py`
  - CQR review（Block → Pass w/ notes）：math 修復、SYNTHETIC GUARD 強制文件化、dead param 移除、notes 誠實。

- [x] **P6-1-CAL-3 param_sweep 納入趨勢參數** — ✅（`5ac2959` + `d127f50` follow-up）
  - sweep grid 接受 `trend_filter_enabled` / `trend_min_strength`（snake_case → `TREND_*` via `SWEEP_FIELD_TO_CONST`）
  - `_run_backtest_summaries` 回傳 `SIGNAL_AUDIT`；`veto_metrics` 餵 harness（`reason=trend_veto` vs allowed entry）
  - engine `refresh_atr` 以 runtime `_config` 讀 `TREND_*`（sweep patch 生效）
  - **A 類限制**：`delta_expectancy` 仍須 B 類 `get_forward_pnl`（tick replay）才有決策價值
  - 檔案：`src/sweep/param_sweep.py`、`src/strategy/params.py`、`tests/sweep/test_param_sweep.py`

- [x] **P6-1-CAL-4 命名 / 文件誠實化** — ✅（與 CAL-5 一併）
  - `trend_ema_period` / `trend_timeframe_min` 文件化為「有效尺度 ≈ tf × period（分鐘）」，short-window displacement proxy，**非真正 macro bias**
  - config.yaml + trend.py docstring + BackTestingSpec 均加說明 + 指向 SOP；yaml alias 僅文件概念（key 不變）
  - 檔案：`config/config.yaml`、`src/strategy/trend.py`（module doc）、`docs/BackTestingSpec.md`

- [x] **P6-1-CAL-5 BackTestingSpec 校準 SOP** — ✅（本節 + 同步）
  - 新增完整「P6-1 Trend Filter Calibration Workflow」章節（accumulate → harness(CAL-2) → sweep 含 trend(CAL-3) → 決策表 Go/No-Go）
  - 驗收條件、A/B-class 區分、與既有 Phase 5/6 關係、鐵律（無數據不調參）均文件化
  - 同步 TODO.md 目前狀態 / Changelog + WeeklyStatus.md 頂節（AGENTS 紀律）
  - 檔案：`docs/BackTestingSpec.md`（新章節 + 狀態表）、`theman/TODO.md`、`docs/WeeklyStatus.md`

**B 類 — UAT 期間逐步完成（需永豐模擬 API；完成前 = Live 開旗標 Blocker）**

- [ ] **P6-1-CAL-6 累積真實樣本** — `TICK_ARCHIVE=1` + `KBARS_ARCHIVE=1`；連續數日
  - 參考：[`docs/UATReminder.md`](docs/UATReminder.md)

- [ ] **P6-1-CAL-7 跑條件分析**
  - 用 P6-1-CAL-2 harness 跑真實 UAT log + tick replay
  - 產出：`trend_min_strength` 敏感度表（0.0 / 0.3 / 0.5 / 0.8 / 1.0 / 1.5 ATR）、veto_rate、delta expectancy、秒停損率變化
  - **決策輔助問題**：veto 掉的單事後賺還賠？若 delta≈0 或負 → 濾網 ROI 低，考慮重設計或不上線

- [ ] **P6-1-CAL-8 人類 Go/No-Go（§4.2 Pilot gate）**
  - **Go**：delta expectancy 穩定為正 + veto_rate 合理 → 提出校準過的 `trend_min_strength`（非零）供人類核可後才開 `trend_filter_enabled`
  - **No-Go**：維持旗標關；或改做真正正交 HTF（獨立抓 30m/日 K、session-anchored VWAP）— 另開任務，不在本清單

**建議執行順序**：`0*（已完成）` → **1** → **2** → **3** → **4** → **5** →（等 API）→ **6** → **7** → **8**

- [x] **P6-2 ATR 動態 Trailing Stop** — ✅ **骨架已落地（`atr_trailing_enabled: false`）**；校準後才開
  - 已落地：`dynamic_trail_points`；exit audit `trail_points_used` + `atr`
  - 待 UAT：校準 `trail_atr_k` / `trail_points_floor`；回測 trailing_stop 分布

- [x] **P6-3 ATR 動態 VWAP 停損** — ✅ **骨架已落地（`atr_vwap_stop_enabled: false`）**；校準後才開
  - 已落地：`dynamic_vwap_stop_distance`；保護期語意不變（P1-6）
  - 待 UAT：校準 `vwap_stop_atr_k`；與 P6-2 **成對**回測後同時開旗標

- [ ] **P6-4 風險基準 Position Sizing（Risk-based）** — Reviewer P2（Live 後優化）
  - 問題：目前固定 1 口（`OrderSignal(..., 1, ...)`，`man.py:857-872`、`941-965`）。
  - 方案：依 **1% 風險法則**或 **ATR 換算**動態決定口數——`qty = floor(account_equity * risk_pct / (stop_distance * point_value))`。
  - **強依賴 P2-1**：qty > 1 需先完成**部分成交追蹤**（`filled_qty` 累計、IOC 結束前不全解鎖、多口持倉管理），否則狀態機會在部分成交時失準。**P2-1 未完成前，P6-4 不得啟用 qty > 1。**
  - 新增參數：`position_sizing_mode`（`fixed` / `risk_pct` / `atr`）、`risk_pct`、`max_contracts`、`account_equity`（或由 API 查詢）。
  - 紀律：Pilot 第一天仍固定 1 口（見 Phase 5）；P6-4 是 UAT/Pilot 驗證策略有正期望值**之後**才放大，不是上線即開。
  - 驗收：模擬不同 equity / ATR 下口數計算正確且受 `max_contracts` 上限保護；qty>1 路徑通過 P2-1 部分成交測試。

- [ ] **P6-5 第二套追價進場（Trend Entry）** — Reviewer P3（選配，最後做）
  - 問題：唯一進場路徑要求 `near_vwap and exhausted`（`man.py:843-852`），強勢趨勢中市場不給量縮回踩 → 完全錯過主升 / 主跌段。
  - 方案：在 P6-1 趨勢濾網**確認強勢**時，啟用備選進場——
    - **分批**：第一筆維持嚴格 pullback 條件；第二筆放寬（允許不回 VWAP 的追價）。
    - **追價邏輯**：momentum 持續強勢（`vol_1s` 維持高檔、buy/sell ratio 維持）且順主趨勢 → 允許在離 VWAP 較遠處進場。
  - 風險控管：追價進場的停損必須**對應放寬**（與 P6-2 / P6-3 ATR 動態停損連動），禁止用追價的遠進場價配固定 6 點 SL（否則進場即虧結構性緩衝，見「進場滑價 vs 停損」）。
  - 前提：**P6-1 / P6-2 / P6-3 全部落地並回測通過後**才實作；否則只是放大暴露。
  - 驗收：趨勢日追價進場能參與主波段；以回測比較「僅 pullback」vs「pullback + 追價」的期望值與最大回撤。

- [x] **P6-6 生存指標：期望值 / 最大回撤 / 夏普（Go/No-Go 績效閘門）** — ✅ **已落地（`65a463d` + review fix `1c3f677`）**
  - 已落地：`performance_metrics.py`（gross/net 期望值、MDD 權益曲線種子 0、跨日串接 MDD、Sharpe/Sortino）；`uat_report` 生存指標區塊；`observability` DAILY_SUMMARY `performance`；`param_sweep` `sweep_score_from_kpi`；摩擦成本三模式
  - 驗收：**單元測試** `test_performance_metrics.py`；determinism `test_performance_in_daily_summary_hash_stable`
  - 使用：UAT 累積 tick 後 `uat_report.py` / `param_sweep.py` 以 **net 期望值 + MDD** 排序選參（`friction_enabled: true` 校準後）
  - 設計備註（保留）：gross = 毛點數含 MockBroker 滑價；net = gross − 設定摩擦；Pilot 以券商成交明細為最終真相

---

## 建議實作順序

```
✅ P0-1 停利邏輯
✅ P0-2 日虧平倉
✅ P0-3 啟動對帳
✅ P0-4 pending 超時（含 _timeout_loop）
✅ P0-5 order id 綁定
✅ P0-6 時間源統一 + test_exchange_time
✅ P0-7 非同步佇列日誌
✅ P0-8 日虧隔日重置
✅ P1-1 ATR K 線 lookback
✅ P1-2 開盤階梯量能閾值 + test_volume_threshold
✅ P1-5 Signal Audit Log（signal_audit.py）
✅ P2-2 核心（_arm_pending 防雙單）
✅ P2-3 收盤平倉 + test_session_flatten
✅ P4-5 config.yaml 外部化
✅ P0-11 UAT tick 非同步落盤（`tick_archiver.py` + `compress_tick_cache.py`）
✅ P0-11 選配 kbars 落盤（`KBARS_ARCHIVE=1` + `kbar_archiver.py`）
✅ P4-3 告警（非同步）+ P4-4 Windows 運維文件 / 腳本
✅ P4-11 下單異常分類 + P4-12 session 看門狗
✅ P6-6 生存指標 + 摩擦成本；P6-1～P6-3 骨架（旗標預設關）
→ Phase 3 UAT（模擬環境，simulation: true；`TICK_ARCHIVE=1`）  ← 目前在這
  → UAT Day 1：P0-11 落盤驗證、P0-9 dump 回報、P0-10 futopt_account、P4-9 usage 基線
  → UAT 期間：P2-7 秒停損率 + 動量→進場轉換率觀測；累積 tick / kbars
  → UAT 後：回測校準 → **開 P6-1～P6-3 旗標** → `param_sweep` 風險調整選參
  → Phase 5 Pilot（CA 憑證 + simulation: false，固定 1 口）

— 以下為 Review #2 策略真實化（Live 前 gate，須先有 P0-11 tick 回測資料）—
→ ✅ P6-6 生存指標（已落地）
→ ✅ P6-1-CAL **A 類 1～5 已 merge `main`**（`d127f50`）；**B 類 6→8** 待 UAT tick → 人類 Go/No-Go 才開旗標
→ 🟡 P6-2 / P6-3 骨架已落地 → **UAT 回測校準 k 後開旗標**（Live hard gate）
→ P6-4 風險口數（Reviewer P2；前置 P2-1 部分成交）
→ P6-5 趨勢追價進場（Reviewer P3，選配，最後做）
```

**Review #1 建議優先落地（不改交易邏輯）**：**P0-11** → P0-10 → P0-9（DEBUG dump）→ UAT 收 P2-7 數據 → 再動 P1-6

**Review #2（策略真實化，Live 前）**：P0-11 累積 tick → UAT 收 SIGNAL_AUDIT / P2-7 → 回測校準 → **P6-1（P0）→ P6-2 + P6-3（P1，成對）→ P6-4（P2）→ P6-5（P3）**。順序鐵律：**先濾網（少做爛單）→ 再動態停損（控每筆風險）→ 最後放大口數 / 追價**。

UAT 後可選：~~P1-4~~（已併入 P6-2 / P6-3）、P2-1 部分成交（P6-4 前置）、P2-2 lock 範圍縮小、~~P4-3 告警~~（已落地）

---

## 參數待校準（UAT 期間記錄）

> 現值來自 [`config/config.yaml`](config/config.yaml)；UAT 期間依實際市況調整後記錄於此。

| 參數                      | 現值   | 備註                                                          |
| ------------------------- | ------ | ------------------------------------------------------------- |
| `BASE_VOL`                | 150    | 量能地板；`opening_volume.base_vol`                           |
| `ATR_VOL_MULT`            | 1.0    | 常態 ATR 換算係數；UAT 掃描                                   |
| `OPEN_MULT_FUTURES`       | 2.5    | 08:45-09:00；建議範圍 2.5-3.0                                 |
| `OPEN_MULT_SPOT`          | 1.5    | 09:00-09:15；建議範圍 1.5-2.0                                 |
| `OPEN_MULT_NORMAL`        | 1.0    | 09:15 之後                                                    |
| `MOMENTUM_VOL_1S`         | 150    | **已廢止於邏輯**；僅 yaml 保留參考，實際用 `_vol_threshold()` |
| `TRAIL_POINTS`            | 8      | Trailing Stop 回落點數                                        |
| `PENDING_TIMEOUT_SEC`     | 8      | pending 超時補查                                              |
| `ATR_PERIOD`              | 20     | **1 分 K 根數** → 20 分鐘 ATR（非天數）；見 P1-1 語意澄清     |
| `ATR_KLINE_LOOKBACK_DAYS` | 10     | K 線回溯天數（P1-1）；盤中重抓見 P4-9                         |
| `VWAP_WINDOW_MIN`         | 5      | 滾動 VWMA（非日內錨定 VWAP）；停損見 P1-6 / 坑十              |
| `SESSION_FLATTEN_TIME`    | 13:40  | 禁止新進場（P2-3）                                            |
| `SESSION_FORCE_FLATTEN`   | 13:44  | 強制平倉（P2-3）                                              |
| `FLATTEN_SLIPPAGE_POINTS` | 8      | 強平 IOC 讓價（僅 session_force_flatten）                     |
| `IOC_SLIPPAGE_POINTS`     | 3      | **全日固定**，開盤不放大；與 SL(6) 配對設計                   |
| `LOG_LEVEL`               | INFO   | UAT 觀測 tick_type 可暫開 DEBUG                               |
| `ENTRY_BAND_POINTS`       | 2.0    | pullback 進場帶寬（P1-7）                                     |
| `EXIT_GRACE_TICKS`        | 60     | 進場保護期 tick 數（P1-6）                                    |
| `EXIT_GRACE_SEC`          | 30     | 進場保護期秒數（P1-6）                                        |
| `NO_TICK_TIMEOUT_SEC`     | 45     | 看門狗無 tick 門檻（P4-8）                                    |
| `LOG_FILE`                | （空） | UAT 建議設 `C:\logs\theman-uat.log`                           |

### Phase 6 參數（已進 `config.yaml`；旗標預設關，回測校準後才開）

> P6-1～P6-3 / P6-6 參數已進 yaml；**初值須以 P0-11 tick + kbars 回測校準**，禁止憑感覺上線。

| 參數                         | 對應項  | 用途                                                        |
| ---------------------------- | ------- | ----------------------------------------------------------- |
| `trend_filter_enabled`       | P6-1    | 趨勢濾網總開關                                              |
| `trend_timeframe_min`        | P6-1    | 高時間框架（5 / 15 分）                                     |
| `trend_mode`                 | P6-1    | `ema` / `slope`（linreg price slope on HTF closes）         |
| `trend_ema_period`           | P6-1    | EMA 週期（trend_mode=ema）                                  |
| `trend_slope_min`            | P6-1    | Slope 門檻（trend_mode=slope；單位為每 HTF bar 的價格變化） |
| `trend_min_strength`         | P6-1 L2 | 最小強度（ATR 單位；有 ATR 時 strength/ATR 後比較）；**0.0 = 最嚴格否決**；校準見 **P6-1-CAL** |
| `trail_atr_k`                | P6-2    | Trailing = `max(floor, atr × k)` 的 k                       |
| `trail_points_floor`         | P6-2    | Trailing 地板（沿用現行 `trail_points`）                    |
| `vwap_stop_atr_k`            | P6-3    | VWAP 停損 = `vwap ± atr × k` 的 k                           |
| `vwap_stop_points_floor`     | P6-3    | VWAP 停損地板（沿用現行 `vwap_stop_points`）                |
| `atr_trailing_enabled`       | P6-2    | ATR Trailing 總開關（預設 `false`）                         |
| `atr_vwap_stop_enabled`      | P6-3    | ATR VWAP 停損總開關（預設 `false`）                         |
| `position_sizing_mode`       | P6-4    | `fixed` / `risk_pct` / `atr`（前置 P2-1）                   |
| `risk_pct`                   | P6-4    | 單筆風險佔權益比例（1% 法則）                               |
| `max_contracts`              | P6-4    | 口數上限保護                                                |
| `sharpe_period`              | P6-6    | 夏普報酬週期：`per_trade` / `daily`                         |
| `sweep_score_metric`         | P6-6    | sweep 排序主鍵：`expectancy_net` / `sharpe_net` / `pnl_net` |
| `sweep_dd_penalty`           | P6-6    | sweep 分數的最大回撤懲罰係數 λ_dd                           |
| `friction_enabled`           | P6-6    | 報表 / sweep 是否扣除摩擦成本                               |
| `friction_mode`              | P6-6    | `flat_round_trip` / `per_side` / `ntd`                      |
| `round_trip_friction_points` | P6-6    | 每筆 round-trip 固定摩擦（點）；`flat_round_trip` 用        |
| `commission_per_side_points` | P6-6    | 每邊成交手續費（點）；`per_side` 用                         |
| `tax_per_exit_points`        | P6-6    | 每筆出場期交稅（點）；`per_side` 用                         |
| `point_value_ntd`            | P6-6    | 每點新台幣價值；微台 **10**、`ntd` 模式換算用               |

### P1-2 未來優化（非 blocker）

- Volume Ratio 平滑曲線：以開盤前 N 根 1 分 K 相對量比動態縮放 multiplier，取代硬階梯；需先累積 tick / K 線 log。

---

## Changelog

| 日期       | 項目                                                                                                                                                                                                                    |
| ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-06-10 | 初版建立，整合 code review + 三點診斷 + 分 phase TODO                                                                                                                                                                   |
| 2026-06-10 | P0-1：分離 momentum_peak / trailing_peak，固定 TP + Trailing Stop                                                                                                                                                       |
| 2026-06-10 | P0-2：日虧觸發 block_new_entry，持倉仍可 manage_exit                                                                                                                                                                    |
| 2026-06-10 | P0-3：login 後 sync_positions 對帳 has_position / entry_price                                                                                                                                                           |
| 2026-06-10 | P0-4：PENDING_TIMEOUT_SEC + update_status / order_deal_records 補查                                                                                                                                                     |
| 2026-06-10 | P0-5：deal/order 回報比對 pending_order_id 後才更新狀態                                                                                                                                                                 |
| 2026-06-10 | P1-2 升級：ATR 基底 + 雙開盤 Time Windows 階梯量能閾值（取代單純 ATR×係數）                                                                                                                                             |
| 2026-06-10 | 新增實戰踩坑章節：時間源統一 P0-6、Lock/網路 I/O P2-2、chrony P4-6                                                                                                                                                      |
| 2026-06-10 | 否決開盤放大 IOC；確立「寧可漏單不硬咬」；P2-5 改為漏單觀測                                                                                                                                                             |
| 2026-06-10 | P0-7：QueueHandler + QueueListener 非同步日誌；坑四同步 I/O 阻塞                                                                                                                                                        |
| 2026-06-10 | 第二輪實戰建議：P0-8 日虧重置、P1-5 audit log、P2-6 callback 守則、強化 P4-1/Pilot                                                                                                                                      |
| 2026-06-10 | P4-5：`config.yaml` + `config.py` 參數外部化；密鑰仍走 env                                                                                                                                                              |
| 2026-06-10 | 新增 README.md；標明 Windows 為目標執行環境；P4-0 Windows 上線檢查清單                                                                                                                                                  |
| 2026-06-10 | P0-6/P0-8 交易所時間 + 隔日重置；單元測試 test_exchange_time                                                                                                                                                            |
| 2026-06-10 | P1-1/P1-2 ATR lookback + 開盤量能階梯；test_volume_threshold                                                                                                                                                            |
| 2026-06-10 | P1-5 SIGNAL_AUDIT JSON log；P2-3 收盤強制平倉；P2-2 lock 內 _arm_pending                                                                                                                                                |
| 2026-06-10 | UATReminder 擴充 Phase 0-3 驗收指南；可進入模擬 UAT                                                                                                                                                                     |
| 2026-06-10 | TODO 同步：目前狀態表、參數現值、實作順序、Phase 3 可開跑標記                                                                                                                                                           |
| 2026-06-10 | UAT 前批次：P1-7/P2-5/6/8、P4-2/6/8/10、CALLBACK_GUARDRAILS                                                                                                                                                             |
| 2026-06-10 | P1-6 進場保護期停損解耦（grace ticks/sec + hard/vwap 分離）                                                                                                                                                             |
| 2026-06-10 | P4-9 kbars 當日抓取 + `api.usage()`；P2-7 `uat_report.py`                                                                                                                                                               |
| 2026-06-10 | P0-9 `DUMP_ORDER_EVENTS` + P0-10 `_require_futopt_account` 落地                                                                                                                                                         |
| 2026-06-10 | 整合 [Code Review #1](docs/CodeReview%231.md)：P0-9/10、P1-6/7、P2-7/8、P4-8/9/10、坑十 VWAP 停損                                                                                                                       |
| 2026-06-10 | P0-3 peak 首 tick 校準；P0-8 trading_day 文件化；P2-1 部分成交防禦；P4-1 重連同步                                                                                                                                       |
| 2026-06-15 | **P0-11 落地**：`tick_archiver` / `compress_tick_cache`；code review 收尾（interval flush、排程器預設排除當日）；UAT gate 解除                                                                                          |
| 2026-06-12 | **P0-11** UAT 非同步 tick 落盤列為 UAT hard gate；回測改 UAT 累積、不批量下載歷史                                                                                                                                       |
| 2026-06-12 | P0-11：盤中 plain CSV；gzip 改 rotate / 排程器壓縮（不盤中 streaming gzip）                                                                                                                                             |
| 2026-06-12 | **整合 [Code Review #2](docs/CodeReview%232.md)**：新增 Phase 6 策略真實化（P6-1～P6-5）；明確區分 UAT Ready vs Live Ready                                                                                              |
| 2026-06-12 | Phase 6：P6-1 趨勢濾網（P0）/ P6-2 ATR Trailing / P6-3 ATR VWAP 停損（P1）/ P6-4 風險口數（P2）/ P6-5 追價進場（P3）；P1-4 併入 P6-2/3                                                                                  |
| 2026-06-15 | **整合 [Code Review #3](docs/CodeReview%233.md)**：四點 Live blocker 盤點（1/3部分/4 已落地）；新增 **P4-11 下單異常分類與降級風控** + **P4-12 session 看門狗（退避重登）** 為 Live hard gate；含「>5s 無回報」降級政策 |
| 2026-06-15 | **新增 P6-6 生存指標**（期望值 / 最大回撤 / 夏普）為 Live 前 Go/No-Go 績效閘門；盤點現況（expectancy 半套、MDD / Sharpe 完全缺）；規劃納入 `uat_report` + `param_sweep` 風險調整排序                                    |
| 2026-06-15 | P6-6 補 **摩擦成本參數**（`friction:` 區塊）：round-trip 費稅可設定；gross / net 雙軌 KPI；與 MockBroker 滑價分離                                                                                                       |
| 2026-06-15 | **落地 P6-6 / P4-11 / P4-12 / P4-3 / P4-4 / P6-1～3 骨架 / kbars 落盤**；review fix：告警非同步、MDD 跨日串接、P6-1 高時框參數；`python run_tests.py` **133** 項全綠                                                    |
| 2026-06-16 | **Phase 7 Strategy Interface**：`Strategy` Protocol + 建構子注入；移除 `VWAPMomentumStrategy=TradingEngine` 別名；`BacktestEngine.host` 命名；CR 收尾；**139** 項全綠                                                   |
| 2026-06-16 | **P6-1 Level 2 雙 Code Review**（策略 + 量化）；commits `a66b183`→`3573ef7`→`1773fbc`→`31881ca`；新增 **P6-1-CAL 校準工作流**（明確標 **非 UAT Blocker**；Live 開旗標 gate）                                         |
| 2026-06-16 | **P6-1-CAL A-class 1-5 完成**（code+test+docs，分支+ CQR persona 直接 review 後 commit）：CAL-1 交易所時間切片（select helper + 真 regression guard + 移除 400 magic）；CAL-2 harness（條件期望值，synthetic + 正確 forward math + 強制 SYNTHETIC GUARD）；CAL-3 sweep 納入 trend 參數 + 報表 veto_metrics；CAL-4/5 命名誠實化 + BackTestingSpec SOP（accumulate→harness→sweep→Go/No-Go）。全數 synthetic 驗證，155 tests OK，flags 永遠 false，無 live/simulation 變更。後續 B-class 待 UAT tick 才跑真實 delta。 |
| 2026-06-16 | **Follow-up code review fixes** (`d127f50`)：CAL-3 sweep key 正規化 + engine runtime `_config` TREND_* + SIGNAL_AUDIT harvest → `veto_metrics`；`Any` import；移除 `default_window`；`.github/workflows/ci.yml` 入庫。155 tests 全綠。 |
| 2026-06-16 | **`feat/p6-1-cal-3-sweep-trend` merge → `main`**（fast-forward）；P6-1 Level 2 + CAL A-class 基建完成；旗標仍關；B-class 待 API。 |
| 2026-06-16 | **文件同步**（post-merge）：TODO 狀態表（155 tests、CAL A 類完成）、WeeklyStatus 頂節（merge `main` + `d127f50`）、AGENTS/CI 現況、docs/README + BackTestingSpec + BackTesting.md 基線 155；`.cursor`/`.grok` 測試基線。 |

### Phase 7 — Strategy Interface & Extensibility (for open source)
- [x] Introduce `strategy.base.Strategy` Protocol + `BaseStrategy` ABC (exact signature from existing evaluate call site).
- [x] Move `StrategySideEffects` to `core/types.py`.
- [x] Inject pluggable strategy into `TradingEngine` (runtime) and `BacktestEngine`.
- [x] Adapt `strategy.vwap_momentum.VWAPMomentumStrategy` as the first (and current default) implementation.
- [x] Update `strategy/__init__.py`, test_helpers, and add injection tests.
- [x] Preserve 100% of prior behavior for the VWAP strategy; all tests and CLIs continue to work.
- [x] Remove `runtime.engine.VWAPMomentumStrategy` host alias (engine is `TradingEngine`, strategy is `strategy.vwap_momentum.VWAPMomentumStrategy`).
- [x] Widen Strategy Protocol / decouple host from VWAP-specific API (`.momentum`, `reset_momentum`, `manage_exit`, audit builders) so non-VWAP strategies survive a tick.
- [x] Align `reset()` vs `reset_momentum()` host call sites with the Protocol.
- [x] CR follow-up: test host naming (`make_host`), public audit builders, doc sync.
- Next: more example strategies, richer MarketContext if needed, possible dynamic plugin loading.

**命名約定（Phase 7 後）**

| 符號                                          | 角色                                            |
| --------------------------------------------- | ----------------------------------------------- |
| `TradingEngine`                               | 執行宿主（狀態機、下單、session、indicators）   |
| `BacktestEngine.host`                         | 回測中的同一宿主                                |
| `strategy=` 建構子參數                        | 決策 plugin（`Strategy` / `BaseStrategy` 子類） |
| `host.strategy`                               | 宿主上已注入的 plugin 實例                      |
| `strategy.vwap_momentum.VWAPMomentumStrategy` | 預設 VWAP 決策實作                              |

See `src/strategy/base.py`. Host = `runtime.TradingEngine` / `backtest.BacktestEngine.host`; decision logic = `strategy.*` plugins.
