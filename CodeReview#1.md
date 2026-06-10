一、架構評價（整體：可上線體質）
做得好的部分（不是客套，這些是實戰最常翻車而你已經防住的）：

Lock 邊界乾淨：api.* 網路呼叫全在 lock 外（place_order、update_status、order_deal_records、sync_positions），lock 內只做狀態讀寫與 signal 組裝。_arm_pending 在 lock 內堵雙單。這是多數人做不對的地方。
非同步 log（QueueHandler+QueueListener，且 callback 路徑用 put_nowait 丟棄不阻塞）— 開盤 tick 暴雨時不會卡 callback 執行緒。
交易所時間統一（tick.datetime 驅動所有時段判斷與 cooldown），time.time() 只用於背景超時。正確。
pending 狀態機：order id 綁定、超時補查、部分成交防禦（解鎖改以券商對帳為準）、重連後 pending補查→對帳→subscribe→ATR 的順序都對。
需要改進的架構點：

測試直接 new sj.Shioaji()（32 tests 跑 12 秒）。每個 test 建立真實 Shioaji client（初始化 Rust core），慢且有隱性外部依賴。建議把 self.api 改為可注入（建構子接受 api，預設才 new），測試傳 mock。這也讓你能寫「收到偽造 deal 回報 → 狀態正確」的測試，而那正是目前覆蓋最弱、實戰最致命的一塊。

futopt_account 可能是 None（_core.pyi 標 Optional[Account]）。若該登入帳號沒開期貨戶或未簽署，place_order(account=None) 會在第一筆單才爆。login() 應在對帳前 assert：


man.py
Lines 9-14
# 建議在 login() sync_positions() 之前加：
# if self.api.futopt_account is None:
#     raise RuntimeError("無期貨帳號，請確認帳號已開通期貨並完成簽署")
缺 no-tick / 心跳看門狗：目前只防「斷線事件」(event 12/13/session_down)。但實務上更常見的是連線還在、tick 卻停了（Solace 靜默、訂閱掉了但無事件）。在交易時段內若 N 秒沒收到 tick，應告警甚至嘗試重訂閱。這個 TODO 沒有，建議補（見下方 TODO 建議）。
二、Shioaji API 使用正確性
逐一對照 _core.pyi。大部分正確（FuturesOrder 參數、place_order(timeout=0)、update_status(trade=)、order_deal_records()、kbars、list_positions、各 callback 簽名、QuoteType.Tick、enum 與字串比較都 OK；tick.close 是 str 你也正確 float() 轉了）。

但有兩個必須在 UAT 第一天驗證的點：

⚠️ A. 委託回報 status 子欄位可能讀不到（最重要）
_handle_futures_order 這兩行：


man.py
Lines 774-774
        status = msg.get("status", {}).get("status", "")

man.py
Lines 800-800
            deal_qty = msg.get("status", {}).get("deal_quantity", 0)
但這版 Shioaji 的型別 stub 裡，FuturesOrderEvent.status（EventOrderStatusDict）只有：


_core.pyi
Lines 1538-1544
class EventOrderStatusDict(TypedDict):
    id: str
    exchange_ts: float
    modified_price: float
    cancel_quantity: int
    order_quantity: int
    web_id: str
沒有 status 也沒有 deal_quantity。如果實際 runtime dict 真的照這個 schema，那你的 status 永遠是 ""、deal_qty 永遠是 0，委託回報的成交/取消判斷會默默退化（目前還能動，是因為你靠 operation.op_type/op_code 判斷取消、靠 FuturesDeal 事件抓成交）。但這是「看起來在跑、其實有條件分支從沒生效」的隱患。

→ UAT 動作：冒煙測試時，在 handle_order_event 開頭把原始 stat、msg 完整 dump 一次（logger.info("RAW_ORDER_EVT %s | keys=%s | %r", stat, list(msg.keys()), dict(msg))），確認 FuturesOrder 與 FuturesDeal 兩種事件的真實欄位名。確認後再決定是否簡化這段邏輯。這是進 Pilot 前的 hard gate。

⚠️ B. ATR 其實是「20 分鐘 ATR」，且每 5 分鐘抓 10 天 1 分 K
refresh_atr 用 api.kbars 預設粒度是 1 分 K。所以：

ATR_PERIOD=20 → 取最後 20 根 = 最近 20 分鐘的 TR 平均，不是 20 天。min_atr_threshold=25 是「20 分鐘 ATR ≥ 25 點」才交易。這個語意要確認是不是你要的（我猜是，當作日內波動濾鏡合理），但 config 註解寫「ATR 計算週期（K 線根數）」容易讓人誤會。
每 atr_refresh_sec=300 秒就抓 10 天的 1 分 K（約 2000-3000 根），一整天下來重複抓幾十次。Shioaji 有流量/位元組上限（UsageOut.limit_bytes），這是潛在的 rate/quota 風險。lookback=10天 只有「開盤第一根」需要（P1-1 的初衷），盤中其實只需要當日資料。建議：盤中改抓當日、或快取昨日 K 只增量更新；至少 UAT 期間用 api.usage() 看一下用量。
其他小事（非錯誤）：login(subscribe_trade=True) 已訂閱委託回報，非模擬路徑又呼叫一次 subscribe_trade（冗餘無害）；activate_ca 某些券商設定需要 person_id，憑證啟用若失敗先試帶 person_id。

三、交易策略實戰可行性
工程沒問題，但策略邏輯有兩個結構性問題，會直接決定你 Pilot 是賺是賠：

🔴 1. 有效停損可能只有 ~3 點（最該擔心的）
進場是「動量突破後、價格拉回到 VWAP 附近 ~2 點才進場」。所以進場時 price ≈ current_vwap ≈ entry_price。但停損是：


man.py
Lines 635-635
            sl_hit = price <= self.entry_price - 6 or price <= self.current_vwap - 3
多單在 vwap - 3 與 entry - 6 取先觸發者。因為你剛在 VWAP 附近進場，vwap - 3 ≈ entry - 3，比 entry - 6 更近 → 實際停損約 3 點就出場。台指期單一 tick 跳 2-3 點是家常便飯，加上你進場 IOC 讓價 ±3，等於 TODO 裡自己警告的「進場即秒停損」結構，只是兇手從「開盤放大 IOC」換成了「VWAP-3 停損」。

這跟你 TODO 坑〈進場滑價 vs 停損〉的數學是同一個陷阱，但目前 review 沒覆蓋到 current_vwap 這條停損與「在 VWAP 進場」的交互作用。Pilot 前務必量化：UAT 統計「進場後 5 秒內因 stop_loss 出場」的比例，若偏高，要嘛放寬 vwap 停損（如 vwap - 6），要嘛把進場帶拉離 VWAP。

🟠 2. 進場條件可能太嚴 → 幾乎不進場 + 邏輯自相矛盾
進場要同時滿足：拉回到 VWAP ±~2 點 且 vol_1s <= 15（量能枯竭），且在動量觸發後 180 秒內。問題：

強動量行情下，價格常常不會回到 5 分 VWAP（VWAP 落後），於是你錯過主升段；
真的回到 VWAP 時，往往代表動量正在轉弱 —— 你是在「動量訊號」後做「均值回歸進場」，方向假設未必一致。
這不是 bug，是策略設計取捨，但實戰預期是進場次數很少，且容易選到動量衰竭的一方。UAT 不要因為「一整天沒幾筆」就以為壞掉 —— 這是設計使然。建議 UAT 用 SIGNAL_AUDIT 統計「動量觸發數 vs 實際進場數」轉換率，作為之後校準依據。

其他策略觀察（次要）
dynamic_threshold = max(2.0, vwap * 0.0001)：台指 ~20000 → vwap*0.0001 ≈ 2，所以這個動態項幾乎是無效的、永遠 2 點。確認是不是想寫 0.001（≈20點），否則那行可以直接寫死 2.0，少個誤導。
命名：這裡的「VWAP」是 5 分鐘滾動 VWMA，不是日內錨定 VWAP。滾動的 VWAP 會跟著價格快速移動，導致 vwap-3 停損也跟著漂 —— 進一步加劇上面第 1 點。心裡要清楚。
daily_pnl 是毛點數，沒扣手續費/稅/滑價。當風控閘門 OK，但別把它當真實損益。
R:R：SL ~3-6 / 固定 TP 20 / 移動停利 8，比例上 TP 給得夠。但若第 1 點的秒停損率高，期望值會被小虧的高頻率吃掉。
四、TODO 建議
你的 TODO 已經很完整，我補幾個目前沒有、但實戰會用到的項目，並按優先級排：

進 UAT 立刻加（blocker 級）

[P0-9] UAT 第一天 dump 原始 order/deal 回報 dict：驗證 FuturesOrder/FuturesDeal 真實欄位名（對應上面 API 隱患 A）。這是「確認狀態機真的有效」的前提，比任何壓力測試都優先。
[P0-10] futopt_account None 防呆：login 後、下單前 assert。
[P2-7] 量化秒停損率：UAT 報表新增「進場→出場 < 5s 且 reason=stop_loss」筆數與比例（對應策略風險 1）。這是 Pilot 通過/打掉的硬指標。
Pilot 前

[P4-8] No-tick 看門狗：交易時段內 N 秒無 tick → 告警 + 嘗試重訂閱（補你目前只靠斷線事件的盲區）。
[P4-9] kbars 流量控管：盤中 ATR 不再抓 10 天 1 分 K；加 api.usage() 監控（對應 API 隱患 B）。
[P1-6] VWAP 停損與進場帶的交互校準：把 vwap-3 與「在 VWAP 進場」一起重新設計，可能與 P1-4（SL/TP 掛 ATR）合併做。
可選

把 dynamic_threshold 的 0.0001 確認/修正。
策略測試引入 mock api（架構點 1），補「偽造 deal 事件驅動狀態機」的測試。
五、進憑證 / UAT 的最小檢查清單
UAT 第一天先做 P0-9 dump 回報，確認回報欄位 → 再相信狀態機。
連跑數日，用 SIGNAL_AUDIT 統計：動量觸發數、進場轉換率、秒停損率、IOC 成交率。
確認 futopt_account 不為 None、api.usage() 用量在限額內。
以上都過，再申請 CA、simulation: false、固定 1 口，只看不調參。
要不要我直接幫你動手把這幾項落地？我建議從風險最低、收益最高的開始：

futopt_account None 防呆（P0-10）
handle_order_event 的原始回報 dump（P0-9，可用 DEBUG 等級）
這兩個不改交易邏輯、純防呆與觀測，最適合 UAT 前先進。策略類（VWAP 停損、進場帶）我建議先 UAT 收數據再改，不要憑空調。你說要哪些我就改。