import asyncio
import logging
import os
import re
from datetime import datetime, timezone

from dotenv import load_dotenv

from modules.bets.db import BetsDB, BETS_DB_KEY
from modules.kalshi.client import KalshiClient
from modules.kalshi.ws_client import KalshiWSCache
from modules.kalshi.models import KalshiMarket
from modules.telegram.bot import TelegramBot
from modules.telegram.messages.alerts import Signal
from modules.tennis_api.client import TennisAPIClient
from modules.tennis_api.models import MatchState
from rules import (
    compact_score,
    check_entry_r2, check_exit_r2,
    check_entry_r3,
)
from state import StateManager
from state_r2 import R2Tracker
from state_r3 import R3Tracker

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Helper — cross-reference Kalshi market title to live Tennis match
# ------------------------------------------------------------------

def _match_for_market(market_title: str, live_matches: dict) -> MatchState | None:
    for match in live_matches.values():
        for player in (match.first_player, match.second_player):
            last = player.strip().split()[-1]
            if re.search(r"\b" + re.escape(last) + r"\b", market_title, re.IGNORECASE):
                return match
    return None


# ------------------------------------------------------------------
# Tennis WebSocket update handler — R3 only
# ------------------------------------------------------------------

async def _process_update(
    match: MatchState,
    kalshi: KalshiWSCache,
    state_mgr_r3: StateManager,
    r3_tracker: R3Tracker,
    bot: TelegramBot,
    bets_db: BetsDB,
) -> None:
    logger.info(
        "Tennis update: %s vs %s | %s | Set %d G%d-%d | %s",
        match.first_player, match.second_player,
        match.tournament, match.current_set,
        match.games_first, match.games_second,
        match.point_score,
    )
    info1, info2 = kalshi.get_prices(match.first_player, match.second_player)

    for player_side, info in (("first", info1), ("second", info2)):
        r3_tracker.update(match.match_id, player_side, match)

        if info is None:
            continue

        price = info.price
        mid   = (price - info.spread / 2) if info.spread is not None else None

        if bot.enabled_r3:
            set1_score  = check_entry_r3(match, player_side, price, info.prev_price)
            ctx_r3      = state_mgr_r3.get_exit_context(match.match_id, player_side)
            exit_r3     = r3_tracker.check_exit(match.match_id, player_side, match, price)

            r3_score  = compact_score(match)
            signal_r3 = state_mgr_r3.process(
                match.match_id, player_side,
                entry_met=set1_score is not None,
                exit_met=exit_r3 is not None,
                price=price,
                entry_mid=mid,
                entry_match_state=r3_score if set1_score is not None else "",
                exit_reason_str=exit_r3 or "",
            )
            state_mgr_r3.tick_position(match.match_id, player_side, price=price)

            player_name_r3 = match.player_name(player_side)
            if signal_r3 in ("entry", "reentry"):
                r3_tracker.set_entry(match.match_id, player_side, price,
                                     player_name=player_name_r3,
                                     match_name=match.match_name)
                prev_p = info.prev_price or price
                drop   = round((prev_p - price) * 100)
                await bot.send_signal(Signal(
                    "R3", "ENTRY" if signal_r3 == "entry" else "RE-ENTRY",
                    f"{player_name_r3} — {match.match_name}",
                    detail=f"Set 1: {set1_score or '?'}  ·  Drop {drop}¢",
                    entry_price=mid,
                ))
            elif signal_r3 == "exit":
                r3_tracker.reset_entry(match.match_id, player_side)
                ep_r3    = ctx_r3.get("entry_mid") or ctx_r3.get("entry_price")
                stats_r3 = state_mgr_r3.get_position_stats(match.match_id, player_side)
                await bot.send_signal(Signal(
                    "R3", "EXIT",
                    f"{player_name_r3} — {match.match_name}",
                    entry_price=ep_r3,
                    exit_price=mid,
                    reason=exit_r3 or "",
                ))
                bets_db.log_exit("r3", player_name_r3, match.match_name,
                                 ep_r3 or mid, mid, exit_r3 or "",
                                 match_state_entry=stats_r3.get("entry_match_state"),
                                 match_state_exit=r3_score)


# ------------------------------------------------------------------
# Rule 2 — Kalshi WebSocket price-move handler (fires on every tick)
# ------------------------------------------------------------------

async def _process_r2_market(
    market: KalshiMarket,
    prev_ya: float | None,
    state_mgr: StateManager,
    r2_tracker: R2Tracker,
    bot: TelegramBot,
    bets_db: BetsDB,
    live_matches: dict,
) -> None:
    """
    Called immediately when Kalshi WS delivers a price move for one market.
    Handles R2 entry and price-based exits (take profit, stop loss).
    Ticks and time-exits are handled by the periodic loop.
    """
    now    = datetime.now(timezone.utc)
    price  = market.yes_ask
    spread = market.spread
    mid    = round(price - spread / 2, 4)
    match  = _match_for_market(market.title, live_matches)

    entry_met    = check_entry_r2(price, prev_ya) and match is not None
    ctx          = state_mgr.get_exit_context(market.ticker, "yes")
    entry_ts     = state_mgr.get_entry_timestamp(market.ticker, "yes")
    elapsed      = (now - entry_ts).total_seconds() if entry_ts else 0
    entry_mid_r2 = ctx.get("entry_mid") or ctx.get("entry_price")
    exit_reason  = check_exit_r2(mid, entry_mid_r2, elapsed_seconds=elapsed)

    r2_match_state = compact_score(match) if match else None
    was_active     = r2_tracker.has_active(market.ticker)

    signal = state_mgr.process(
        market.ticker, "yes",
        entry_met=entry_met,
        exit_met=exit_reason is not None,
        price=price,
        entry_mid=mid if entry_met else None,
        entry_match_state=r2_match_state or "" if entry_met else "",
        exit_mid=mid if exit_reason else None,
        exit_reason_str=exit_reason or "",
    )
    state_mgr.tick_position(market.ticker, "yes", price=price, mid=mid)

    if signal in ("entry", "reentry"):
        r2_tracker.set_entry(market.ticker, price, mid, spread, prev_ya, match)
        drop = round((prev_ya - price) * 100) if prev_ya is not None else 0
        logger.info("R2 %s: %s  drop=%d¢  mid=%.2f  match=%s",
                    signal.upper(), market.ticker, drop, mid,
                    match.match_name if match else "none")
        await bot.send_signal(Signal(
            "R2", "ENTRY" if signal == "entry" else "RE-ENTRY",
            market.title,
            detail=f"Drop {drop}¢",
            entry_price=mid,
        ))

    elif signal == "exit":
        r2_tracker.set_exit(market.ticker, price, mid, exit_reason or "", r2_match_state or "")
        ep_r2 = ctx.get("entry_mid") or ctx.get("entry_price")
        logger.info("R2 EXIT: %s  reason=%s  mid=%.2f", market.ticker, exit_reason, mid)
        await bot.send_signal(Signal(
            "R2", "EXIT",
            market.title,
            entry_price=ep_r2,
            exit_price=mid,
            reason=exit_reason or "",
        ))

    elif was_active:
        # In-position: record tick for LOG (WS fires frequently — only record
        # when state is available so LOG isn't just a wall of price numbers)
        second_break = entry_mid_r2 is not None and mid < entry_mid_r2 - 0.10
        r2_tracker.tick(market.ticker, mid, match, second_break)


# ------------------------------------------------------------------
# R2 periodic loop — time exits + post-exit LOG (runs every 30s)
# ------------------------------------------------------------------

async def _r2_periodic_loop(
    kalshi: KalshiWSCache,
    state_mgr_r2: StateManager,
    r2_tracker: R2Tracker,
    bot: TelegramBot,
    bets_db: BetsDB,
    tennis: TennisAPIClient,
) -> None:
    """Handles R2 time-exits and LOG collection on a 30-second timer."""
    while True:
        await asyncio.sleep(30)
        try:
            now  = datetime.now(timezone.utc)
            live = tennis.live_matches
            for market in kalshi.markets:
                is_active      = r2_tracker.has_active(market.ticker)
                has_log        = r2_tracker.has_pending_log(market.ticker)
                if not (is_active or has_log):
                    continue

                price  = market.yes_ask
                spread = market.spread
                mid    = round(price - spread / 2, 4)
                match  = _match_for_market(market.title, live)

                ctx          = state_mgr_r2.get_exit_context(market.ticker, "yes")
                entry_ts     = state_mgr_r2.get_entry_timestamp(market.ticker, "yes")
                elapsed      = (now - entry_ts).total_seconds() if entry_ts else 0
                entry_mid_r2 = ctx.get("entry_mid") or ctx.get("entry_price")

                if is_active:
                    exit_reason = check_exit_r2(mid, entry_mid_r2, elapsed_seconds=elapsed)
                    if exit_reason:
                        r2_match_state = compact_score(match) if match else None
                        signal = state_mgr_r2.process(
                            market.ticker, "yes",
                            entry_met=False, exit_met=True,
                            price=price, exit_mid=mid,
                            exit_reason_str=exit_reason,
                        )
                        if signal == "exit":
                            r2_tracker.set_exit(market.ticker, price, mid,
                                                exit_reason, r2_match_state or "")
                            ep = ctx.get("entry_mid") or ctx.get("entry_price")
                            await bot.send_signal(Signal(
                                "R2", "EXIT", market.title,
                                entry_price=ep, exit_price=mid, reason=exit_reason,
                            ))

                if has_log:
                    log_ready = r2_tracker.tick_post_exit(market.ticker, mid, match)
                    if log_ready:
                        log_data = r2_tracker.get_log_data(market.ticker)
                        r2_tracker.mark_log_sent(market.ticker)
                        if log_data:
                            await bot.send_log_r2(market.title, log_data)
                            stats_r2 = state_mgr_r2.get_position_stats(market.ticker, "yes")
                            bets_db.log_exit_r2(
                                market.title, log_data,
                                match_state_entry=stats_r2.get("entry_match_state"),
                            )
        except Exception as e:
            logger.error("R2 periodic error: %s", e)


# ------------------------------------------------------------------
# R3 orphan exit loop (runs every 30s)
# ------------------------------------------------------------------

async def _r3_orphan_loop(
    state_mgr_r3: StateManager,
    r3_tracker: R3Tracker,
    bot: TelegramBot,
    bets_db: BetsDB,
    tennis: TennisAPIClient,
) -> None:
    while True:
        await asyncio.sleep(30)
        try:
            live = tennis.live_matches
            for match_id, player_side in state_mgr_r3.active_positions():
                if match_id in live:
                    continue
                d     = r3_tracker._data.get((match_id, player_side))
                if d is None:
                    continue
                ctx   = state_mgr_r3.get_exit_context(match_id, player_side)
                stats = state_mgr_r3.get_position_stats(match_id, player_side)
                ep    = ctx.get("entry_mid") or ctx.get("entry_price")
                reason = "Match ended"
                signal = state_mgr_r3.process(
                    match_id, player_side,
                    entry_met=False, exit_met=True,
                    price=ep, exit_reason_str=reason,
                )
                if signal == "exit":
                    r3_tracker.reset_entry(match_id, player_side)
                    logger.info("R3 orphan exit: %s %s", d.player_name, d.match_name)
                    await bot.send_signal(Signal(
                        "R3", "EXIT",
                        f"{d.player_name} — {d.match_name}",
                        entry_price=ep, exit_price=None, reason=reason,
                    ))
                    bets_db.log_exit(
                        "r3", d.player_name, d.match_name,
                        ep or 0, None, reason,
                        match_state_entry=stats.get("entry_match_state"),
                    )
        except Exception as e:
            logger.error("R3 orphan loop error: %s", e)


# ------------------------------------------------------------------
# Background loops
# ------------------------------------------------------------------

async def _heartbeat_loop(
    bot: TelegramBot,
    tennis: TennisAPIClient,
    kalshi: "KalshiWSCache | None" = None,
) -> None:
    await asyncio.sleep(15)
    while True:
        try:
            match_count = len(tennis.live_matches)
            kalshi_matches = None
            if kalshi:
                names, _ = kalshi.live_tradeable(tennis.fresh_matches(max_age_secs=300))
                kalshi_matches = names
            await bot.send_heartbeat(match_count, kalshi_matches=kalshi_matches)
            logger.info("Heartbeat sent — %d live matches, %d Kalshi",
                        match_count, len(kalshi_matches) if kalshi_matches else 0)
        except Exception as e:
            logger.error("Heartbeat error: %s", e)
        await asyncio.sleep(3600)


async def _state_cleanup_loop(
    state_mgr_r2: StateManager,
    state_mgr_r3: StateManager,
    r2_tracker: R2Tracker,
    r3_tracker: R3Tracker,
    tennis: TennisAPIClient,
    kalshi: KalshiWSCache | None,
) -> None:
    while True:
        await asyncio.sleep(300)
        try:
            tennis.cleanup_stale()
            active_r1 = set(tennis.live_matches.keys())
            if kalshi:
                active_r2 = {m.ticker for m in kalshi.markets}
                state_mgr_r2.cleanup(active_r2)
                r2_tracker.cleanup(active_r2)
            state_mgr_r3.cleanup(active_r1)
            r3_tracker.cleanup(active_r1)
            logger.debug("State cleanup: %d active matches", len(active_r1))
        except Exception as e:
            logger.error("State cleanup error: %s", e)


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

async def main() -> None:
    token      = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_ids   = os.getenv("TELEGRAM_CHAT_IDS") or os.getenv("TELEGRAM_CHAT_ID")
    tennis_key = os.getenv("TENNIS_API_KEY")
    kalshi_key_id = os.getenv("KALSHI_KEY_ID", "")
    kalshi_pem    = os.getenv("KALSHI_PRIVATE_KEY_PATH", "kalshi_private.pem")

    if not token or not chat_ids:
        raise RuntimeError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_IDS must be set in .env")
    if not tennis_key:
        raise RuntimeError("TENNIS_API_KEY must be set in .env")

    bot          = TelegramBot(token=token, chat_ids=chat_ids)
    bets_db      = BetsDB("bets.db")
    bot.app.bot_data[BETS_DB_KEY] = bets_db
    state_mgr_r2 = StateManager()
    state_mgr_r3 = StateManager()
    r2_tracker   = R2Tracker()
    r3_tracker   = R3Tracker()
    tennis       = TennisAPIClient(api_key=tennis_key)

    kalshi_ws: KalshiWSCache | None = None
    if kalshi_key_id:
        try:
            kalshi_client = KalshiClient(key_id=kalshi_key_id, private_key_path=kalshi_pem)
            kalshi_ws     = KalshiWSCache(kalshi_client)
            logger.info("Kalshi WS client initialised")
        except Exception as e:
            logger.warning("Kalshi init failed — price checks disabled: %s", e)
    else:
        logger.warning("KALSHI_KEY_ID not set — price checks disabled")

    await bot.start()
    logger.info("Telegram bot started")

    tasks: list[asyncio.Task] = []

    if kalshi_ws:
        # Register R2 callback — fires on every Kalshi price move
        async def _on_kalshi_move(market: KalshiMarket, prev_ya: float | None) -> None:
            if bot.enabled_r2:
                # Use 30s rolling price as prev — replicates REST 30s polling behaviour
                prev_30s = kalshi_ws.prev_ask_30s(market.ticker, window_secs=30)
                await _process_r2_market(
                    market, prev_30s if prev_30s is not None else prev_ya,
                    state_mgr_r2, r2_tracker, bot, bets_db,
                    tennis.fresh_matches(max_age_secs=300),
                )

        kalshi_ws.on_price_move(_on_kalshi_move)

        tasks.append(asyncio.create_task(kalshi_ws.run()))
        tasks.append(asyncio.create_task(
            _r2_periodic_loop(kalshi_ws, state_mgr_r2, r2_tracker, bot, bets_db, tennis)
        ))

    tasks.append(asyncio.create_task(
        _r3_orphan_loop(state_mgr_r3, r3_tracker, bot, bets_db, tennis)
    ))
    tasks.append(asyncio.create_task(_heartbeat_loop(bot, tennis, kalshi_ws)))
    tasks.append(asyncio.create_task(
        _state_cleanup_loop(state_mgr_r2, state_mgr_r3, r2_tracker, r3_tracker,
                            tennis, kalshi_ws)
    ))

    async def on_update(match: MatchState) -> None:
        if kalshi_ws is None:
            return
        await _process_update(match, kalshi_ws, state_mgr_r3, r3_tracker, bot, bets_db)

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
