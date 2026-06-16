# Weekly Status — 人機協作開發日記

> 給**人類**看的進度、Follow-up、待決策。工程路線圖見 [`TODO.md`](../TODO.md)；文件職責見 [`DOC_MAP.md`](DOC_MAP.md)。  
> **歷史週報**（2026-06-12～06-16）→ [`ARCHIVE/weekly-status-2026.md`](ARCHIVE/weekly-status-2026.md)

**用法**：重大決策時在下方新增一節（最新放最上面）。

---

## 範本（複製用）

```markdown
### YYYY-MM-DD（週次 / 標題一句話）

**目前進度**
- 

**人類必做（Follow-up）**
- [ ] 

**Pending / 待決策**
- 

**備註 / 開發日記**
- 
```

---

## 長期提醒（跨週有效）

| 項目 | 說明 |
| ---- | ---- |
| **申請永豐 API** | 目前 **0 權限**。模擬 UAT：行情 + 帳務 + 交易（不需 CA）。 |
| **UAT 累積 tick** | 不再批量下載歷史；`TICK_ARCHIVE=1` 每日落盤 → `tick_cache/`。 |
| **KBARS_ARCHIVE** | 建議 UAT 一併開啟，供 ATR / 趨勢回測熱身。 |
| **Phase 3 UAT** | 可開跑（待 API）→ [`UAT_CHECKLIST.md`](UAT_CHECKLIST.md) + [engine UAT](https://github.com/timhwchuang/trading-engine/blob/main/docs/UAT_CHECKLIST.md) |
| **Phase 6 CAL B 類** | 待 UAT tick；見 [strategy CALIBRATION.md](https://github.com/timhwchuang/strategy-vwap-momentum/blob/main/docs/CALIBRATION.md) |
| **Pilot 門檻** | UAT 全過 + CA；秒停損率硬指標 → [`BeforePilot.md`](BeforePilot.md) |
| **三 repo** | `trading-engine@v0.2.0`、`trading-backtest@v0.1.1`、`strategy-vwap-momentum@v0.1.1`、`trading-app@v0.1.1` |

---

### 2026-06-16（文件重構完成 — WeeklyStatus archive + BackTestingSpec 拆分）

**目前進度**
- **WeeklyStatus**：舊節移至 [`ARCHIVE/weekly-status-2026.md`](ARCHIVE/weekly-status-2026.md)；本檔只保留範本 + 長期提醒 + 最新一節。
- **BackTestingSpec 拆分**：
  - Kernel 契約 → `trading-engine/docs/BACKTEST_HOST_CONTRACT.md`
  - 回放 / MockBroker → `trading-backtest/docs/BACKTEST_IMPLEMENTATION.md`
  - 策略校準 → `strategy-vwap-momentum/docs/CALIBRATION.md`
  - Sweep / 確定性 → `trading-app/docs/SWEEP_SPEC.md`
- **trading-app `BackTestingSpec.md`** → 僅剩索引 stub。

**人類必做（Follow-up）**
- [ ] 申請永豐模擬 API
- [ ] KEY 到手後跑 `docs/UAT_CHECKLIST.md` Phase A→E

**Pending / 待決策**
- B 類 P6-1-CAL 待 UAT tick 累積
- NDJSON 事件層待第一段乾淨 UAT 後

**備註**
- 歷史 CodeReview / Phase8 spec 已刪（GitHub 歷史）；`theman` 已自運維路徑清除。