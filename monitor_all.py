"""
Monitor ALL live matches with Kalshi coverage — R2 + R3 evaluation every tick.
Run: python -u monitor_all.py
"""
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

from modules.kalshi.client import KalshiClient
from modules.kalshi.models import KalshiMarket
from modules.kalshi.ws_client import KalshiWSCache
from modules.tennis_api.client import TennisAPIClient
from modules.tennis_api.models import MatchState
from rules import check_entry_r2, check_entry_r3, check_exit_r2, fmt_point_score

load_dotenv()
logging.basicConfig(level=logging.WARNING)
sys.stdout.reconfigure(line_buffering=True)

# ── simple in-memory position tracking ─────────────────────────────────
_r2_positions: dict[str, dict] = {}   # ticker → {entry_mid, entry_time}
_r3_positions: dict[str, dict] = {}   # "match_id:side" → {entry_mid}

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")

def _sep():
    print("-" * 60)

# ── Tennis callback ─────────────────────────────────────────────────────

def _on_tennis(match: MatchState, kalshi: KalshiWSCache) -> None:
    info1, info2 = kalshi.get_prices(match.first_player, match.second_player)
    if info1 is None and info2 is None:
        return  # no Kalshi market — skip

    score = fmt_point_score(
        match.point_score, match.serving,
        match.match_point_first, match.match_point_second,
        is_tiebreak=match.is_tiebreak,
    ).replace("–", "-")
    tb = " [TB]" if match.is_tiebreak else ""

    print(f"\n[{_now()}] TENNIS  {match.first_player} vs {match.second_player}"
          f" | S{match.sets_first}-{match.sets_second}"
          f" | G{match.games_first}-{match.games_second}{tb}"
          f" | {score} | {match.tournament}")

    for side, info in (("first", info1), ("second", info2)):
        if info is None:
            continue
        name   = match.player_name(side)
        price  = info.price
        prev_p = info.prev_price
        spread = info.spread if info.spread is not None else 0.0
        mid    = round(price - spread / 2, 4)
        key    = f"{match.match_id}:{side}"

        # ── R3 ──
        set1 = check_entry_r3(match, side, price, prev_p)
        if set1:
            if key not in _r3_positions:
                _r3_positions[key] = {"entry_mid": mid, "name": name}
                drop = round((prev_p - price) * 100) if prev_p else 0
                print(f"  ** R3 ENTRY  {name}  set1={set1}  drop={drop}c  ask={price:.2f}  mid={mid:.2f}")
            else:
                ep = _r3_positions[key]["entry_mid"]
                print(f"  OK R3 HOLD   {name}  entry={ep:.2f}  now={mid:.2f}  P&L={round((mid-ep)*100):+}c")
        else:
            if key in _r3_positions:
                ep = _r3_positions.pop(key)["entry_mid"]
                print(f"  XX R3 EXIT   {name}  P&L={round((mid-ep)*100):+}c")
            else:
                _r3_why_short(match, side, price, prev_p, name)

        # ── R2 (price-range + prev-price check only — drop checked on Kalshi tick) ──
        if _r2_positions.get(name):
            ep = _r2_positions[name]["entry_mid"]
            et = _r2_positions[name]["entry_time"]
            elapsed = (datetime.now(timezone.utc) - et).total_seconds()
            reason = check_exit_r2(mid, ep, elapsed)
            if reason:
                _r2_positions.pop(name)
                print(f"  XX R2 EXIT   {name}  {reason}  P&L={round((mid-ep)*100):+}c")
            else:
                print(f"  OK R2 HOLD   {name}  entry={ep:.2f}  now={mid:.2f}  P&L={round((mid-ep)*100):+}c  {int(elapsed)}s")


def _r3_why_short(match, side, price, prev_p, name):
    if prev_p is None:          reason = "no prev price"
    elif price >= prev_p:       reason = f"price not dropped ({prev_p:.2f}->{price:.2f})"
    elif price < 0.35:          reason = f"price {price:.2f} < floor 0.35"
    elif price > 0.75:          reason = f"price {price:.2f} > cap 0.75"
    elif match.current_set != 2: reason = f"set {match.current_set} (need set 2)"
    elif match.games_first + match.games_second > 4:
                                reason = f"G{match.games_first}-{match.games_second} too late in set 2"
    else:
        s1 = match.set_score(1)
        if s1 is None:          reason = "no set 1 data"
        elif s1.winner() == side: reason = "player won set 1"
        else:                   reason = "should fire?"
    print(f"  -- R3 skip   {name}: {reason}")


# ── Kalshi callback ─────────────────────────────────────────────────────

def _on_kalshi(market: KalshiMarket, prev_ya: float | None, live: dict) -> None:
    price  = market.yes_ask
    spread = market.spread
    mid    = round(price - spread / 2, 4)
    name   = market.title

    # Match this market to a Tennis match player name
    matched_name = None
    for match in live.values():
        i1, i2 = None, None
        for side in ("first", "second"):
            pname = match.player_name(side)
            import re
            last = pname.strip().split()[-1]
            if re.search(r"\b" + re.escape(last) + r"\b", market.title, re.IGNORECASE):
                matched_name = pname
                break
        if matched_name:
            break

    display = matched_name or name
    drop = round((prev_ya - price) * 100) if prev_ya else 0

    # R2 entry
    if check_entry_r2(price, prev_ya):
        if display not in _r2_positions:
            _r2_positions[display] = {"entry_mid": mid, "entry_time": datetime.now(timezone.utc)}
            print(f"\n[{_now()}] ** R2 ENTRY  {display}  drop={drop}c  ask={price:.2f}  mid={mid:.2f}  prev={prev_ya:.2f}")
    else:
        if drop >= 5:  # only log notable moves to keep output readable
            print(f"[{_now()}] KALSHI  {display}  ask={price:.2f}  drop={drop}c  spread={round(spread*100)}c"
                  + ("  <-- notable" if drop >= 8 else ""))


# ── Main ────────────────────────────────────────────────────────────────

async def main():
    tennis_key    = os.getenv("TENNIS_API_KEY", "")
    kalshi_key_id = os.getenv("KALSHI_KEY_ID", "")
    kalshi_pem    = os.getenv("KALSHI_PRIVATE_KEY_PATH", "kalshi_private.pem")

    kalshi = KalshiWSCache(KalshiClient(key_id=kalshi_key_id, private_key_path=kalshi_pem))
    tennis = TennisAPIClient(api_key=tennis_key)

    print(f"[{_now()}] Starting — monitoring ALL live matches with Kalshi coverage")
    _sep()

    async def on_kalshi_move(market: KalshiMarket, prev_ya: float | None) -> None:
        _on_kalshi(market, prev_ya, tennis.live_matches)

    async def on_tennis_update(match: MatchState) -> None:
        _on_tennis(match, kalshi)

    kalshi.on_price_move(on_kalshi_move)
    tennis.on_update(on_tennis_update)

    kalshi_task = asyncio.create_task(kalshi.run())
    try:
        while True:
            try:
                await tennis.run()
            except (KeyboardInterrupt, asyncio.CancelledError):
                raise
            except Exception as e:
                print(f"[{_now()}] Tennis WS error: {e} — reconnecting")
                await asyncio.sleep(5)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        kalshi_task.cancel()
        print(f"\n[{_now()}] Stopped.")

if __name__ == "__main__":
    asyncio.run(main())
