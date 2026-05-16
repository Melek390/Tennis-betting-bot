"""
Live monitor: tracks a named player across Tennis API WS + Kalshi WS.
Prints match state every Tennis update and evaluates R2/R3 conditions.

Usage:
    python monitor_live.py "Gauff"
    python monitor_live.py "Gauff" "Swiatek"   # narrow by opponent too
"""
import asyncio
import logging
import os
import re
import sys
from datetime import datetime, timezone

sys.stdout.reconfigure(line_buffering=True)  # flush every line

from dotenv import load_dotenv

from modules.kalshi.client import KalshiClient
from modules.kalshi.ws_client import KalshiWSCache
from modules.kalshi.models import KalshiMarket
from modules.tennis_api.client import TennisAPIClient
from modules.tennis_api.models import MatchState
from rules import check_entry_r2, check_entry_r3, check_exit_r2, fmt_point_score, compact_score

load_dotenv()

logging.basicConfig(level=logging.WARNING)  # silence library noise

PLAYER   = sys.argv[1] if len(sys.argv) > 1 else "Gauff"
OPPONENT = sys.argv[2] if len(sys.argv) > 2 else ""

# ── state ──────────────────────────────────────────────────────────────
_r2_entry_mid:   float | None = None
_r2_entry_time:  datetime | None = None
_r3_entry_mid:   float | None = None
_r3_entry_side:  str = ""

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def _find_match(live: dict) -> MatchState | None:
    pat = re.compile(r"\b" + re.escape(PLAYER) + r"\b", re.IGNORECASE)
    opp = re.compile(r"\b" + re.escape(OPPONENT) + r"\b", re.IGNORECASE) if OPPONENT else None
    for m in live.values():
        if pat.search(m.first_player) or pat.search(m.second_player):
            if opp and not (opp.search(m.first_player) or opp.search(m.second_player)):
                continue
            return m
    return None


def _player_side(match: MatchState) -> str:
    """Return 'first' or 'second' for the monitored player."""
    pat = re.compile(r"\b" + re.escape(PLAYER) + r"\b", re.IGNORECASE)
    return "first" if pat.search(match.first_player) else "second"


# ── Tennis update callback ──────────────────────────────────────────────

def _on_tennis(match: MatchState, kalshi: KalshiWSCache) -> None:
    global _r3_entry_mid, _r3_entry_side

    side   = _player_side(match)
    name   = match.player_name(side)
    info1, info2 = kalshi.get_prices(match.first_player, match.second_player)
    info   = info1 if side == "first" else info2

    score  = fmt_point_score(match.point_score, match.serving,
                              match.match_point_first, match.match_point_second,
                              is_tiebreak=match.is_tiebreak).replace("–", "-")
    tb_tag = " [TB]" if match.is_tiebreak else ""
    print(
        f"\n[{_now()}] TENNIS  {name} | "
        f"Sets {match.sets_first}-{match.sets_second} | "
        f"G {match.games_first}-{match.games_second}{tb_tag} | "
        f"{score} | Srv: {match.serving}"
    )

    if info is None:
        print(f"           Kalshi: no market found for '{name}'")
        return

    price   = info.price
    prev_p  = info.prev_price
    spread  = info.spread
    mid     = round(price - spread / 2, 4)
    prev_str = f"{prev_p:.2f}" if prev_p is not None else "—"
    print(f"           Kalshi: ask={price:.2f}  mid={mid:.2f}  spread={round(spread*100)}c  prev={prev_str}")

    # ── R3 check ──
    set1_score = check_entry_r3(match, side, price, prev_p)
    if set1_score:
        if _r3_entry_mid is None:
            _r3_entry_mid  = mid
            _r3_entry_side = side
            drop = round((prev_p - price) * 100) if prev_p else 0
            print(f"  ** R3 ENTRY  {name}  set1={set1_score}  drop={drop}c  mid={mid:.2f}")
        else:
            print(f"  OK R3 in position  entry_mid={_r3_entry_mid:.2f}  current={mid:.2f}  P&L={round((mid-_r3_entry_mid)*100):+}c")
    else:
        if _r3_entry_mid is not None and _r3_entry_side == side:
            # crude exit: R3 condition no longer met
            pnl = round((mid - _r3_entry_mid) * 100)
            print(f"  XX R3 EXIT  P&L={pnl:+}c  mid={mid:.2f}")
            _r3_entry_mid  = None
            _r3_entry_side = ""
        else:
            r3_why = _r3_why(match, side, price, prev_p)
            print(f"  - R3 not met: {r3_why}")


def _r3_why(match: MatchState, side: str, price: float, prev_p) -> str:
    """Human-readable reason R3 entry is not firing."""
    if prev_p is None:
        return "no prev price yet"
    if price >= prev_p:
        return f"price not dropped ({prev_p:.2f}->{price:.2f})"
    if price < 0.35:
        return f"price too low ({price:.2f}<0.35)"
    if price > 0.75:
        return f"price too high ({price:.2f}>0.75)"
    if match.current_set != 2:
        return f"not set 2 (set={match.current_set})"
    if match.games_first + match.games_second > 4:
        return f"too many games in set 2 ({match.games_first+match.games_second}>4)"
    s1 = match.set_score(1)
    if s1 is None:
        return "no set 1 score recorded"
    if s1.winner() == side:
        return "player won set 1 (R3 needs a set loss)"
    return "conditions met — should have fired"


# ── Kalshi price-move callback ──────────────────────────────────────────

def _on_kalshi(market: KalshiMarket, prev_ya: float | None, live: dict) -> None:
    global _r2_entry_mid, _r2_entry_time

    # Only care about markets that contain our player name
    pat = re.compile(r"\b" + re.escape(PLAYER) + r"\b", re.IGNORECASE)
    if not pat.search(market.title):
        return

    price  = market.yes_ask
    spread = market.spread
    mid    = market.mid
    now    = datetime.now(timezone.utc)

    print(f"\n[{_now()}] KALSHI  {market.title}")
    prev_str = f"{prev_ya:.2f}" if prev_ya is not None else "—"
    print(f"           ask={price:.2f}  mid={mid:.2f}  spread={round(spread*100)}c  prev={prev_str}")

    # ── R2 check ──
    if _r2_entry_mid is None:
        if check_entry_r2(price, prev_ya):
            drop = round((prev_ya - price) * 100) if prev_ya else 0
            _r2_entry_mid  = mid
            _r2_entry_time = now
            print(f"  ** R2 ENTRY  drop={drop}c  mid={mid:.2f}")
        else:
            drop = round((prev_ya - price) * 100) if prev_ya else 0
            needed = 12
            print(f"  - R2 not met: drop={drop}c (need>={needed}c)  price={price:.2f} (need 0.20-0.75)")
    else:
        elapsed = (now - _r2_entry_time).total_seconds() if _r2_entry_time else 0
        reason  = check_exit_r2(mid, _r2_entry_mid, elapsed)
        pnl     = round((mid - _r2_entry_mid) * 100)
        if reason:
            print(f"  XX R2 EXIT  {reason}  P&L={pnl:+}c")
            _r2_entry_mid  = None
            _r2_entry_time = None
        else:
            print(f"  OK R2 in position  entry={_r2_entry_mid:.2f}  current={mid:.2f}  P&L={pnl:+}c  elapsed={int(elapsed)}s")


# ── Main ────────────────────────────────────────────────────────────────

async def main() -> None:
    tennis_key    = os.getenv("TENNIS_API_KEY", "")
    kalshi_key_id = os.getenv("KALSHI_KEY_ID", "")
    kalshi_pem    = os.getenv("KALSHI_PRIVATE_KEY_PATH", "kalshi_private.pem")

    if not tennis_key or not kalshi_key_id:
        print("ERROR: TENNIS_API_KEY and KALSHI_KEY_ID must be set in .env")
        return

    kalshi_client = KalshiClient(key_id=kalshi_key_id, private_key_path=kalshi_pem)
    kalshi        = KalshiWSCache(kalshi_client)
    tennis        = TennisAPIClient(api_key=tennis_key)

    print(f"Monitoring player: '{PLAYER}'" + (f" vs '{OPPONENT}'" if OPPONENT else ""))
    print("Waiting for Tennis API + Kalshi WS connections...\n")

    # Register Kalshi price-move callback
    async def on_kalshi_move(market: KalshiMarket, prev_ya: float | None) -> None:
        _on_kalshi(market, prev_ya, tennis.live_matches)

    kalshi.on_price_move(on_kalshi_move)

    # Register Tennis update callback
    async def on_tennis_update(match: MatchState) -> None:
        # Only process if this is our match
        pat = re.compile(r"\b" + re.escape(PLAYER) + r"\b", re.IGNORECASE)
        if not (pat.search(match.first_player) or pat.search(match.second_player)):
            return
        if OPPONENT:
            opp = re.compile(r"\b" + re.escape(OPPONENT) + r"\b", re.IGNORECASE)
            if not (opp.search(match.first_player) or opp.search(match.second_player)):
                return
        _on_tennis(match, kalshi)

    tennis.on_update(on_tennis_update)

    # Run both WS feeds concurrently
    kalshi_task = asyncio.create_task(kalshi.run())

    try:
        while True:
            try:
                await tennis.run()
            except (KeyboardInterrupt, asyncio.CancelledError):
                raise
            except Exception as e:
                print(f"[{_now()}] Tennis WS error: {e} — reconnecting in 5s")
                await asyncio.sleep(5)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        kalshi_task.cancel()
        print("\nStopped.")


if __name__ == "__main__":
    asyncio.run(main())
