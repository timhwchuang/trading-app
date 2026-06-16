# 外部 Code Review #2 — 策略升級評估（2026-06-12）

> 主題：工程體質已達 UAT 標準，但「交易邏輯」仍是 prototype。本輪聚焦進出場邏輯放進真實戰場的存活力，而非系統穩定性。
> 摘要與待辦對應見 [`TODO.md`](../TODO.md) 的「外部 Code Review #2」章節與 Phase 6。

---

## 結論

- 程式品質（工程面）：**8.5 / 10**
- UAT Ready：**是**
- 進正式盤前，至少補上：
  - 趨勢 Filter（P0）
  - ATR 動態 Trailing（P1）
  - ATR 動態 VWAP Stop（P1）
- 這三項對績效改善的影響，遠大於 Position Sizing。

> 補上趨勢濾網 + ATR 動態 trailing / VWAP 停損後，這其實已經是**新策略**，不是修策略。

---

## 潛在問題 / 改進建議（原文）

### 1. 進場訊號可能偏晚或偏保守

必須同時滿足「量能衰竭 + 靠近 VWAP」，在強勢趨勢中可能錯過很大一段行情。

建議可以考慮分批進場（例如第一筆嚴格條件，第二筆放寬），或增加「如果 momentum 持續強勢，允許追價」的備選邏輯。

### 2. Position Sizing 太簡單

目前固定 1 口。建議至少做到根據 ATR 或帳戶權益的波動調整口數（例如 1% 風險法則）。

### 3. Trailing Stop 與 Grace Period 的平衡

`EXIT_GRACE_TICKS` + `EXIT_GRACE_SEC` 保護期內只看硬停損，設計很好。

但 trailing stop 的 `TRAIL_POINTS` 如果設太緊，可能在震盪中容易被掃；設太鬆又失去保護。建議可以做成 ATR 倍數動態 trailing。

### 4. VWAP Stop 的適應性

目前是固定 `VWAP_STOP_POINTS`，在不同波動環境下意義不同。建議改成 `current_vwap ± ATR * k` 會更合理。

### 5. 缺少趨勢過濾

目前純粹靠短期 momentum + pullback，在大趨勢反轉或盤整行情中容易連續止損。

建議加入更高時間框架（例如 5 分或 15 分）的趨勢判斷（EMA、Supertrend、price slope / linreg 等）作為 filter。

---

## 三大核心診斷

### 進場條件過於嚴苛（量能衰竭 + 靠近 VWAP）

進場訊號必須同時滿足 `near_vwap` 與 `exhausted`（`vol_1s <= EXHAUSTION_VOL`）。本意是做「安全的回踩拉回」，但在極端強勢的單邊趨勢中，市場根本不會給這種完美的量縮回踩。量能會持續高企，結果策略只能眼睜睜看著大行情噴出，與大波段無緣。

### 靜態停損與移動止盈（未與 ATR 連動）

代碼引入了固定的 `HARD_STOP_POINTS`、`VWAP_STOP_POINTS` 和 `TRAIL_POINTS`。妙的是，明明寫了 `refresh_atr()`，還拿它來計算量能門檻（`_vol_threshold`），卻沒有把 ATR 運用在價格停損上。固定點數在波動劇烈時極易被掃單，在波動平淡時又會給予市場太多利潤回撤。

### 缺乏大週期趨勢濾網（Macro Blindness）

策略的微觀量能只看 1 秒鐘窗口（`vol_1s`）。這種極短線動能很容易在大級別盤整盤中被來回雙巴。若沒有大週期（例如 5 分鐘或 15 分鐘的均線或 VWAP 斜率）來定義當天的「主趨勢」，策略很容易在沒有趨勢的市場裡頻繁停損。

---

## Reviewer 優先級

| 優先級 | 項目 | 說明 |
| ------ | ---- | ---- |
| P0 | Trend Filter | 5m EMA 或 price slope (linreg) |
| P1 | ATR Trailing | `TRAIL_POINTS → ATR * k` |
| P1 | ATR VWAP Stop | `VWAP_STOP_POINTS → ATR * k` |
| P2 | Position Sizing | Risk Based |
| P3 | 第二套追價進場 | Trend Entry |

---

## 待辦對應

| Reviewer | TODO ID | 詳見 |
| -------- | ------- | ---- |
| P0 Trend Filter | P6-1 | [`TODO.md`](../TODO.md) Phase 6 |
| P1 ATR Trailing | P6-2 | 同上 |
| P1 ATR VWAP Stop | P6-3 | 同上 |
| P2 Position Sizing | P6-4 | 同上（前置 P2-1 部分成交） |
| P3 Trend Entry | P6-5 | 同上 |
