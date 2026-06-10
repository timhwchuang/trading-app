_check_no_tick_watchdog 用 tick.datetime 判斷時段: 如果 tick 真的完全停了, _last_tick_exchange_dt 會凍結在最後一筆。剛好停在 13:45 後就不會觸發看門狗, 但盤中(最危險的時段)是會觸發的, 影響有限。可接受, UAT 觀察即可。

_maybe_warn_clock_skew 用 tick.datetime.timestamp(): naive datetime 會被當系統本地時區解讀。前提是部署機器在 Asia/Taipei。建議在 UATReminder 或部署文件明確要求機器時區 = 台北(否則 skew 會誤報且不影響策略, 因策略本就用 tick 時間)。

refresh_atr 仍每 300s 呼叫 _log_api_usage: usage() 本身也算一次 API 呼叫。量很小, 但 UAT 期間留意一下 usage() 自身的占比。