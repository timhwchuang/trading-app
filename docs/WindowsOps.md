# Windows 運維清單（P4-0 / P4-3 / P4-4）

> 目標執行環境：**Windows 10/11 或 Windows Server**。UAT / Pilot 皆以本清單驗收。

## P4-0 上線前檢查

- [ ] Python 3.10+ 已安裝；專案 venv 建立完成
- [ ] `.\.venv\Scripts\activate` 可啟動；`python run_tests.py` 全綠
- [ ] 系統時區 **台北 (UTC+8)**；自動對時已開啟（`w32tm /query /status`）
- [ ] 環境變數已設定（User 或 System）：
  - `SJ_API_KEY` / `SJ_SEC_KEY`
  - `LOG_FILE=C:\logs\trading-app-uat.log`
  - `TICK_ARCHIVE=1`（UAT 累積 tick）
  - `KBARS_ARCHIVE=1`（UAT 累積 kbars，供回測 ATR 熱身）
  - 選配：`TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` 或 `ALERT_WEBHOOK_URL`
- [ ] `C:\logs\` 目錄存在且執行帳號可寫入
- [ ] 交易時段電腦不睡眠；Windows Update 主動時段延後
- [ ] `config\config.yaml` 中 `simulation: true`（UAT）或 `false`（Pilot + CA）

## P4-3 告警通道

程式透過 `src/alerts.py` 發送 **best-effort** 告警（不阻塞 callback）：

| 環境變數 | 用途 |
| -------- | ---- |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot token |
| `TELEGRAM_CHAT_ID` | 目標 chat id |
| `ALERT_WEBHOOK_URL` | 通用 JSON webhook（body: `{text, level}`） |

觸發時機（已落地）：

- 出場下單重試耗盡（CRITICAL）
- Pending 超時無回報（entry / exit，CRITICAL）
- Session 重登入失敗 / 達上限（CRITICAL）
- 進場致命拒單（CRITICAL）

驗收：設定 Telegram 後，以 `tests/test_alerts.py` 或手動 `python -c "from alerts import send_alert; send_alert('test')"` 確認收到訊息。

## P4-4 進程守護

### 方案 A：工作排程器（建議 UAT）

```powershell
# 以系統管理員 PowerShell 執行
cd C:\trading-app
.\scripts\windows\register-task.ps1 -ProjectRoot C:\trading-app
```

- 開機觸發；失敗每 1 分鐘重試最多 3 次
- crash 後重啟走 P0-3 `sync_positions` 對帳

### 方案 B：NSSM 服務（Pilot 可選）

1. 下載 [NSSM](https://nssm.cc/) 並加入 PATH
2. `nssm install trading-app "C:\trading-app\.venv\Scripts\python.exe" "-m" "live"`
3. 設定 `AppDirectory=C:\trading-app\src`；Environment 加入 API keys

### 手動啟動（開發 / 除錯）

```powershell
.\scripts\windows\start-trading-app.ps1 -ProjectRoot C:\trading-app
```

## 收盤後維護

```powershell
# 壓縮昨日 tick（預設排除當日進行中檔）
cd src
.\.venv\Scripts\python.exe -m storage.compress
```

建議工作排程器每日 **15:30** 執行。

## 相關文件

- [`docs/UAT_CHECKLIST.md`](UAT_CHECKLIST.md)
- [`TODO.md`](../TODO.md) Phase 4
