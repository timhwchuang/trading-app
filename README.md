# VWAP Momentum 策略（theman）

> **目標執行環境：Windows**（本專案以 Windows 桌面 / 伺服器為主要部署平台開發與 UAT。）

台指期 VWAP 動量策略，透過 [Shioaji](https://sinotrade.github.io/) 連接永豐金 API。參數見 `config.yaml`，密鑰僅走環境變數。

---

## 系統需求

- **Windows 10 / 11** 或 Windows Server
- **Python 3.10+**（建議 3.11+）
- 永豐金 Shioaji API 金鑰（模擬或正式）
- 系統時區建議設為 **(UTC+08:00) 台北**（策略邏輯以交易所時間為準，但 log 對帳較直覺）

---

## 安裝

### 1. 安裝 Shioaji（若尚未安裝）

PowerShell（系統管理員可選）：

```powershell
pip install shioaji
```

或使用官方安裝腳本：

```powershell
irm https://raw.githubusercontent.com/sinotrade/shioaji/main/install.ps1 | iex
```

### 2. 建立虛擬環境並安裝依賴

```powershell
cd C:\path\to\theman
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

---

## 環境變數（PowerShell）

```powershell
# 必填：API 金鑰
$env:SJ_API_KEY = "your_api_key"
$env:SJ_SEC_KEY = "your_secret_key"

# 正式下單時必填（模擬可略）
$env:SJ_CA_PATH = "C:\certs\Sinopac.pfx"
$env:SJ_CA_PASSWD = "your_ca_password"

# 可選：覆寫設定檔與日誌
$env:CONFIG_PATH = "C:\theman\config.yaml"
$env:LOG_FILE = "C:\logs\theman.log"
$env:LOG_LEVEL = "INFO"
```

若要開機後自動帶入，可寫入「系統內容 → 進階 → 環境變數」，或使用 `.ps1` 啟動腳本。

---

## 執行

```powershell
.\.venv\Scripts\activate
python man.py
```

首次請確認 `config.yaml` 中 `simulation: true`，通過 UAT 後再改為 `false`。

---

## 設定檔

| 檔案          | 說明                                             |
| ------------- | ------------------------------------------------ |
| `config.yaml` | 策略參數、交易時段、開盤量能階梯（**不含密鑰**） |
| `config.py`   | YAML 載入器；`man.py` 啟動時自動讀取             |

修改參數後**重啟程式**即可，無需改 `man.py`。

---

## Windows 運維備忘

| 項目         | 建議做法                                                                    |
| ------------ | --------------------------------------------------------------------------- |
| 開機自動啟動 | 工作排程器（Task Scheduler）或 [NSSM](https://nssm.cc/) 註冊為 Windows 服務 |
| 時間同步     | 設定 → 時間與語言 → **自動設定時間**；或 `w32tm /query /status` 確認 NTP    |
| 睡眠 / 更新  | 交易時段禁用睡眠；延後 Windows Update 自動重開機                            |
| 日誌目錄     | 預先建立 `C:\logs\`，並確認執行帳號有寫入權限                               |
| 防火牆       | 允許 Python / Shioaji 對外連線至券商 API                                    |

詳細上線清單見 [`TODO.md`](TODO.md) Phase 4。

---

## 專案文件

| 檔案                               | 內容                                       |
| ---------------------------------- | ------------------------------------------ |
| [`TODO.md`](TODO.md)               | 開發路線圖、實戰踩坑、UAT / Pilot 檢查清單 |
| [`UATReminder.md`](UATReminder.md) | Phase 0 驗收步驟與 log 證據                |

---

## 常見問題

**Q：可以在 Linux / macOS 上跑嗎？**
A：程式為跨平台 Python，但本專案文件與運維流程以 **Windows 為準**。若改在 Linux 部署，請自行對照 TODO 中 chrony / systemd 等 Linux 備註。

**Q：`LOG_FILE` 路徑怎麼寫？**
A：Windows 可用 `C:\logs\theman.log` 或 `C:/logs/theman.log`。

**Q：正式下單要注意什麼？**
A：`simulation: false`、設定 CA 憑證、Pilot 階段固定 1 口，先觀察 08:45-09:15 滑價與 Cancelled 率。
