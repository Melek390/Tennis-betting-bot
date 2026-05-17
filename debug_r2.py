"""
5-minute R2 debug: mirrors bot's exact R2 logic including fresh_matches(300) filter.
Every Kalshi tick ≥3¢ is printed with why R2 did or didn't fire.

Run: python -u debug_r2.py
"""
import asyncio, logging, os, re, sys
from datetime import datetime, timezone

sys.stdout.reconfigure(line_buffering=True)
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.WARNING)

from modules.kalshi.client import KalshiClient
from modules.kalshi.models import KalshiMarket
from modules.kalshi.ws_client import KalshiWSCache
from modules.tennis_api.client import TennisAPIClient
from rules import check_entry_r2

RUN_SECS = 5 * 60

def _now():
    return datetime.now(timezone.utc).strftime("%H:%M:%S")

def _match_for_market(title, live):
    for match in live.values():
        for player in (match.first_player, match.second_player):
            last = player.strip().split()[-1]
            if re.search(r"\b" + re.escape(last) + r"\b", title, re.IGNORECASE):
                return match
    return None

def _r2_why(price, prev_ya, match):
    if prev_ya is None:
        return "no prev_price"
    drop = prev_ya - price
    if drop < 0.12:
        return f"drop only {round(drop*100)}c (need ≥12c)"
    if price < 0.20:
        return f"price {round(price*100)}c < 20c floor"
    if price > 0.75:
        return f"price {round(price*100)}c > 75c cap"
    if match is None:
        return "NO TENNIS MATCH (fresh_matches filter blocked)"
    return "should have fired?"

async def main():
    kalshi = KalshiWSCache(KalshiClient(
        key_id=os.getenv("KALSHI_KEY_ID", ""),
        private_key_path=os.getenv("KALSHI_PRIVATE_KEY_PATH", "kalshi_private.pem"),
    ))
    tennis = TennisAPIClient(api_key=os.getenv("TENNIS_API_KEY", ""))

    moves = 0

    async def on_move(market: KalshiMarket, prev_ya: float | None) -> None:
        nonlocal moves
        price = market.yes_ask
        if prev_ya is None:
            return
        drop = round((prev_ya - price) * 100)
        if drop < 3:          # ignore tiny noise
            return

        moves += 1
        fresh  = tennis.fresh_matches(max_age_secs=300)
        match  = _match_for_market(market.title, fresh)
        fired  = check_entry_r2(price, prev_ya) and match is not None

        tag = "** R2 ENTRY **" if fired else f"no entry — {_r2_why(price, prev_ya, match)}"
        print(
            f"[{_now()}] {market.title[:50]:<50} "
            f"ask={round(price*100):3}c  drop={drop:+3}c  "
            f"prev={round(prev_ya*100):3}c  tennis={'YES' if match else 'no '}  "
            f"{tag}"
        )

    kalshi.on_price_move(on_move)

    async def on_tennis(match):
        pass
    tennis.on_update(on_tennis)

    kalshi_task   = asyncio.create_task(kalshi.run())
    tennis_task   = asyncio.create_task(tennis.run())

    print(f"[{_now()}] Debug R2 — running {RUN_SECS}s. Showing all Kalshi drops ≥3¢ ...\n")
    await asyncio.sleep(RUN_SECS)

    kalshi_task.cancel()
    tennis_task.cancel()
    fresh_count = len(tennis.fresh_matches(max_age_secs=300))
    print(f"\n[{_now()}] Done. {moves} notable moves in {RUN_SECS}s. "
          f"Fresh Tennis matches at end: {fresh_count}")

if __name__ == "__main__":
    asyncio.run(main())
