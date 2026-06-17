# 文件索引

> **路線圖**：[`TODO.md`](../TODO.md)（未完成項）｜**週報**：[`WeeklyStatus.md`](WeeklyStatus.md)｜**職責分工**：[`DOC_MAP.md`](DOC_MAP.md)  
> **AI 請先讀**：[`../AGENTS.md`](../AGENTS.md) §2 安全護欄

| 文件 | 用途 |
| ---- | ---- |
| [`../AGENTS.md`](../AGENTS.md) | AI 主規範（架構、gate、runbook） |
| [`DOC_MAP.md`](DOC_MAP.md) | **文件職責地圖**（避免 TODO / UAT / checklist 重疊） |
| [`UAT_CHECKLIST.md`](UAT_CHECKLIST.md) | **App 層 UAT**（Windows 部署、落盤、報表） |
| [`Architecture.md`](Architecture.md) | 四 repo 邊界 |
| [`AuditContract.md`](AuditContract.md) | SIGNAL/FILL/DAILY_SUMMARY log 契約 |
| [`BeforePilot.md`](BeforePilot.md) | UAT → Pilot gate |
| [`WindowsOps.md`](WindowsOps.md) | 排程、告警、NSSM |
| [`CALLBACK_GUARDRAILS.md`](CALLBACK_GUARDRAILS.md) | Shioaji callback 守則 |
| [`BackTesting.md`](BackTesting.md) | 回測哲學（高層） |
| [`SWEEP_SPEC.md`](SWEEP_SPEC.md) | 確定性 + param sweep（app 層） |
| `python -m reporting.calibration_cli` | P6-1 B 類：log + tick replay harness + `--sweep` |
| [`BackTestingSpec.md`](BackTestingSpec.md) | 索引 stub → 四 repo 規格 |
| [`ARCHIVE/`](ARCHIVE/) | 歷史週報、monolith `BackTestingSpec`（非現行真相） |
| [`UPGRADE_RUNBOOK.md`](UPGRADE_RUNBOOK.md) | **四 repo 升級 SOP**（pin 矩陣、tag 順序） |
| [`RELEASE_CHECKLIST.md`](RELEASE_CHECKLIST.md) | Tag 前檢查 |
| [`releases/`](releases/) | 版本說明 |

## Kernel / sibling 文件（勿在 app 重寫）

| Repo | 關鍵規格 |
| ---- | -------- |
| [trading-engine BACKTEST_HOST_CONTRACT](https://github.com/timhwchuang/trading-engine/blob/main/docs/BACKTEST_HOST_CONTRACT.md) | 回放宿主 API 契約 |
| [trading-engine UAT_CHECKLIST](https://github.com/timhwchuang/trading-engine/blob/main/docs/UAT_CHECKLIST.md) | 狀態機、重連、pending、flatten |
| [trading-engine LIVE_SAFETY](https://github.com/timhwchuang/trading-engine/blob/main/docs/LIVE_SAFETY.md) | 實盤護欄 |
| [trading-backtest BACKTEST_IMPLEMENTATION](https://github.com/timhwchuang/trading-backtest/blob/main/docs/BACKTEST_IMPLEMENTATION.md) | MockBroker、回放迴圈 |
| [strategy-vwap-momentum CALIBRATION](https://github.com/timhwchuang/strategy-vwap-momentum/blob/main/docs/CALIBRATION.md) | P6-1 趨勢校準 SOP |

## 現行架構速查（v0.1.2）

- **Host**：`trading-engine` → `TradingEngine`
- **Backtest**：`trading-backtest`；app `src/backtest/engine.py` 注入 ports
- **Strategy**：`strategy-vwap-momentum`
- **Wiring**：`trading_app_engine_ports()`
- **測試**：trading-app **81** 項；siblings 各自 `run_tests.py`