# trading-app

> **Reference integrator app** for TXF VWAP momentum on Windows — wires `trading-engine`, `trading-backtest`, and `strategy-vwap-momentum` into a runnable deployment with config, storage, reporting, and UAT tooling.

> **目標執行環境：Windows**（開發、UAT、Pilot 皆以 Windows 為準。）

| 文件 | 用途 |
|------|------|
| [SPEC.md](SPEC.md) | App 層邊界、依賴方向、公開 wiring API |
| [docs/UATReminder.md](docs/UATReminder.md) | UAT 驗收步驟 |
| [docs/Architecture.md](docs/Architecture.md) | 與三 sibling repo 的架構對照 |
| [CHANGELOG.md](CHANGELOG.md) | 版本變更 |

**Sibling packages** (pin for v0.1.0):

- [trading-engine](https://github.com/timhwchuang/trading-engine) `@ v0.2.0`
- [trading-backtest](https://github.com/timhwchuang/trading-backtest) `@ v0.1.0`
- [strategy-vwap-momentum](https://github.com/timhwchuang/strategy-vwap-momentum) `@ v0.1.0`

---

## 系統需求

- **Windows 10 / 11** 或 Windows Server
- **Python 3.11+**
- 永豐金 [Shioaji](https://sinotrade.github.io/) API 金鑰（模擬或正式）
- 系統時區建議 **(UTC+08:00) 台北**

---

## 安裝

```powershell
git clone https://github.com/timhwchuang/trading-app.git
cd trading-app
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

`requirements.txt` 已 pin 三個 sibling git tag。Monorepo 開發可改 `pip install -e ../trading-engine` 等。

---

## 環境變數（PowerShell）

```powershell
$env:SJ_API_KEY = "your_api_key"
$env:SJ_SEC_KEY = "your_secret_key"
$env:SJ_CA_PATH = "C:\certs\Sinopac.pfx"      # 正式下單
$env:SJ_CA_PASSWD = "your_ca_password"
$env:CONFIG_PATH = "C:\trading-app\config\config.yaml"
$env:LOG_FILE = "C:\logs\trading-app-uat.log"
$env:LOG_LEVEL = "INFO"
$env:TICK_ARCHIVE = "1"                         # UAT 建議開啟
```

---

## 執行

```powershell
.\.venv\Scripts\activate
cd src
python -m live
```

| 用途 | 指令 |
|------|------|
| Live / 模擬 | `python -m live` |
| 回測 | `python -m backtest --code TXFR1 --dates 2026-06-12` |
| UAT 報告 | `python -m reporting C:\logs\trading-app-uat.log` |
| 壓縮 tick | `python -m storage.compress` |

首次請確認 `config/config.yaml` 中 **`simulation: true`**。UAT 通過後再評估 Pilot。

---

## 專案結構

```
trading-app/
├── config/config.yaml       # 策略參數（非密鑰）
├── src/
│   ├── integrations/        # trading_app_engine_ports() 接線
│   ├── live/                # CLI 入口
│   ├── backtest/engine.py   # 薄 wrapper（注入 ports）
│   ├── storage/             # tick/kbar 落盤
│   ├── reporting/           # uat_report、績效指標
│   └── sweep/               # 參數研究
├── tests/                   # integration tests (~69)
├── pyproject.toml
└── requirements.txt
```

測試：`python run_tests.py`

---

## Disclaimer

本 repo 為個人研究與學習用途。**UAT-ready ≠ Live-ready**。實盤風險自負。上線前請閱讀 [trading-engine LIVE_SAFETY](https://github.com/timhwchuang/trading-engine/blob/main/docs/LIVE_SAFETY.md) 與 [UAT_CHECKLIST](https://github.com/timhwchuang/trading-engine/blob/main/docs/UAT_CHECKLIST.md)。