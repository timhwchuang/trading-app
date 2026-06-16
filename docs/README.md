# 文件索引

> 工程規格以 [`TODO.md`](../TODO.md) 為準；每週進度見 [`WeeklyStatus.md`](WeeklyStatus.md)。
>
> **AI / Cursor / Grok 請先讀**：[`../AGENTS.md`](../AGENTS.md)（**§2 安全護欄優先**）；Cursor 另見 [`.cursor/rules/`](../.cursor/rules/)；Grok 見 [`.grok/settings.json`](../.grok/settings.json)。

| 文件                                                       | 用途                                       |
| ---------------------------------------------------------- | ------------------------------------------ |
| [`../AGENTS.md`](../AGENTS.md)                             | **AI 主規範**（架構、gate、文件紀律、runbook） |
| [`.cursor/rules/`](../.cursor/rules/)                      | Cursor `alwaysApply` 規則                  |
| [`.grok/settings.json`](../.grok/settings.json)            | Grok 專案 instructions 摘要                |
| [`BackTesting.md`](BackTesting.md)                         | 回測哲學、同構性、專案結構、Phase 進度     |
| [`BackTestingSpec.md`](BackTestingSpec.md)                 | 回測可執行規格（Phase 2-7 驗收）           |
| [`AuditContract.md`](AuditContract.md)                     | SIGNAL/FILL/DAILY_SUMMARY log 契約         |
| [`UATReminder.md`](UATReminder.md)                         | UAT 第一天檢查清單                         |
| [`BeforePilot.md`](BeforePilot.md)                         | UAT → Pilot 觀測項與實操守則               |
| [`WindowsOps.md`](WindowsOps.md)                           | Windows 部署、告警、排程                   |
| [`CALLBACK_GUARDRAILS.md`](CALLBACK_GUARDRAILS.md)         | Shioaji callback 執行緒守則                |
| [`CodeReview#1`～`#3`](.)                                  | 歷史 code review（含重構前 `man.py` 行號） |
| [`CodeReview#BackTesting.md`](CodeReview%23BackTesting.md) | 回測專項 review（歷史）                    |

## 現行架構速查（2026-06-16）

- **執行宿主**：`src/runtime/engine.py` → `TradingEngine`
- **回測**：`src/backtest/engine.py` → `BacktestEngine.host`
- **決策 plugin**：`src/strategy/`（預設 `VWAPMomentumStrategy`）
- **契約**：`src/strategy/base.py` → `Strategy` / `BaseStrategy`
- **測試**：`python run_tests.py`（139 項）；mock 宿主 `tests/test_helpers.make_host()`
