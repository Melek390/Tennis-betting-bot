import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable

import aiohttp

from .models import MatchState
from .parser import parse_message, parse_finished

logger = logging.getLogger(__name__)

UpdateCallback = Callable[[MatchState], Awaitable[None]]


class TennisAPIClient:
    _WS_URL = "wss://wss.api-tennis.com/live"
    _RECONNECT_DELAY = 5  # seconds between reconnection attempts

    _STALE_AFTER = 1800  # seconds — remove match if no update for 30 min

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._callbacks: list[UpdateCallback] = []
        self._matches: dict[str, MatchState] = {}
        self._last_seen: dict[str, float] = {}
        self._running = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def on_update(self, callback: UpdateCallback) -> None:
        """Register a coroutine to be called on every match state update."""
        self._callbacks.append(callback)

    @property
    def live_matches(self) -> dict[str, MatchState]:
        """Snapshot of all currently tracked live matches keyed by match_id."""
        return dict(self._matches)

    def fresh_matches(self, max_age_secs: float = 300) -> dict[str, MatchState]:
        """Live matches that received a Tennis API update within the last max_age_secs.
        Used by R2 to avoid entering on matches the API stopped reporting (match over)."""
        cutoff = time.monotonic() - max_age_secs
        return {mid: m for mid, m in self._matches.items()
                if self._last_seen.get(mid, 0) >= cutoff}

    async def run(self) -> None:
        """Connect and keep alive. Reconnects automatically on disconnection."""
        self._running = True
        while self._running:
            try:
                await self._connect()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("WebSocket error: %s — reconnecting in %ds", e, self._RECONNECT_DELAY)
                await asyncio.sleep(self._RECONNECT_DELAY)

    async def stop(self) -> None:
        self._running = False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def cleanup_stale(self) -> None:
        """Remove matches not updated in the last 30 minutes."""
        cutoff = time.monotonic() - self._STALE_AFTER
        stale = [mid for mid, ts in self._last_seen.items() if ts < cutoff]
        for mid in stale:
            self._matches.pop(mid, None)
            self._last_seen.pop(mid, None)
        if stale:
            logger.info("Removed %d stale matches, %d remaining", len(stale), len(self._matches))

    async def _connect(self) -> None:
        url = f"{self._WS_URL}?APIkey={self._api_key}&timezone=UTC"
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(url, heartbeat=30) as ws:
                logger.info("Connected to Tennis API WebSocket")
                # Clear on reconnect — fresh stream means fresh state
                self._matches.clear()
                self._last_seen.clear()
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        await self._handle_message(msg.data)
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        logger.error("WebSocket error frame: %s", ws.exception())
                        break
                    elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED):
                        logger.warning("WebSocket closed by server")
                        break

    async def _handle_message(self, raw: str) -> None:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Non-JSON WebSocket message: %.120s", raw)
            return

        # Remove matches that the API has marked as finished (event_live = "0").
        # These messages are NOT passed to callbacks — they only clean up state.
        finished = parse_finished(data)
        for match_id in finished:
            if match_id in self._matches:
                logger.info("Match finished — removing from live_matches: %s", match_id)
                self._matches.pop(match_id, None)
                self._last_seen.pop(match_id, None)

        states = parse_message(data)
        for state in states:
            prev = self._matches.get(state.match_id)
            if prev is not None:
                # Drop stale messages where the set number went backwards
                if state.current_set < prev.current_set:
                    logger.debug(
                        "Dropped stale update %s: set %d → %d",
                        state.match_id, prev.current_set, state.current_set,
                    )
                    continue
                # Drop impossible game scores within the same set
                if prev.current_set == state.current_set:
                    if state.games_first < prev.games_first or state.games_second < prev.games_second:
                        logger.debug(
                            "Dropped impossible score update %s: G%d-%d → G%d-%d",
                            state.match_id,
                            prev.games_first, prev.games_second,
                            state.games_first, state.games_second,
                        )
                        continue
            self._matches[state.match_id] = state
            self._last_seen[state.match_id] = time.monotonic()
            for cb in self._callbacks:
                try:
                    await cb(state)
                except Exception as e:
                    logger.error("Error in update callback: %s", e)
