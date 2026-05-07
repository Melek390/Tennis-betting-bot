import asyncio
import logging
import os
from datetime import datetime, timezone

from dotenv import load_dotenv

from modules.bets.db import BetsDB, BETS_DB_KEY
from modules.kalshi.client import KalshiClient
from modules.kalshi.markets import MarketCache
from modules.telegram.bot import TelegramBot
from modules.tennis_api.client import TennisAPIClient
from modules.tennis_api.models import MatchState
from rules import (
    check_entry, check_exit, compact_score, entry_detail, entry_state_label,
    check_entry_r2, check_exit_r2,
    check_entry_r3, is_deuce,
)
from state import StateManager
from state_r3 import R3Tracker

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
    state_mgr_r3: StateManager,
    r3_tracker: R3Tracker,
    bot: TelegramBot,
    bets_db: BetsDB,
) -> None:
    info1, info2 = kalshi.get_prices(match.first_player, match.second_player)

    for player_side, info in (("first", info1), ("second", info2)):
        if info is None:
            continue

        price = info.price
        mid   = (price - info.spread / 2) if info.spread is not None else None
        ps    = match.point_score

        # ---- Rule 1 — Break Point / Advantage ----
        if bot.enabled:
            player_name = match.player_name(player_side)
            score       = compact_score(match)

            # Fast deuce exit — Tennis API only, fires before Kalshi check
            if state_mgr.is_in_position(match.match_id, player_side) and is_deuce(match):
                last_p, last_m = state_mgr.last_price_mid(match.match_id, player_side)
                ctx_deuce = state_mgr.get_exit_context(match.match_id, player_side)
                signal = state_mgr.process(
                    match.match_id, player_side,
                    entry_met=False, exit_met=True,
                    price=last_p, exit_mid=last_m,
                    exit_point_score=ps, exit_reason_str="Deuce",
                )
                if signal == "exit":
                    exit_pnl = last_m if last_m is not None else last_p
                    stats = state_mgr.get_position_stats(match.match_id, player_side)
                    await bot.send_exit(player_name, match.match_name, score,
                                        exit_price=exit_pnl, stats=stats, exit_reason="Deuce")
                    bets_db.log_exit("r1", player_name, match.match_name,
                                     stats.get("entry_price") or last_p, exit_pnl, "Deuce")

            elif info is not None:
                # Normal Kalshi-priced R1 processing
                entry_met   = check_entry(match, player_side, price,
                                          prev_price=info.prev_price, spread=info.spread)
                ctx         = state_mgr.get_exit_context(match.match_id, player_side)
                exit_reason = check_exit(match, player_side, price=price, **ctx)
                exit_pnl    = mid if mid is not None else price

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

                state_mgr.tick_position(match.match_id, player_side,
                                        price=price, mid=mid, point_score=ps)

                log_ready = state_mgr.tick_post_exit(match.match_id, player_side, price, mid, ps)

                if log_ready:
                    log_data = state_mgr.get_log_data(match.match_id, player_side)
                    state_mgr.mark_log_sent(match.match_id, player_side)
                    await bot.send_log(player_name, match.match_name, log_data)

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
                                        exit_price=exit_pnl, stats=stats, exit_reason=exit_reason)
                    bets_db.log_exit("r1", player_name, match.match_name,
                                     stats.get("entry_price") or price, exit_pnl, exit_reason or "")

        # ---- Rule 3 — Back Fav after Set Loss ----
        # Always update game tracking regardless of enabled state
        r3_tracker.update(match.match_id, player_side, match)

        if bot.enabled_r3:
            set1_score  = check_entry_r3(match, player_side, price, info.prev_price)
            ctx_r3      = state_mgr_r3.get_exit_context(match.match_id, player_side)
            exit_r3     = r3_tracker.check_exit(match.match_id, player_side, match, price)

            signal_r3 = state_mgr_r3.process(
                match.match_id, player_side,
                entry_met=set1_score is not None,
                exit_met=exit_r3 is not None,
                price=price,
                exit_reason_str=exit_r3 or "",
            )
            state_mgr_r3.tick_position(match.match_id, player_side, price=price)

            player_name_r3 = match.player_name(player_side)
            if signal_r3 in ("entry", "reentry"):
                r3_tracker.set_entry(match.match_id, player_side, price)
                await bot.send_entry_r3(
                    player_name_r3, match.match_name, price,
                    info.prev_price or price, set1_score or "?",
                    reentry=(signal_r3 == "reentry"),
                )
            elif signal_r3 == "exit":
                r3_tracker.reset_entry(match.match_id, player_side)
                await bot.send_exit_r3(
                    player_name_r3, match.match_name, price,
                    ctx_r3.get("entry_price"), exit_r3 or "",
                )
                bets_db.log_exit("r3", player_name_r3, match.match_name,
                                 ctx_r3.get("entry_price") or price, price, exit_r3 or "")


# ------------------------------------------------------------------
# Rule 2 — Kalshi Spike Fade update handler
# ------------------------------------------------------------------

async def _process_r2(
    kalshi: MarketCache,
    state_mgr: StateManager,
    bot: TelegramBot,
    bets_db: BetsDB,
) -> None:
    now = datetime.now(timezone.utc)
    for market in kalshi.markets:
        prev   = kalshi.prev_yes_ask(market.ticker)
        price  = market.yes_ask
        spread = round(market.yes_ask + market.no_ask - 1.0, 4)
        mid    = round(price - spread / 2, 4)

        entry_met = check_entry_r2(price, prev, spread=spread)
        ctx       = state_mgr.get_exit_context(market.ticker, "yes")

        entry_ts = state_mgr.get_entry_timestamp(market.ticker, "yes")
        elapsed  = (now - entry_ts).total_seconds() if entry_ts else 0
        exit_reason = check_exit_r2(price, ctx.get("entry_price"), elapsed_seconds=elapsed)

        signal = state_mgr.process(
            market.ticker, "yes",
            entry_met=entry_met,
            exit_met=exit_reason is not None,
            price=price,
            entry_mid=mid if entry_met else None,
            exit_mid=mid if exit_reason else None,
            exit_reason_str=exit_reason or "",
        )
        state_mgr.tick_position(market.ticker, "yes", price=price, mid=mid)

        if signal in ("entry", "reentry"):
            await bot.send_entry_r2(market.title, price, prev or price, reentry=(signal == "reentry"))
        elif signal == "exit":
            exit_pnl = mid
            await bot.send_exit_r2(market.title, exit_pnl, ctx.get("entry_price"), exit_reason or "")
            bets_db.log_exit("r2", market.title, market.title,
                             ctx.get("entry_price") or price, exit_pnl, exit_reason or "")


# ------------------------------------------------------------------
# Background loops
# ------------------------------------------------------------------

async def _kalshi_refresh_loop(
    cache: MarketCache,
    state_mgr_r2: StateManager,
    bot: TelegramBot,
    bets_db: BetsDB,
) -> None:
    while True:
        try:
            await cache.refresh()
            if bot.enabled_r2:
                await _process_r2(cache, state_mgr_r2, bot, bets_db)
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
    state_mgr: StateManager,
    state_mgr_r2: StateManager,
    state_mgr_r3: StateManager,
    r3_tracker: R3Tracker,
    tennis: TennisAPIClient,
    kalshi: MarketCache | None,
) -> None:
    while True:
        await asyncio.sleep(300)
        try:
            tennis.cleanup_stale()
            active_r1 = set(tennis.live_matches.keys())
            state_mgr.cleanup(active_r1)
            if kalshi:
                active_r2 = {m.ticker for m in kalshi.markets}
                state_mgr_r2.cleanup(active_r2)
            state_mgr_r3.cleanup(active_r1)
            r3_tracker.cleanup(active_r1)
            logger.debug("State cleanup: %d active matches", len(active_r1))
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
    bets_db      = BetsDB("bets.db")
    bot.app.bot_data[BETS_DB_KEY] = bets_db
    state_mgr    = StateManager()
    state_mgr_r2 = StateManager()
    state_mgr_r3 = StateManager()
    r3_tracker   = R3Tracker()
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
        tasks.append(asyncio.create_task(_kalshi_refresh_loop(kalshi_cache, state_mgr_r2, bot, bets_db)))

    tasks.append(asyncio.create_task(_heartbeat_loop(bot, tennis)))
    tasks.append(asyncio.create_task(_state_cleanup_loop(state_mgr, state_mgr_r2, state_mgr_r3, r3_tracker, tennis, kalshi_cache)))

    async def on_update(match: MatchState) -> None:
        if kalshi_cache is None:
            return
        await _process_update(match, kalshi_cache, state_mgr, state_mgr_r3, r3_tracker, bot, bets_db)

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
