# UAT 驗收提醒

> **執行環境：Windows**（PowerShell 啟動，見 [`README.md`](README.md)）。
> 通過標準：**每項有 log 證據 + 人工對帳一致**。驗的是狀態機，不是有沒有賺錢。
>
> 完整清單見 [`TODO.md`](TODO.md) Phase 3。以下按實作項目整理驗收要點。

---

## 啟動前檢查（模擬 UAT）

```powershell
cd C:\path\to\theman
.\.venv\Scripts\activate
$env:SJ_API_KEY = "your_api_key"
$env:SJ_SEC_KEY = "your_secret_key"
$env:LOG_FILE = "C:\logs\theman-uat.log"   # 建議開啟（P4-2 每日輪替）
# UAT 第一天：驗證委託回報欄位
$env:DUMP_ORDER_EVENTS = "1"
python man.py
```

- [ ] `config.yaml` 中 `simulation: true`
- [ ] 系統時區為台北 (UTC+8)
- [ ] log 出現 `VWAP Momentum 策略已啟動` 與 `ATR(...) 更新`
- [ ] log 出現 `API usage [login]`（P4-9 流量基線）

### UAT 第一天（必做）

1. `DUMP_ORDER_EVENTS=1` 跑一筆委託/成交 → 搜尋 `RAW_ORDER_EVT` 確認欄位名（P0-9）
2. 確認啟動無 `無期貨帳號` 錯誤（P0-10）
3. 收盤後：`python uat_report.py C:\logs\theman-uat.log`（P2-7）

---

## Phase 0 — 狀態機 Blocker

### P0-1 修正停利 / 停損邏輯

進場後價格持平 **不會** 秒出；固定 TP 20 點、Trailing 回落 8 點才出場。

- Log：`進場完成 | Long/Short @ 價格`；持平期間無 `(exit)` 下單

### P0-2 日虧上限仍須允許平倉

`daily_pnl <= -120` 後 `block_new_entry`，但持倉仍可 `manage_exit`。

- Log：`觸發單日最大虧損，停止新進場` → 仍可 `下單 ... (exit)` → `平倉完成`

### P0-3 啟動時持倉對帳

重啟後 `sync_positions()` 同步券商持倉；`trailing_peak` 首 tick 校準（多 `max(entry,tick)` / 空 `min(entry,tick)`）。

- Log：`持倉對帳 | ... | peak 待首 tick 校準` → `持倉 peak 校準 | ...`
- Log：`持倉對帳 | Long/Short N口 @ 均價` 或 `持倉對帳 | 無持倉`

### P0-4 Pending 超時與補查

IOC 未成交 / 回報遺失，8 秒後補查或解鎖。

- Log：`補查確認成交` / `補查確認委託未成交/已取消` / `Pending 超時 8s 且補查無結果`

### P0-5 成交回報綁定 order id

舊單遲到成交不影響當前狀態。

- Log：`忽略非當前委託成交回報 | expected=... got=...`

### P0-6 交易所時間統一

cooldown、開盤階梯、時段邊界皆用 `tick.datetime`，不受系統鐘漂移影響。

- 驗收：人為將系統鐘 offset ±2s，開盤階梯與 cooldown 行為不變
- 邊界：`08:44:59` 不交易；`08:45:00` 可交易；`13:45:00` 仍屬交易時段（擋新信號由 `SESSION_END` 控制）

### P0-8 日虧隔日重置

跨日運行後，新交易日 `daily_pnl` / `block_new_entry` / `consecutive_loss` 歸零。

- Log：`交易日切換 YYYY-MM-DD → YYYY-MM-DD，重置日內風控`

---

## Phase 1 — 訊號品質

### P1-1 ATR K 線回溯

週一 / 連假後開盤 ATR > 0。

- Log：`ATR(20) 更新: XX.XX | lookback=10 天`

### P1-2 開盤量能階梯

`08:45-09:00` 閾值 ×2.5；`09:00-09:15` ×1.5；`09:15` 後 ×1.0。

- Log：`MOMENTUM 量能通過 | dir=... vol_1s=... base=... mult=... threshold=...`
- 09:15 前後假訊號數應較固定 150 明顯下降

### P1-5 Signal Audit Log

每筆進出場 signal 一行 JSON，可事後還原濾鏡狀態。

- Log 格式：`SIGNAL_AUDIT {"intent":"entry","direction":"Buy","price":...,"ts":...,"vol_1s":...,"buy_ratio":...,"atr":...,"multiplier":...,"vol_threshold":...,"vwap":...,"reason":"pullback"}`
- 出場 reason：`stop_loss` / `take_profit` / `trailing_stop` / `session_force_flatten`
- 驗收：隨機抽 5 筆，人工可還原當下狀態

### P1-3 tick_type 分布（UAT 觀測）

開盤 30 分鐘統計 log 中 `Type:0/1/2` 比例（DEBUG 等級）；type 0 佔比高時留意 buy/sell ratio 品質。

---

## Phase 2 — 委託狀態機

### P2-3 收盤強制平倉

| 時間 | 行為 |
|------|------|
| `13:40` 前 | 正常進出場 |
| `13:40` 起 | 禁止新進場（無 entry signal） |
| `13:44` 起仍有倉 | aggressive IOC 強平（讓價 `flatten_slippage_points`，預設 8 點） |

- Log：`收盤強制平倉 | Long/Short @ 價格 | force_flatten_time=13:44`
- Audit：`"reason":"session_force_flatten"`
- 驗收：收盤前持倉必定清空，不留倉過夜

### P2-2 防雙單（觀測）

signal 產生後、下單前已在 lock 內設 `is_pending`，開盤高頻 tick 不應出現連續兩筆 entry 下單。

### IOC 未成交（開盤漏單，預期行為）

進場 IOC Cancelled 是保護機制，不是 bug。

- Log：`tag=intent_cancelled` 或 `tag=intent_cancelled_open_session`（08:45–09:15）
- **禁止**為提高成交率放大開盤 IOC 讓價

### P1-6 進場保護期停損

保護期內（60 tick 且 30 秒）僅硬停損 ±6；之後才啟用 VWAP 停損（audit `stop_loss_vwap`）。

- 驗收：進場後小幅震盪不應秒觸 `stop_loss_vwap`；`uat_report` 秒停損率應下降

### P4-8 No-tick 看門狗（觀測）

長時間無 tick：`No-tick 看門狗 | ... 嘗試重訂閱`

### P1-3 tick_type 分布（觀測）

每 30 分鐘：`tick_type 分布 | type0=... type1=...`

---

## Phase 3 快速對照表

| # | 項目 | 通過標準 |
|---|------|----------|
| 3.1 | 冒煙測試 | 登入、tick、進出場、pending 解鎖、不秒出 |
| 3.2 | 狀態機壓力 | P0-2/3/4/8、時段邊界、P2-3 收盤平倉 |
| 3.3 | 市況覆蓋 | 週一 ATR、雙開盤階梯、09:15 邊界 |
| 3.4 | 對帳 | 策略 log vs 券商成交；滑價；IOC 成交率 |

### P4-1 斷線重連（手動斷網驗證）

- 斷線：log `API 連線中斷` 或 `API 重連中`；期間無新進場，持倉仍可平倉
- 重連：log `重連後狀態同步完成`（順序：pending 補查 → 對帳 → subscribe → ATR）

### 尚未納入本次 UAT blocker（可後補）
- **P2-1** 部分成交（qty=1 暫不顯性）
- **P1-4** SL/TP 與 ATR 掛鉤（可選優化）

---

## 憑證與 Pilot 銜接

模擬 UAT 全過後，申請 CA 憑證完成再進 Pilot：

1. 設定 `SJ_CA_PATH` / `SJ_CA_PASSWD`
2. `config.yaml` → `simulation: false`
3. 固定 **1 口**，連續 2-4 週只觀察不調參
4. 重點審計 08:45-09:15 滑價與 `intent_cancelled` 率
