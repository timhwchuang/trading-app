# Shioaji Callback 執行緒安全守則（P2-6）

`on_tick` 與 `handle_order_event` 來自**不同執行緒**。新增 callback 前必讀。

## 原則

1. **共享狀態**（`has_position`、`is_pending`、`daily_pnl`、`current_vwap` 等）讀寫必須在 `with self.lock` 內。
2. **禁止**在 callback 內呼叫 `api.*` 網路 I/O（`place_order`、`subscribe`、`kbars` 等）。
3. **禁止**在 callback 內 `join()`、`sleep`、同步磁碟 I/O。
4. **Log** 使用 `QueueHandler`（`put_nowait`）；callback 路徑禁止同步 `FileHandler`。

## Lock 不變式（誰能改什麼）

| 狀態 | 可修改處 |
| ---- | -------- |
| `has_position` / `entry_price` / `position_dir` | `_apply_deal_fill`、`sync_positions`、`_clear_pending`（lock 內） |
| `is_pending` / `pending_*` | `_arm_pending`、`_clear_pending`、`_handle_futures_order`、`_apply_deal_fill`（lock 內） |
| `daily_pnl` / `consecutive_loss` / `block_new_entry` | `_apply_deal_fill`、`_reset_daily_state`（lock 內） |
| `api.place_order` | **僅** `place_order()`，且在 lock **外** |
| `api.subscribe` / `refresh_atr` | 背景執行緒或 `_on_reconnected` / 看門狗，**不在** `on_tick` lock 內 |

## 網路 I/O 允許位置

- `login()`、`start()` 主執行緒
- `place_order()`（lock 外）
- `_reconcile_pending_trade` / `sync_positions`（由 lock 外呼叫）
- `_timeout_loop`、`_on_reconnected`、`_maybe_refresh_atr` 背景執行緒

## Code Review Checklist

- [ ] 新 callback 內有 `with self.lock` 包住狀態讀寫
- [ ] 新 callback 內無 `api.*`
- [ ] 新 log 走 async queue，非熱路徑逐 tick DEBUG
