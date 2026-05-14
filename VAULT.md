# Tennis Betting Bot — Session Context

## Project
Async Python bot that monitors live ATP/WTA matches via Tennis API WebSocket and Kalshi prediction markets. Sends Telegram alerts for two rules. Runs on a Linux VM via `sudo systemctl restart tennisbot`.

## Rules
| Rule | Entry | Exit |
|------|-------|------|
| R2 Spike Fade | YES ask drops ≥12¢ in one tick, price 20–75¢ | +10¢ TP / -8¢ SL / 15min time exit |
| R3 Back Fav | Lost set 1, now set 2 ≤4 games, price 35–75¢, price dropped | Set 2 ended (current_set>2) / double break / 9min time exit |

## Key Files
| File | Role |
|------|------|
| `main.py` | Wires everything. R2 fires on Kalshi WS callback. R3 fires on Tennis WS callback. Periodic 30s loop for time-exits and R2 LOG. |
| `rules.py` | `check_entry_r2/r3`, `check_exit_r2`, `fmt_point_score`, `compact_score` |
| `state.py` | State machine per (id, player): WATCHING→IN_POSITION→WATCHING_REENTRY |
| `state_r2.py` | `R2Tracker` — entry snapshot, per-point ticks (deduped on Tennis state), exit snapshot, post-exit ticks, LOG data |
| `state_r3.py` | `R3Tracker` — tracks breaks in set 2, time exit, entry/exit snapshots |
| `modules/kalshi/ws_client.py` | `KalshiWSCache` — WS feed, 6s snapshot drain, fires `on_price_move` callbacks on ≥0.5¢ moves. Falls back to cached `no_ask` when WS message omits it. |
| `modules/kalshi/client.py` | RSA-PSS signed REST client |
| `modules/tennis_api/client.py` | Tennis WS client, stale-tick guards (games backwards + current_set backwards) |
| `modules/tennis_api/parser.py` | Parses Tennis API JSON → `MatchState` |
| `modules/telegram/bot.py` | `send_signal`, `send_log_r2`, `send_heartbeat`, `send_error` |
| `modules/telegram/messages/alerts.py` | Message formatters: `Signal`, `log_r2_text`, `heartbeat_text` |
| `modules/bets/db.py` | SQLite trade log |
| `monitor_live.py` | Debug tool only. `python -u monitor_live.py "PlayerName"` — shows live Tennis + Kalshi state and R2/R3 evaluation per tick. |

## Architecture Flow
```
Tennis API WS  →  on_update(match)           →  R3 check  →  Telegram
Kalshi WS      →  on_price_move(mkt, prev)   →  R2 entry/exit  →  Telegram
30s loop       →  R2 time-exits + post-exit LOG collection
30s loop       →  R3 orphan exits (match ended with open position)
5min loop      →  state cleanup, stale match removal
```

## Constants (rules.py)
```python
_R2_DROP_MIN      = 0.12   # ≥12¢ single-tick drop to enter
_R2_PRICE_MIN     = 0.20
_R2_PRICE_MAX     = 0.75
_R2_HARD_STOP     = 0.08   # -8¢ stop loss
_R2_TAKE_PROFIT   = 0.10   # +10¢ take profit
_R2_MAX_OPEN_SECS = 900    # 15min time exit

_R3_PRICE_FLOOR     = 0.35
_R3_PRICE_CAP       = 0.75
_R3_MAX_SET2_GAMES  = 4    # enter within first 4 games of set 2
```

## Recent Fixes (2026-05-14)

### Kalshi WS replaces REST polling
- `ws_client.py` new: seeds markets via REST, then subscribes to WS ticker channel
- R2 entry/exit fires immediately on each price move (was: 30s REST poll)
- `no_ask` preserved from cache when WS omits `no_ask_dollars` (prevented negative spread / wrong mid)

### R2 LOG ticks: one per point played
- `state_r2.py`: dedup key `"set|game|point"` — records one tick per Tennis API state change, not one per Kalshi WS wiggle
- Entry/exit detection unchanged — still fires on every WS tick

### fmt_point_score rewrite (rules.py)
- Fixed: API sends `"A"` for advantage, old code checked `"AD"` → BP never annotated
- Added: serving-aware BP (`returner at 40 or Ad`)
- Added: MP takes priority over BP
- Added: `is_tiebreak=True` → `"TB 5–3 [MP]"`, skips Deuce/BP logic
- `alerts.py`: game score `G 6-6` suppressed in LOG ticks when point_score starts with `"TB "`

### R3 false exit — "Set 2 won" firing seconds after entry
**Root cause**: Stale Tennis API messages (`current_set=1` delayed) arrived after set 2 started. Parser added set-2 game data to `completed_sets`, making `set_score(2)` non-None prematurely → false "Set 2 won" exit.
- `client.py`: drop updates where `state.current_set < prev.current_set`
- `state_r3.py`: only trust "Set 2 ended" when `match.current_set > 2`

## Watchpoints
- `spread=-Xc` occasionally in monitor: `no_ask` stale vs current `yes_ask`. Mid off by ~1c, not critical.
- R3 checks both players each Tennis update — only one can have lost set 1, so at most one entry fires per match.
- Kalshi WS `_SNAPSHOT_WINDOW = 6.0s` — initial price burst drained silently; callbacks only fire after.
- R3 exit `"Set 2 ended"` only triggers when `current_set > 2` — never during set 2 itself.
