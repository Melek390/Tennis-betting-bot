# Tennis Betting Bot — Project Notes

## Client's Original Strategy Rules

These are the rules as specified by the client. Always restore to these values as the baseline before any testing tweaks.

| Rule | Entry Conditions | Price Cap | Exit Condition |
|------|-----------------|-----------|----------------|
| 1 | Player has a match point | ≤ 75¢ | Match point lost |
| 2 | Leads 1-0 in sets + ≥2 game lead in current set | ≤ 65¢ | Game lead drops below 2 |
| 3 | Sets tied 1-1 + ≥2 game lead in deciding set | ≤ 62¢ | Game lead drops below 2 |
| 4 | Won set 1 by ≥2 games + ≥1 game lead in set 2 | ≤ 58¢ | Game lead in set 2 gone |

Price caps live in `rules.py` → `_PRICE_CAP` dict. To test with looser params, change that dict and revert when done.

## Architecture

- `main.py` — entry point, wires all modules together
- `rules.py` — all 4 entry/exit conditions + `rule_detail()` for alert text
- `state.py` — state machine per (match_id, player, rule): WATCHING → PENDING_ENTRY → IN_POSITION → PENDING_EXIT → WATCHING_REENTRY → PENDING_REENTRY
- `modules/tennis_api/` — WebSocket client (wss://wss.api-tennis.com/live)
- `modules/kalshi/` — RSA-PSS signed API client, per-player market price lookup
- `modules/telegram/` — bot, handlers, keyboards, alert messages

## Signal Flow

1. WebSocket update → `_process_update()` → `state.process()` returns "entry"/"exit"/"reentry"/None
2. "entry" → Telegram alert with [Confirmed entry] [I'm skipping this] buttons
3. User confirms → state moves to IN_POSITION → bot scans for exit condition
4. Exit found → alert with [Confirmed exit] [Keeping my position]
5. User confirms exit → state moves to WATCHING_REENTRY → bot scans for re-entry
6. Re-entry found → alert with [Confirmed re-entry] [I'm skipping this]

Multiple rules can be active simultaneously for the same match — each (match_id, player, rule) is tracked independently.

## Credentials (.env)

```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
TENNIS_API_KEY=...
KALSHI_KEY_ID=...
KALSHI_PRIVATE_KEY_PATH=kalshi_private.pem
```

Kalshi uses RSA-PSS auth — private key must be a PEM file at `KALSHI_PRIVATE_KEY_PATH`.
