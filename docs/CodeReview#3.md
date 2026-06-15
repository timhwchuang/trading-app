# 外部 Code Review #3 — Live 前防護網盤點（2026-06-15）

> 主題：工程架構已達 production-grade，但「真槍實彈」環境中外部網路、券商 API、期交所搓合機制會成為敵對面。本輪聚焦 **UAT Ready ≠ Live Ready** 的剩餘缺口。
> 摘要與待辦對應見 [`TODO.md`](../TODO.md) 的「外部 Code Review #3」章節與 Phase 4（P4-11 / P4-12）。

---

## 一、令人驚豔的工程嚴謹度（頂尖 5% 的架構）

從純粹的軟體工程與系統設計角度來看，這份準備工作做得極其出色。在散戶程式交易圈中，絕大多數人的架構都屬於「玩具級」，而交出來的是「生產線級」（Production-grade）的架構。幾個亮點非常到位：

### 確定性驗證（Determinism Gate）

透過 SHA-256 雜湊來校驗回測與審計日誌，這在機構法人非常常見，能徹底杜絕前視偏差（Look-ahead bias）與狀態污染。

### 結構化觀測（Telemetry & Observability）

將 `SIGNAL_AUDIT` 與 `FILL_AUDIT` 輸出為單行 JSON，並搭配 UAT 腳本進行指標落盤與滑價分析。這讓系統在出問題時具備極高的可追溯性。

### 時間軸邊界（Exchange Time Context）

嚴格區分交易所時間、開盤衝擊窗與日曆日，精準繞開了期貨跨日、夜盤或日光節約時間常見的時間陷阱。

---

## 二、迎戰實盤，這份準備還缺少什麼？（致命盲點）

雖然代碼架構非常完美，但在「真槍實彈」的 live 環境中，外部網路、券商 API、以及期交所搓合機制會變成你的「敵對面」。目前這套系統要上實盤，還有以下幾個硬傷必須補足：

### 1. 斷線重啟後的「狀態恢復與倉位對帳」（Reconciliation）── 最核心的 Blocker

在實盤中，Windows 更新重啟、網路斷線、或是程式因為未捕獲的異常崩潰是必然會發生的。

**盲點**：如果程式在盤中 10:30 崩潰並重啟，你的 `man.py` 如何知道現在帳戶裡有沒有部位？

**解法**：系統啟動時，不能預設起始狀態是 Position = 0。必須在初始化時呼叫 `api.list_positions()` 向永豐後台對帳。如果發現後台持有一口多單，程式必須能自動將狀態機重建為「持有多單、重新計算硬停損與移動停利線」的狀態。否則，13:45 的強制平倉機制（Flatten）將會失效，引發嚴重的留倉風險。

### 2. 下單 API 的異常捕獲（Exception Handling）

目前代碼在呼叫 `api.place_order` 時，預設了 API 一定會成功響應。

**盲點**：實盤中，當行情出現大震盪，永豐的 API Gateway 可能會回應 Timeout、Line busy、或是「憑證逾期 / 帳戶餘額不足」等異常。如果此時程式直接拋出 Exception 導致主執行緒崩潰，你的部位就會處於失控狀態。

**解法**：下單模組必須包覆在外層的 `try...except` 中，並針對不同類型的錯誤制定策略（例如：如果是網路逾期，是否要立刻進行重試，或者啟動 Line / Telegram 蜂鳴器進行人工介入）。

### 3. 斷線重連機制（Session Recovery）

你在 `man.py` 中註冊了 `set_session_down_callback`，這很好。

**盲點**：當觸發斷線時，你的程式只是留下了 log。但在實盤中，你需要的是自動重新登入（Auto Re-login）並重新訂閱（Re-subscribe）Tick 串流。

**解法**：必須設計一個看門狗（Watchdog）或在 Callback 中實作退避演算法（Exponential Backoff），在網路恢復時自動重新連線，並在重新連線後立即觸發上述第 1 點的「部位對帳」。

### 4. 複數口數（qty > 1）與「部分成交」（Partial Fills）

你在 `TODO.md` 中有提到 Phase 2-1 待補。

**盲點**：實盤下單（尤其是滑價控制使用 IOC 或市價單時），一口以上的委託極容易遇到「部分成交」。例如：你想買進 2 口，結果只成交 1 口，另外 1 口被取消。

**解法**：你的 `OrderProcessor` 或狀態機必須能處理 `OrderState` 傳回的殘餘張數。當收到部分成交回報時，觸發移動停利的計算基數必須動態調整，不能只做二分法（全部成交 vs 全未成交）的邏輯。

---

## 三、總結：UAT 階段的過關心態

💡 這份準備已經拿到了 90 分，但剩下的 10 分決定了真錢的生死。

你目前的代碼完全足以去跑永豐金的 UAT 自動審核（因為模擬環境不會有真的斷線、部分成交和系統崩潰）。建議你按照目前的節奏，先用這套代碼通過 UAT，拿到實盤憑證權限。

但在真正切換到實盤交易（Pilot 階段）的「第一天」之前，請務必把 **「斷線重連、盤中重啟狀態恢復、下單 Exception 捕獲」** 這三個保護網寫好。

---

## 四、Reviewer 直球問題：Pending 超時降級

> 在目前的 `man.py` 狀態機設計中，如果真的遇到 `api.place_order` 送出後超過 5 秒完全沒有收到任何回報（既非成交也非取消），你預期系統應該採取什麼樣的降級風控動作？

### 建議降級政策（已併入 P4-11）

1. `PENDING_TIMEOUT_SEC`（現 8s）觸發 → `_reconcile_pending_trade`（`update_status` / `order_deal_records` 補查，已落地 P0-4）。
2. 補查仍無結果 → 視為**鏈路可疑**（IOC 理論上應秒回；全無回報多半是網路 / API 斷，而非單還掛在簿上）：
   - `list_positions` **強制對帳**（以券商為真相，沿用 P0-3）。
   - 設 `block_new_entry`、**告警人工**。
   - 若對帳發現非預期裸倉 → 立即 `manage_exit` / flatten。
3. **鐵律**：寧可重複對帳，**不可假設「下單已失敗」**——order id 綁定（P0-5）+ `sync_positions` 防 ghost position 遲到成交。

---

## 五、本地盤點（2026-06-15）

> 將 reviewer 四點對照現行 `man.py` 後的結論。詳見 [`TODO.md`](../TODO.md)「外部 Code Review #3」。

| # | Reviewer 提出 | 現況（對應碼） | 結論 |
| - | ------------- | -------------- | ---- |
| 1 | 斷線重啟後狀態恢復與倉位對帳 | ✅ 已落地 P0-3：`login()` → `sync_positions()`（`man.py:282`）；首 tick `_calibrate_trailing_peak_after_resync`（`man.py:510`） | **已完成**，無新工 |
| 2 | 下單 API 異常捕獲 | ⚠️ 部分：`place_order` 已包 `try/except`（`man.py:1004-1036`），但扁平處理——無錯誤分類、無重試、無告警、entry/exit 一視同仁 | **真實缺口 → P4-11** |
| 3 | 斷線重連機制 | ⚠️ 大部分：event 12/13 + `_on_reconnected()`（`man.py:1406`）+ no-tick 看門狗（P4-8）。但僅依賴 Shioaji 內建重連；無主動重登入退避 | **真實缺口 → P4-12** |
| 4 | 複數口數與部分成交 | ✅ 防禦層已落地 P2-1：`pending_qty`、`deal_qty < expected` → `CRITICAL` + 解鎖 + `sync_positions`（`man.py:1162-1177`） | **已有防禦**，完整實作見 P2-1 / P6-4 |

### 本地評估摘要

- **這份 review 的價值不在「找到新 bug」，而在「驗收心態」**：模擬環境不會給你斷線、部分成交、API timeout，這些保護網在 UAT 不會被測到，卻是 Pilot 第一天的生死線。
- **多數點子工程面已防住**（P0-3 / P0-4 / P0-5 / P4-1 / P4-8 / P2-1），代表前面的迭代方向是對的。
- **兩個缺口確實該補**：①下單異常的「分類 + 降級」而非扁平 log（P4-11）；②session 永不恢復時的「主動重登入退避」（P4-12）。兩者都屬 **Live hard gate**，不阻擋 UAT。

---

## 待辦對應

| Reviewer | TODO ID | 詳見 |
| -------- | ------- | ---- |
| #1 Reconciliation | P0-3 ✅ | [`TODO.md`](../TODO.md) Phase 0 |
| #2 Exception Handling | P4-11 | [`TODO.md`](../TODO.md) Phase 4 |
| #3 Session Recovery | P4-12 | 同上（與 P4-1 / P4-3 連動） |
| #4 Partial Fills | P2-1 / P6-4 | [`TODO.md`](../TODO.md) Phase 2 / Phase 6 |
| Pending 超時降級政策 | P4-11 | 同上 |
