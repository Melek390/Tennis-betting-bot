import asyncio, os, time
from dotenv import load_dotenv
load_dotenv()

from modules.kalshi.client import KalshiClient
from modules.tennis_api.client import TennisAPIClient

async def main():
    # --- Tennis API check ---
    tennis = TennisAPIClient(api_key=os.getenv("TENNIS_API_KEY"))
    async def noop(m): pass
    tennis.on_update(noop)
    task = asyncio.create_task(tennis.run())
    await asyncio.sleep(12)
    task.cancel()

    print(f"Tennis API: {len(tennis.live_matches)} live, {len(tennis.fresh_matches(300))} fresh\n")
    for m in tennis.live_matches.values():
        age = int(time.monotonic() - tennis._last_seen.get(m.match_id, 0))
        fresh = m.match_id in tennis.fresh_matches(300)
        if any(n in (m.first_player + m.second_player).lower() for n in ("sinner","ruud","rome","paul","quinn","jeanjean","fernandez")):
            print(f"  {'FRESH' if fresh else 'STALE':5} {m.first_player} vs {m.second_player} | age={age}s | {m.tournament}")

    # --- Kalshi check ---
    print()
    client = KalshiClient(key_id=os.getenv("KALSHI_KEY_ID",""), private_key_path=os.getenv("KALSHI_PRIVATE_KEY_PATH","kalshi_private.pem"))
    for series in ("KXATPMATCH","KXWTAMATCH"):
        data = await client.get("/markets", params={"series_ticker": series, "limit": 200})
        for m in data.get("markets", []):
            title = m.get("yes_sub_title") or m.get("title") or ""
            if any(n in title.lower() for n in ("sinner","ruud","rome","paul","quinn")):
                ya = m.get("yes_ask_dollars")
                print(f"  Kalshi [{series}] {title} | ask={ya} | status={m.get('status')}")

asyncio.run(main())
