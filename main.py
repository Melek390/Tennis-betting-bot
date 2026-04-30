import asyncio
import logging
import os

from dotenv import load_dotenv

from modules.kalshi.client import KalshiClient
from modules.kalshi.markets import MarketCache
from modules.telegram.bot import TelegramBot
from modules.tennis_api.client import TennisAPIClient
from modules.tennis_api.models import MatchState
from rules import check_entry, check_exit, compact_score, entry_detail, entry_state_label, has_returner_pressure
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
    info1, info2 = kalshi.get_prices(match.first_player, match.second_player)

    for player_side, info in (("first", info1), ("second", info2)):
        if info is None:
            continue

        price = info.price
        mid   = (price - info.spread / 2) if info.spread is not None else None
        ps    = match.point_score

        if not bot.enabled:
            continue

        entry_met   = check_entry(match, player_side, price,
                                  prev_price=info.prev_price, spread=info.spread)
        ctx         = state_mgr.get_exit_context(match.match_id, player_side)
        exit_reason = check_exit(match, player_side, price=price, **ctx)

        signal = state_mgr.process(
            match.match_id, player_side,
            entry_met=entry_met,
            exit_met=exit_reason is not None,
            price=price,
            entry_state=entry_state_label(match) if entry_met else "",
            entry_spread=info.spread if entry_met else None,
            entry_mid=mid if entry_met else None,
            entry_point_score=ps if entry_met else "",
            exit_mid=mid if exit_reason else None,
            exit_point_score=ps if exit_reason else "",
            exit_reason_str=exit_reason or "",
        )

        pressure = has_returner_pressure(match, player_side)
        state_mgr.tick_position(match.match_id, player_side, pressure,
                                price=price, mid=mid, point_score=ps)

        # Post-exit tick collection — fires 2 ticks after exit is signalled
        log_ready = state_mgr.tick_post_exit(match.match_id, player_side, price, mid, ps)

        player_name = match.player_name(player_side)
        score       = compact_score(match)

        if log_ready:
            log_data = state_mgr.get_log_data(match.match_id, player_side)
            state_mgr.mark_log_sent(match.match_id, player_side)
            await bot.send_log(player_name, match.match_name, log_data)

        if signal is None:
            continue

        if signal == "entry":
            detail = entry_detail(match, player_name, price)
            await bot.send_entry(player_name, match.match_name, score, price,
                                 detail, spread=info.spread)
        elif signal == "reentry":
            detail = entry_detail(match, player_name, price)
            await bot.send_reentry(player_name, match.match_name, score, price,
                                   detail, spread=info.spread)
        elif signal == "exit":
            stats = state_mgr.get_position_stats(match.match_id, player_side)
            await bot.send_exit(player_name, match.match_name, score,
                                exit_price=price, stats=stats, exit_reason=exit_reason)


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
    await asyncio.sleep(15)
    while True:
        try:
            match_count = len(tennis.live_matches)
            await bot.send_heartbeat(match_count)
            logger.info("Heartbeat sent — %d live matches", match_count)
        except Exception as e:
            logger.error("Heartbeat error: %s", e)
        await asyncio.sleep(3600)


async def _state_cleanup_loop(
    state_mgr: StateManager, tennis: TennisAPIClient
) -> None:
    while True:
        await asyncio.sleep(300)
        try:
            tennis.cleanup_stale()
            active = set(tennis.live_matches.keys())
            state_mgr.cleanup(active)
            logger.debug("State cleanup: %d active matches", len(active))
        except Exception as e:
            logger.error("State cleanup error: %s", e)


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
        while True:
            try:
                await tennis.run()
                logger.warning("Tennis WebSocket exited cleanly — reconnecting in 10s")
            except (KeyboardInterrupt, asyncio.CancelledError):
                raise
            except Exception as e:
                logger.error("Tennis WebSocket error: %s — reconnecting in 10s", e)
                await bot.send_error(f"WebSocket disconnected: {e}\nReconnecting in 10s...")
            await asyncio.sleep(10)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        for t in tasks:
            t.cancel()
        await bot.stop()
        logger.info("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
