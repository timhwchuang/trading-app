# trading-app UAT Checklist

> **執行環境：Windows**。驗的是**狀態機與對帳**，不是獲利。  
> **Kernel 場景**（重連、pending、flatten、audit）→ [trading-engine UAT_CHECKLIST](https://github.com/timhwchuang/trading-engine/blob/main/docs/UAT_CHECKLIST.md) Phase B/C。  
> **本檔**只涵蓋 app 部署、落盤、報表與銜接。

---

## Phase A — 部署與設定

| # | 項目 | Pass | 備註 |
|---|------|:----:|------|
| A1 | `pip install -r requirements.txt` 成功 | ☐ | pin `v0.2.2` / `v0.1.1` / `v0.1.2` |
| A2 | `python run_tests.py` 全綠（81 項） | ☐ | |
| A3 | `config/config.yaml` → `simulation: true` | ☐ | Agent 不得改 false |
| A4 | `SJ_API_KEY` / `SJ_SEC_KEY` 已設（模擬帳戶） | ☐ | 不 commit |
| A5 | 系統時區台北 UTC+8 | ☐ | |
| A6 | `LOG_FILE=C:\logs\trading-app-uat.log` | ☐ | 建議開啟 |

### 啟動指令

```powershell
cd C:\path\to\trading-app
.\.venv\Scripts\activate
$env:SJ_API_KEY = "your_api_key"
$env:SJ_SEC_KEY = "your_secret_key"
$env:LOG_FILE = "C:\logs\trading-app-uat.log"
$env:TICK_ARCHIVE = "1"
$env:KBARS_ARCHIVE = "1"
$env:DUMP_ORDER_EVENTS = "1"
cd src
python -m live
```

| # | 啟動後確認 | Pass |
|---|------------|:----:|
| A7 | log：`VWAP Momentum 策略已啟動` | ☐ |
| A8 | log：`ATR(...) 更新` | ☐ |
| A9 | log：`Tick 落盤已啟用`（`TICK_ARCHIVE=1`） | ☐ |
| A10 | 無 `無期貨帳號` 錯誤 | ☐ |

---

## Phase B — 第一個交易日（App 層必做）

| # | 項目 | Pass | 備註 |
|---|------|:----:|------|
| B1 | 盤中 `tick_cache/{code}_{date}.csv` 持續增長 | ☐ | 欄位與 live tick 一致 |
| B2 | `DUMP_ORDER_EVENTS=1` 有一筆 `RAW_ORDER_EVT` | ☐ | 確認券商欄位名 |
| B3 | 收盤後 `python -m storage.compress` → `*.csv.gz` 可重放 | ☐ | 預設排除當日 |
| B3b | 手動斷網 30–60s → 恢復：暖機期無 entry、有倉斷線有 CRITICAL 告警 | ☐ | P4-13；見 `LIVE_SAFETY.md` |
| B4 | `python -m reporting C:\logs\trading-app-uat.log` 有輸出 | ☐ | 秒停損率**觀測**，非 gate |
| B5 | 工作排程器（選配）：`register-task.ps1` 註冊成功 | ☐ | 見 `WindowsOps.md` |

收盤壓縮（建議 15:30）：

```powershell
cd C:\path\to\trading-app\src
..\.venv\Scripts\python.exe -m storage.compress
```

---

## Phase C — Kernel 整合驗收（引用 engine）

在 Phase A/B 完成後，逐項執行 [trading-engine UAT_CHECKLIST](https://github.com/timhwchuang/trading-engine/blob/main/docs/UAT_CHECKLIST.md)：

| Engine Phase | 重點 | App 注意 |
|--------------|------|----------|
| B1 | 全日 tick 進出場 | 用 `trading_app_engine_ports()` 接線 |
| B2 | Session flatten | `config.yaml` session 時段 |
| B3 | 斷線重連 | UAT 可手動斷網 |
| B4 | Pending 超時 | 測試 cfg 可縮短 timeout |
| B5 | 非法 signal 不 arm | engine 內建 |
| B6 | `get_state_snapshot` 與券商一致 | 重啟後對帳 |

Log 契約：`docs/AuditContract.md`（`SIGNAL_AUDIT` / `FILL_AUDIT` / `DAILY_SUMMARY`）。

---

## Phase D — 連續模擬（≥3 日）

| # | 項目 | Pass |
|---|------|:----:|
| D1 | 每日 log vs 券商成交明細一致 | ☐ |
| D2 | 無雙 entry（`is_pending` 有效） | ☐ |
| D3 | 收盤前持倉清空（session flatten） | ☐ |
| D4 | 跨日 `daily_pnl` / `block_new_entry` 重置 | ☐ |
| D5 | `tick_cache/` 累積可用於回測 | ☐ |

---

## Phase E — Sign-off

| 欄位 | 值 |
|------|-----|
| trading-app tag | v0.1.2 |
| trading-engine tag | v0.2.2 |
| UAT 負責人 | |
| 模擬交易日數 | |
| 問題紀錄 | |
| **結果** | ☐ Pass → 評估 Pilot &nbsp; ☐ Fail → 修復 |

Pilot 銜接：[`BeforePilot.md`](BeforePilot.md) + [`trading-engine LIVE_SAFETY`](https://github.com/timhwchuang/trading-engine/blob/main/docs/LIVE_SAFETY.md)。

---

## 附錄：常見 log 關鍵字（快速搜尋）

| 主題 | 搜尋 |
|------|------|
| 進場 | `進場完成`, `FILL_AUDIT` |
| 日虧熔斷 | `觸發單日最大虧損` |
| 對帳 | `持倉對帳` |
| Pending | `Pending 超時`, `補查確認` |
| 收盤平倉 | `收盤強制平倉`, `session_force_flatten` |
| 斷線 | `API 連線中斷`, `重連後狀態同步完成` |