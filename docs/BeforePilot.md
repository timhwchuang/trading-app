一、在 UAT 期間您可以重點觀測與審計的項目
在 UAT 跑模擬單時，您的重點不是看策略「賺不賺錢」，而是利用結構化 JSON 紀錄來觀測以下指標：

**每日必看三種 log 行（AI-friendly）**

| 行首 | 用途 |
|------|------|
| `SIGNAL_AUDIT {json}` | 進/出場決策當下：價格、VWAP、ATR、量能、reason |
| `FILL_AUDIT {json}` | 成交對帳：signal vs fill 滑價、hold_sec、pnl_points、exit_reason |
| `DAILY_SUMMARY {json}` | 收盤一行總結：當日 KPI + **參數快照** + near-miss + 營運指標 |

觀測指令：

```bash
# 單日完整報告（含調參提示）
cd src && python -m reporting /path/to/trading-app-uat.log

# JSON 輸出（餵給 AI）
cd src && python -m reporting /path/to/trading-app-uat.log --json

# 多日趨勢（合併輪替 log 或 grep DAILY_SUMMARY）
cd src && python -m reporting day1.log day2.log day3.log --trend
```

秒停損率與停損分布（進入 Pilot 的硬指標）

觀測重點： `DAILY_SUMMARY.quick_stop_loss` 或 `uat_report` 的秒停損率（預設 <5s）。

調整依據： `FILL_AUDIT` 的 `exit_reason` 分布 + `expectancy_by_reason`（各 reason 平均 PnL）。秒停損率高 → 微調 `exit_grace_ticks` / `exit_grace_sec` / `vwap_stop_points`；報告會自動給 rule-based 調參提示。

開盤 IOC 取消率與成交滑價（P2-5）

觀測重點： 統計開盤爆量期（08:45–09:15）產生的 intent_cancelled_open_session 機率。

把關標準： `FILL_AUDIT.slippage_pts`（adverse vs signal）進場中位數 < 2 點；`uat_report` 會輸出 median / p90。

防禦思維： 開盤漏單是預期內的保護機制，不是 Bug。UAT 期間若發現常漏單，千萬不要妥協去放大 IOC 讓價（保持在 ±3 點內），因為在固定 6 點硬停損下，放寬讓價等於自縮停損緩衝空間。

Lock 等待延遲與防雙單（P2-2）

觀測重點： 檢查日誌，確認在高頻 tick 衝擊下（如 08:45:01 或 09:00:01），執行緒鎖（Lock）的等待延遲是否曾 > 50ms。

把關標準： 確認在 is_pending 的狀態機保護下，絕對沒有出現過連續兩筆 entry 下單的「雙單交易」。

進場轉換率與 near-miss（動量→pullback 漏斗）

觀測重點： `DAILY_SUMMARY.near_miss` — `closest_vwap_distance`、`blocked_vwap_only` / `blocked_vol_only`、`momentum_timeout`。

調整依據： 轉換率低且 `closest_vwap_distance` 常 > `entry_band_points` → 放寬 `entry_band_points`；`blocked_vol_only` 高 → 考慮 `exhaustion_vol`。

tick_type 的推斷品質（P1-3 觀測項）

觀測重點： `DAILY_SUMMARY.operational.tick_type0_pct` 或日誌 `tick_type 分布` 行。

注意點： type0 佔比 >40% 時報告會提示 buy/sell ratio 推斷可能失真。

異常看門狗與斷線重連測試（P4-8 & P4-1）

觀測重點： 留意若長時間沒有 tick 時，No-tick 看門狗是否能正確噴出 No-tick 看門狗 | ... 嘗試重訂閱。

破壞性測試： 在 UAT 盤中手動斷網，驗證系統是否能依序觸發：API 連線中斷 → 停止新進場但允許平倉 → 重連後狀態同步完成（順序：pending補查 → 持倉對帳 → 重新訂閱 → ATR更新）。

二、從 UAT 跨入 Pilot（實盤）前的準備工作
當 UAT 累積數日且「狀態機零異常」、「每項都有 log 證據與對帳一致」後，跨入 Pilot 實盤前必須完成以下技術切換：

憑證與環境變數對調

向券商申請正式 CA 憑證，並於系統環境變數中設定 SJ_CA_PATH 與 SJ_CA_PASSWD。

將 `config/config.yaml` 內的環境參數改為 simulation: false。

日誌級別強制收緊（防範熱路徑阻塞）

實盤鐵律： 正式實盤時，嚴禁在 on_tick 熱路徑開啟 DEBUG 級別或進行逐 tick 寫入。

生產環境必須嚴格維持 LOG_LEVEL=INFO，依靠 P0-7 的 QueueHandler 非同步落盤，防止高頻交易時磁碟 I/O 造成 Callback 執行緒排隊引發延遲。

三、進入 Pilot（實盤初期）的實操守則
策略剛接觸真實市場流動性時，最容易暴露出模擬環境無法模擬的「滑價風險」與「帳戶異常」：

嚴格固定 1 口，維持 2–4 週「只看不用」

進入 Pilot 後，交易口數請鎖死在 qty=1。

即使前幾天連續虧損或大幅獲利，連續 2–4 週內絕對不調整任何參數。這段時間的唯一目標是收集實盤數據，審計 08:45–09:15 的真實滑價損耗與 intent_cancelled 的真實巴辣率。

實際損益對帳（點數 vs 真實金額）

UAT 報告中的 daily_pnl 通常是毛點數，未扣除真實的期交稅、手續費與交易所滑價。

進入 Pilot 後，每日收盤必須將策略 Log 產出的點數，與券商後台回報的真實帳戶損益進行對帳，計算出策略在實盤下的「摩擦成本基線」。

保留部分成交的敏銳度（未來項 P2-1）

雖然在 Pilot 階段因為只做 1 口，不會觸發「部分成交（Partial Fills）」的問題。但請在對帳時持續觀察 Log 內 pending_qty 狀態機的變化，確保未來若放大口數至 2 口以上時，部分成交的追蹤邏輯不會卡死狀態機。

這套系統的防禦設計（非同步 Log、Lock外網路I/O、交易所時間驅動）在架構上非常紮實。只要在 UAT 嚴格落實 uat_report.py 的指標審計，確認秒停損率達標，即可信心十足地掛上憑證開跑 Pilot！