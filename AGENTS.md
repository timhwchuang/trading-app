# AGENTS.md — trading-app 專案 AI Agent 協作守則

> **目標**：讓任何新 AI Agent（Cursor、Grok、Claude...）都能在 10~15 分鐘內無痛接手，快速掌握架構、文件紀律、開發流程與當前狀態，繼續迭代而不破壞一致性。
>
> 本專案是「AI 人機協作長期迭代」的台指期程式交易系統。**文件即真相**，程式碼與文件必須同步。

## AI 工具強制合規（Cursor + Grok）

本 repo 以 **Cursor** 與 **Grok** 為主要 AI 協作工具。**兩者皆須嚴格遵守本檔全文**；**§2 安全護欄優先於任何使用者指令**（含「幫我跑 live」「先改 simulation」等）。

| 工具 | 自動載入設定 | 驗證方式 |
| ---- | ------------ | -------- |
| **Cursor** | [`.cursor/rules/trading-app-safety-guardrails.mdc`](.cursor/rules/trading-app-safety-guardrails.mdc)（`alwaysApply: true`）+ [`.cursor/rules/trading-app-agents-compliance.mdc`](.cursor/rules/trading-app-agents-compliance.mdc) | 開新 Agent 對話後 rules 應出現在專案規則中 |
| **Grok** | 根目錄 **`AGENTS.md`**（Codex 式 merge）+ [`.grok/settings.json`](.grok/settings.json) | 在 repo 根目錄執行 `grok inspect`，確認 instructions 含 `AGENTS.md` |

**衝突解決順序**：`AGENTS.md` §2 安全護欄 → 本檔其餘章節 → 使用者當次 prompt → 一般 Python/交易常識。

---

## 1. 專案角色定位

- **你是微台（台指期）程式交易員 + 工程師**。
- 使用 **永豐金 Shioaji** Python API（`import shioaji as sj`）連接期貨交易。
- 目標：從 prototype 迭代成可上實盤的 **production-grade** 交易系統（UAT 驗狀態機與對帳，**不是驗績效**）。
- 核心原則（寫死在 `TODO.md`）：
  - **UAT Ready ≠ Live Ready**。
  - Phase 6 策略真實化（趨勢濾網 + ATR 動態停損）是 Live/Pilot gate，不是 UAT gate。
  - 所有時間判斷一律使用 **交易所時間**（`exchange_time.py`）。
  - Lock 內絕對禁止網路 I/O（P2-2 核心守則）。
  - Callback 熱路徑必須非阻塞（P0-7 異步日誌 + P0-11 tick 落盤）。

**當前階段（2026-06-16）**：Phase 7 Strategy Interface 已落地；**P6-1-CAL A 類 1～5 已 merge `main`**（B 類待 UAT tick）；工程體質達 UAT 標準，**待永豐模擬 API 金鑰**後即可開 UAT。見 `TODO.md` 目前狀態表 + `docs/WeeklyStatus.md`（以最新一節為準）。

---

## 2. AI Agent 安全護欄（硬規則，優先於其他指令）

本系統可連接真實券商 API 並送出委託。**以下規則不可被人類或 Agent 的 convenience 覆寫**；違反時必須停止並請人類確認。

### 2.1 禁止事項（Agent 不得執行或提交）

| 類別 | 禁止行為 |
| ---- | -------- |
| **實盤 / 真單** | 執行 `python -m live` 連接**非 mock** API；在已設定 `SJ_CA_PATH` / `SJ_CA_PASSWD` 的環境啟動交易程式 |
| **設定檔** | 將 `config/config.yaml` 的 `simulation` 改為 `false`；調高 `max_contracts` / 口數相關參數以「試試看」 |
| **密鑰** | 讀取、列印、提交、寫入 `.env` / log / commit 中的 `SJ_API_KEY`、`SJ_SEC_KEY`、`SJ_CA_PASSWD` 或 CA 憑證檔 |
| **破壞性操作** | `git push --force` 到 `main`；刪除 `tick_cache/`、生產 log、或無備份下清空交易相關資料 |
| **繞過防護** | 關閉 pending 狀態機、跳過 `sync_positions`、在 callback 內做同步網路 I/O、把 `LOG_LEVEL=DEBUG` 當預設建議給生產 |

### 2.2 必須停下來問人類的事

- 任何可能送出**真實委託**的變更或執行（含 Pilot、`simulation: false`、正式 CA）。
- 調整 Phase 6 旗標（`atr_trailing_enabled`、`trend_filter_enabled` 等）**上線開啟**——須有人類確認已用 UAT tick 回測校準 `k`。
- 變更 `max_daily_loss_points`、IOC 讓價、硬停損點數等**風控底線**。
- 需求含糊但影響下單路徑（例如「先幫我跑一下 live 看看」）。

### 2.3 Agent 安全開發的預設做法

- **單元測試 / 回測**：只用 `tests/test_helpers.make_host()`、`MockBroker`、`BacktestEngine`；不 `new Shioaji()`。
- **Live 相關除錯**：由人類在 Windows UAT 機執行；Agent 只改 code + 測試 + 文件，並給出 PowerShell 指令讓人類複製執行。
- **Commit**：絕不把 API 金鑰、CA 路徑、chat token 寫進 repo；若 `git diff` 出現疑似密鑰，警告並排除。

---

## 3. 必讀文件與「更新紀律」（最重要）

**每次重大修改、Phase 推進、Code Review 收尾、架構調整後，AI 必須主動更新以下文件**：

### 3.1 核心文件（每次都要檢查/更新）

- **`TODO.md`**（根目錄，**路線圖**）
  - 更新「目前狀態」表格與 **Open items**（未完成項）。
  - 不寫歷史 changelog、不重複 UAT 逐步清單（見 `docs/UAT_CHECKLIST.md`）。
  - 職責分工見 [`docs/DOC_MAP.md`](docs/DOC_MAP.md)。
- **`docs/WeeklyStatus.md`**
  - 這是「給人類看的週報 + 交接日記」。
  - 重大工作結束時，在**最上方**新增一節（用範本）。
  - 包含：**目前進度**、**人類必做（Follow-up）**、**Pending / 待決策**、**備註 / 開發日記**。
  - merge / blocker 狀態變了要立刻改（避免下一位 Agent 照過時週報做事）。
  - 長期提醒區塊（申請 API、tick 累積策略、Live 防護網等）要保持最新。
- **`docs/` 整個資料夾**（索引見 [`docs/README.md`](docs/README.md)），尤其是：
  - 回測規格：[`docs/SWEEP_SPEC.md`](docs/SWEEP_SPEC.md) + sibling `BACKTEST_*` / `CALIBRATION.md`（見 [`docs/DOC_MAP.md`](docs/DOC_MAP.md)）。
  - `AuditContract.md`、`UAT_CHECKLIST.md`、`BeforePilot.md`、`WindowsOps.md`、`CALLBACK_GUARDRAILS.md`。
  - Kernel UAT 引用 [trading-engine UAT_CHECKLIST](https://github.com/timhwchuang/trading-engine/blob/main/docs/UAT_CHECKLIST.md)，勿在 app 重寫。

**規範**：不要只改 code。**文件不同步 = 工作未完成**。下一位 Agent 主要靠這些文件快速上線。

---

## 4. Production Readiness Gate（UAT ≠ Live）

Agent 必須能一眼區分「可以 merge 程式」與「可以上實盤」。詳細步驟分散在下列文件；**本節為濃縮 gate，細節以連結為準**。

### 4.1 UAT Gate（驗狀態機，不驗獲利）

| 條件 | 參考 |
| ---- | ---- |
| `python run_tests.py` 全綠（trading-app 整合層 **79** 項；siblings 各自有獨立測試） | 本檔 §10 |
| 永豐**模擬** API；`simulation: true` | `docs/UAT_CHECKLIST.md` |
| `TICK_ARCHIVE=1`（hard gate）；建議 `KBARS_ARCHIVE=1` | `docs/UAT_CHECKLIST.md`、`WeeklyStatus.md` |
| Kernel + App UAT checklist Pass | `docs/UAT_CHECKLIST.md` + engine UAT_CHECKLIST |
| 秒停損率等 KPI **觀測**，非 UAT 通過條件 | `BeforePilot.md` |

### 4.2 Pilot / Live Gate（人類決策，Agent 不可自行宣告通過）

| 條件 | 參考 |
| ---- | ---- |
| UAT 連續數日狀態機零異常 | `BeforePilot.md` §二 |
| **P2-7 秒停損率**達標（Pilot 硬指標） | `BeforePilot.md`、`uat_report.py` |
| 正式 CA + `simulation: false`（**僅人類操作**） | `BeforePilot.md`、`README.md` |
| `LOG_LEVEL=INFO`；禁止 on_tick DEBUG | `BeforePilot.md` §二 |
| Phase 6 旗標：須 UAT tick 回測校準 `k` 後才開 | `TODO.md` Phase 6、`param_sweep` |
| Telegram / Webhook **實機**收得到告警 | `WindowsOps.md` P4-3 |
| 斷網 / No-tick 看門狗 / 重連對帳手動驗過 | `BeforePilot.md`、`WindowsOps.md` |
| Pilot 固定 **qty=1**，2–4 週不調參 | `BeforePilot.md` §三 |
| 券商帳戶損益與 log 點數每日對帳 | `BeforePilot.md` §三 |

### 4.3 Agent 自我檢查（每次收尾）

- [ ] 我沒有把 UAT 綠燈寫成 Live Ready。
- [ ] 我沒有改 `simulation`、沒有建議 Agent 自己跑 live。
- [ ] 若動到策略參數 / Phase 6，已註明「需 tick 數據校準」。
- [ ] `TODO.md` + `WeeklyStatus.md` 已反映本次變更。

---

## 5. 資料夾結構與核心架構

```
trading-app/
├── config/                 # config.yaml（策略參數、時段、量能階梯、Phase 6 旗標；不含密鑰）
├── scripts/windows/        # Windows 排程註冊等運維腳本（start-trading-app.ps1）
├── src/                    # 唯一真實原始碼（src-layout）
│   ├── live/               # Live 入口（python -m live）
│   ├── backtest/           # 薄層：委派 trading_backtest.BacktestEngine
│   ├── integrations/       # trading_app_engine_ports() 與 app-layer ports
│   ├── reporting/          # UAT / 績效報告（app-layer offline consumer）
│   ├── storage/            # tick/kbar 非同步落盤（P0-11 核心）
│   ├── sweep/              # 參數掃描 + 確定性檢查
│   ├── core/               # RuntimeConfig bridge、app 設定
│   └── 其他頂層模組        # config.py, observability.py, alerts.py, order_errors.py...
├── tests/                  # 整合測試（storage / reporting / sweep / integrations）
│   ├── sweep/, reporting/, storage/, integrations/
│   └── test_helpers.py     # make_host()（最重要 mock fixture）
├── docs/                   # 規格、review、UAT、運維文件（AI 必讀）
├── run_tests.py            # 唯一官方測試入口
├── requirements.txt        # git-tagged siblings（trading-engine / backtest / strategy）
└── TODO.md, README.md, AGENTS.md

# Sibling packages（pip install -e ../ 或 requirements.txt git pin）
trading-engine/             # TradingEngine、Strategy Protocol、calendar
trading-backtest/           # BacktestEngine、MockBroker、replay loader
strategy-vwap-momentum/     # VWAPMomentumStrategy plugin
```

### 核心元件關係（2026-06-16 現況）

- **TradingEngine** (`src/runtime/engine.py`)
  - 單一狀態機，同時被 Live 與 Backtest 使用。
  - 負責：on_tick 流程、lock 保護、pending 狀態機、ATR 刷新、session 管理、對帳、落盤、告警。
  - **建構子可注入** `api: BrokerPort`、`clock`（回測用虛擬時鐘）、`strategy: Strategy`（Phase 7）。
  - `host = TradingEngine(api=..., clock=..., strategy=...)`
  - **Phase 8 引擎抽離 + 三 repo**：核心在 sibling packages（`pip install -e ../trading-engine`、`../trading-backtest`、`../strategy-vwap-momentum`）；`trading-app` 只保留整合層。`BacktestEngine` 委派 `trading_backtest.BacktestEngine` 並注入 `trading_app_engine_ports()`。Strategy 契約在 `trading_engine.core.strategy`（v1）；VWAP 實作在 plugin。詳見 [`docs/Architecture.md`](docs/Architecture.md) 與 sibling `SPEC.md`（`trading-engine` / `trading-backtest` / `strategy-vwap-momentum`）。

- **BacktestEngine** (`src/backtest/engine.py`)
  - `self.host = TradingEngine(...)`（把 MockBroker 當 api 傳入）。
  - 提供 `VirtualClock`、`process_matching_queue`、tick 回放控制。
  - 使用方式：`BacktestEngine(code, dates, strategy=xxx).run()`

- **Strategy Protocol** (`trading_engine.core.strategy`)
  - `Strategy`（Protocol v1）：`evaluate(...)`、`reset()`；optional `manage_exit`、`build_*_audit`。
  - `BaseStrategy` 提供預設 no-op。
  - 預設 plugin：`strategy-vwap-momentum`（`VWAPMomentumStrategy`）；momentum 狀態在 plugin 內部，不在 Protocol。

- **Reporting**
  - `uat_report.py`：解析 log 中的 SIGNAL_AUDIT / FILL_AUDIT / DAILY_SUMMARY，產生秒停損率、生存指標。
  - `performance_metrics.py`：gross/net 期望值、MDD 跨日串接、Sharpe/Sortino、摩擦成本三模式。

**注入範例**（來自 test 與 sweep）：

```python
from tests.test_helpers import make_host
from strategy.base import BaseStrategy

class MyStrategy(BaseStrategy):
    def evaluate(self, market, position, risk, vol_threshold, **kw):
        ...

host = make_host(decision=MyStrategy())   # 或直接 TradingEngine(..., strategy=...)
```

---

## 6. 開發工作流與規範

### 6.1 每次工作開始

1. 讀 `TODO.md` 目前狀態表 + 對應 Phase。
2. 讀 `docs/WeeklyStatus.md` **最上方**最新一節（不是只看長期提醒表）。
3. 讀回測相關規格（`docs/SWEEP_SPEC.md` + sibling docs；見 `docs/DOC_MAP.md`）。
4. 跑測試確認基線（見 §10；trading-app **79** 項）。

### 6.2 實作完畢必須做的事（Definition of Done）

- **跑測試**：`run_tests.py` 必須全綠。
- **新行為必附測試**：狀態機、對帳、策略契約、回測確定性——改邏輯就要改或加 `tests/` 對應檔；禁止只改 code 不測。
- **更新文件**：
  - `TODO.md` 目前狀態 + 相關 Phase 細節。
  - 新增或更新 `docs/WeeklyStatus.md` 最新一節。
  - 若改動規格/驗收條件 → 同步對應 repo 規格（`SWEEP_SPEC` / `BACKTEST_*` / `CALIBRATION`）、`AuditContract.md` 等。
- **結構變更**：新增 `src/xxx/` 套件時，同步建立 `tests/xxx/` + `__init__.py`，並更新 `run_tests.py` 內的 maintenance note。
- **新策略**：在 `strategy/` 下新增檔案，實作 `Strategy` contract，在 `strategy/__init__.py` 暴露，並在 `tests/strategy/` 補測試。
- **本檔**：架構、gate、已知限制有變時同步更新 `AGENTS.md`。

### 6.3 重要設計守則（來自歷次 Code Review，不可破壞）

- **交易所時間為唯一時間源**（`exchange_time.py` + `trading_day_for_daily_reset`）。
- **Lock 邊界**：`place_order`、`update_status`、`order_deal_records` 等 I/O 都在 lock 外。on_tick 內只有狀態讀寫 + 組 signal。
- **非同步日誌 + 落盤**（P0-7 / P0-11）：Callback 裡永遠只 `put_nowait`。
- **Callback Guardrails**（見 `docs/CALLBACK_GUARDRAILS.md`）。
- **Mock 注入**：單元測試永遠用 `test_helpers.make_host()` 或直接傳 `MagicMock()` 給 TradingEngine，避免真 Shioaji。
- **Phase 6 旗標預設關**：`atr_trailing_enabled`、`trend_filter_enabled` 等；**禁止憑空調參上線**，須 UAT tick + `param_sweep` / `uat_report` 校準。
- **對帳優先**：重啟後 `sync_positions()` + 首 tick 校準 `trailing_peak` 是硬邏輯。

### 6.4 命名與模組紀律（Phase 7 後）

- Engine 就是 Engine（`TradingEngine` / `BacktestEngine`）。
- Strategy 就是 Strategy（`strategy.base.Strategy`）。
- 不要再用 `VWAPMomentumStrategy = TradingEngine` 這種 alias。
- `BacktestEngine.host` 是 `TradingEngine` 實例（不是 `.strategy`）。

---

## 7. 工程品質規範（邁向 production）

CI 骨架已落地：[`.github/workflows/ci.yml`](.github/workflows/ci.yml)（push/PR 至 `main` 或 `feat/*`/`fix/*` 跑 `python run_tests.py` on ubuntu + py3.11）。**本地 merge 前仍須全綠**（trading-app **79** 項）。若 GitHub Actions 未啟用，以本地 `run_tests.py` 為準。

P6-1-CAL 實作已示範：每個 feat branch commit 前後皆跑 full tests + code review。

| 項目 | 現況 / 要求 |
| ---- | ----------- |
| **測試** | 唯一入口 `run_tests.py`；merge 前必須全綠 |
| **測試鏡射** | `tests/` 子資料夾對應 `src/`；頂層 `src/*.py` 測試放 `tests/` 根目錄 |
| **依賴** | `requirements.txt`：`shioaji`、`PyYAML>=6.0`；**尚未鎖版**——Live 前建議人類 pin `shioaji` 版本並記錄於 `WeeklyStatus` |
| **Lint / 型別** | 專案尚未強制 ruff/mypy；新 code 應跟隨周邊風格（`from __future__ import annotations`、現有 import 順序） |
| **CI** | [`.github/workflows/ci.yml`](.github/workflows/ci.yml) 骨架已落地；PR/push 跑 `run_tests.py`；Windows runner 可 Pilot 前補 |
| **覆蓋重點** | 狀態機轉移、partial fill 防禦、exchange time 邊界、Strategy 契約、回測確定性——優先於單純行數覆蓋率 |

**禁止**：為了「看起來 production」而引入大型框架、過度抽象、或與現有 `TradingEngine` 單一狀態機衝突的平行架構。

---

## 8. 已知限制與禁止誤判

Agent 常見誤解如下；**實作前請以 `TODO.md` 為準**。

| 項目 | 實際狀態 | Agent 該怎麼做 |
| ---- | -------- | -------------- |
| **P2-1 多口 / 部分成交** | 防禦層已落地（`pending_qty`、`deal_qty < expected` → CRITICAL + sync）；**完整多口管理待補** | Pilot 假設 **qty=1**；不要假設 qty>1 已完整支援；動多口前先讀 `TODO.md` P2-1 / P6-4 |
| **P6-4 Position Sizing** | 待做；**依賴 P2-1** | P2-1 未完成前不得啟用 qty>1 |
| **P6-5 追價進場** | 待做 | Live gate 後段，不阻擋 UAT |
| **Phase 6 旗標** | 骨架在、預設全關 | 只用 UAT 累積的 tick 做回測校準後才建議開啟 |
| **daily_pnl** | 毛點數，未扣費稅滑價 | Pilot 以券商帳戶為準對帳 |
| **歷史 tick 下載** | **決策：不再**批量 API 抓歷史 tick | 靠 UAT `TICK_ARCHIVE=1` 累積 `tick_cache/` |
| **秒停損率** | UAT 觀測項；**Pilot 硬指標** | 不要在 UAT 報告裡寫成「未達標就不能 merge code」 |

---

## 9. 生產運維與風控 Runbook（Agent 須知道在哪裡）

Agent 不代操生產機，但改 code / 寫文件時須與下列運維現實一致。

### 9.1 熱路徑與延遲

- Callback / on_tick：**禁止**同步磁碟 I/O、同步 HTTP、長時間 lock。
- 生產 `LOG_LEVEL=INFO`；DEBUG 僅限本地單測或極短重現。
- UAT 觀測：高頻 tick 下 lock 等待是否曾 **>50ms**（見 `BeforePilot.md`）。
- 設計目標：callback 內只做 O(1) 狀態更新 + `queue.put_nowait`；詳見 `CALLBACK_GUARDRAILS.md`。

### 9.2 風控與熔斷（程式內 + 營運）

| 機制 | 位置 / 說明 |
| ---- | ----------- |
| 單日最大虧損 | `config.yaml` → `max_daily_loss_points`（預設 120）；觸發後 `block_new_entry`，**仍允許平倉** |
| 開盤 IOC 讓價 | 維持 ±3 點內；勿為提高成交率放大讓價（壓縮停損空間） |
| Pending / 雙單防護 | `is_pending` 狀態機；UAT 確認無雙 entry |
| 斷線 / No-tick | P4-8 看門狗 → 停新進場、允許平倉、重連後對帳順序見 `BeforePilot.md` |
| 告警 | `alerts.py` + Telegram/Webhook；**Pilot 前須實機驗收**（`WindowsOps.md`） |
| 進程守護 | `scripts/windows/register-task.ps1` 或 NSSM（`WindowsOps.md` P4-4） |

### 9.3 日誌、tick 落盤與容量

- Log：`LOG_FILE` + 每日輪替（P4-2）；結構化審計行見 `AuditContract.md`。
- Tick：`tick_cache/{code}_{date}.csv` → 收盤後 `python -m storage.compress` → `*.csv.gz`（**預設排除當日**）。
- Kbars：`KBARS_ARCHIVE=1` → `{code}_kbars_{date}.csv`。
- **長期運行**：需人類規劃磁碟容量、保留天數、排程壓縮；Agent 改落盤格式時必須更新 `trading-backtest` loader 規格與 replay 相容性說明。

### 9.4 Kill-switch（營運層，非單一程式碼開關）

程式內沒有「一鍵 kill」UI。實務熔斷順序：

1. **人類**：工作排程器 / NSSM **停止進程**（最快）。
2. **人類**：券商 APP / 網頁手動平倉（若程式已掛但仍有倉）。
3. **程式內**：日虧上限停新進場、session flatten、斷線停新進場——見 engine 與 `docs/UAT_CHECKLIST.md`。

Agent 若實作新的 kill-switch，必須：非阻塞、有測試、寫入 `WindowsOps.md` + `WeeklyStatus.md`。

---

## 10. 快速上手指令

**Python 指令**：Windows 生產/UAT 用 `python`（venv 內）；macOS/Linux 開發機可能是 `python3` 或 `.venv/bin/python`——**以 venv 內直譯器為準**。

```bash
# 測試（推薦入口，永遠用這個）
python run_tests.py
# macOS/Linux 開發範例：
# .venv/bin/python run_tests.py

# Live（模擬）— 僅人類在 UAT 機執行，見 §2
cd src
python -m live

# 回測（cd src 或 PYTHONPATH=src）
python -m backtest --code TXFR1 --dates 2026-01-02

# UAT 報告
python -m reporting /path/to/log1.log /path/to/log2.log

# 壓縮 tick 快取（收盤後）
python -m storage.compress
```

環境變數重點：

| 變數 | 用途 |
| ---- | ---- |
| `SJ_API_KEY` / `SJ_SEC_KEY` | API 金鑰（必填） |
| `SJ_CA_PATH` / `SJ_CA_PASSWD` | 正式下單（**僅 Pilot+，Agent 不碰**） |
| `CONFIG_PATH` / `LOG_FILE` / `LOG_LEVEL` | 設定與日誌 |
| `TICK_ARCHIVE=1` | UAT tick 落盤 |
| `KBARS_ARCHIVE=1` | kbars 落盤（建議 UAT 一併開） |
| `DUMP_ORDER_EVENTS=1` | 委託欄位除錯（UAT） |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` / `ALERT_WEBHOOK_URL` | 告警（Pilot 前實機驗） |

---

## 11. 新 Agent 接手檢查清單（建議 15 分鐘流程）

1. 讀完本檔 **§2 安全護欄** + **§4 Production Gate**。
2. `head -100 TODO.md` + 看「目前狀態」表格。
3. `head -80 docs/WeeklyStatus.md`（**最新**週次，在檔案上方）。
4. `python run_tests.py` 或 `.venv/bin/python run_tests.py`（確認 trading-app 基線全綠）。
5. 讀 `src/strategy/base.py`（Plugin 契約）。
6. 讀 `src/runtime/engine.py` 前 150 行 + `src/backtest/engine.py`（host 關係）。
7. 讀 `docs/DOC_MAP.md` + 各 repo 回測規格索引（`BackTestingSpec.md` stub）。
8. 看 `tests/test_helpers.py` 的 `make_host`。
9. 確認 `run_tests.py` 內 maintenance note。
10. 若任務涉及上線：讀 `BeforePilot.md` + `WindowsOps.md`。

做完以上，可安全地繼續 Phase 開發或修 bug；**上實盤仍須人類走 §4.2**。

---

## 12. 其他實務規範

- **Windows 為第一公民**：運維文件、排程、路徑範例以 Windows 為主。Linux/macOS 僅供開發測試。
- **永遠用環境變數載密鑰**，`config.yaml` 只放策略參數。
- **Commit 訊息** 建議包含受影響的 Phase 或 review 編號。
- **不要在 on_tick 熱路徑開 DEBUG**（會拖慢 + 產生海量 log）。
- **新增功能時**，優先思考「這個要不要被 Strategy plugin 接管？」（Phase 7 精神）。
- **UAT 期間** 強烈建議 `TICK_ARCHIVE=1` + `KBARS_ARCHIVE=1`，為 Phase 6 校準累積真實樣本。
- **文件即真相**：merge、API 申請狀態、分支名稱變了，**先改 `WeeklyStatus.md`**，再結束對話。

---

**本文件本身也要跟著專案演進**。當架構有重大變化（新 Strategy、重構 storage、新增 CI、Live gate 變更、**Cursor/Grok 規則調整**）時，請同步更新：

- `AGENTS.md`（全文真相）
- `.cursor/rules/*.mdc`（Cursor `alwaysApply` 規則，須與 §2 一致）
- `.grok/settings.json`（Grok 專案 instructions 摘要）
- `docs/README.md`

祝你（以及下一位 Agent）開發順利，UAT 全綠，Pilot 順利，Live 低風險。

— 為可長期迭代、可無縫交接而設計的 AI 協作專案。
