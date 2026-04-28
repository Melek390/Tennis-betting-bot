import asyncio
import logging
import os

from dotenv import load_dotenv

from modules.kalshi.client import KalshiClient
from modules.kalshi.markets import MarketCache
from modules.telegram.bot import TelegramBot
from modules.telegram.state import STATE_MGR_KEY
from modules.tennis_api.client import TennisAPIClient
from modules.tennis_api.models import MatchState
from rules import check_entry, check_exit, rule_detail
from state import StateManager

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Core update handler — called on every tennis WebSocket message
# ------------------------------------------------------------------

async def _process_update(
    match: MatchState,
    kalshi: MarketCache,
    state_mgr: StateManager,
    bot: TelegramBot,
) -> None:
    price1, price2 = kalshi.get_prices(match.first_player, match.second_player)

    for player_side, price in (("first", price1), ("second", price2)):
        if price is None:
            continue

        for rule in range(1, 8):
            if not bot.enabled_rules.get(rule, True):
                continue

            entry_met = check_entry(rule, match, player_side, price)
            exit_met  = check_exit(rule, match, player_side)
            signal    = state_mgr.process(match.match_id, player_side, rule, entry_met, exit_met)

            if signal is None:
                continue

            player_name = match.player_name(player_side)
            score       = match.score_summary

            if signal == "entry":
                detail = rule_detail(rule, match, player_side, player_name, price)
                await bot.send_entry(rule, player_name, match.match_name, score, price,
                                     match.match_id, player_side, detail)
            elif signal == "reentry":
                detail = rule_detail(rule, match, player_side, player_name, price)
                await bot.send_reentry(rule, player_name, match.match_name, score, price,
                                       match.match_id, player_side, detail)
            elif signal == "exit":
                await bot.send_exit(rule, player_name, match.match_name, score,
                                    match.match_id, player_side)


# ------------------------------------------------------------------
# Background loops
# ------------------------------------------------------------------

async def _kalshi_refresh_loop(cache: MarketCache) -> None:
    while True:
        try:
            await cache.refresh()
        except Exception as e:
            logger.error("Kalshi refresh error: %s", e)
        await asyncio.sleep(MarketCache.REFRESH_INTERVAL)


async def _heartbeat_loop(bot: TelegramBot, tennis: TennisAPIClient) -> None:
    # Give the WebSocket time to connect and receive initial match data
    await asyncio.sleep(15)
    while True:
        match_count = len(tennis.live_matches)
        await bot.send_heartbeat(match_count)
        logger.info("Heartbeat sent — %d live matches", match_count)
        await asyncio.sleep(3600)


async def _state_cleanup_loop(
    state_mgr: StateManager, tennis: TennisAPIClient
) -> None:
    while True:
        await asyncio.sleep(300)  # every 5 minutes
        tennis.cleanup_stale()
        active = set(tennis.live_matches.keys())
        state_mgr.cleanup(active)
        logger.debug("State cleanup: %d active matches", len(active))


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

async def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_ids = os.getenv("TELEGRAM_CHAT_IDS") or os.getenv("TELEGRAM_CHAT_ID")
    tennis_key = os.getenv("TENNIS_API_KEY")
    kalshi_key_id = os.getenv("KALSHI_KEY_ID", "")
    kalshi_pem = os.getenv("KALSHI_PRIVATE_KEY_PATH", "kalshi_private.pem")

    if not token or not chat_ids:
        raise RuntimeError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_IDS must be set in .env")
    if not tennis_key:
        raise RuntimeError("TENNIS_API_KEY must be set in .env")

    bot = TelegramBot(token=token, chat_ids=chat_ids)
    state_mgr = StateManager()
    bot.app.bot_data[STATE_MGR_KEY] = state_mgr
    tennis = TennisAPIClient(api_key=tennis_key)

    # Kalshi is optional until client provides credentials
    kalshi_cache: MarketCache | None = None
    if kalshi_key_id:
        try:
            kalshi_client = KalshiClient(key_id=kalshi_key_id, private_key_path=kalshi_pem)
            kalshi_cache = MarketCache(kalshi_client)
            logger.info("Kalshi client initialised")
        except Exception as e:
            logger.warning("Kalshi init failed — price checks disabled: %s", e)
    else:
        logger.warning("KALSHI_KEY_ID not set — price checks disabled until credentials are added")

    await bot.start()
    logger.info("Telegram bot started")

    tasks: list[asyncio.Task] = []

    if kalshi_cache:
        tasks.append(asyncio.create_task(_kalshi_refresh_loop(kalshi_cache)))

    tasks.append(asyncio.create_task(_heartbeat_loop(bot, tennis)))
    tasks.append(asyncio.create_task(_state_cleanup_loop(state_mgr, tennis)))

    async def on_update(match: MatchState) -> None:
        if kalshi_cache is None:
            return
        await _process_update(match, kalshi_cache, state_mgr, bot)

    tennis.on_update(on_update)

    logger.info("Connecting to Tennis API WebSocket...")
    try:
        await tennis.run()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        for t in tasks:
            t.cancel()
        await bot.stop()
        logger.info("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
