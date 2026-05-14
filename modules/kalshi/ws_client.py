"""
Kalshi WebSocket price feed — replaces 30-second REST polling.

On startup it seeds the market list via REST, then maintains a persistent WS
connection to wss://api.elections.kalshi.com/trade-api/ws/v2.  Every price move
fires registered callbacks immediately (typ. 200–700 ms from Kalshi server time).

Public interface mirrors MarketCache so drop-in replacement is straightforward:
  get_prices(), prev_yes_ask(), markets, live_tradeable()
Plus new:
  on_price_move(callback)  — fires (KalshiMarket, prev_yes_ask) on each move
"""
import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable

import aiohttp

from .client import KalshiClient
from .models import KalshiMarket, PriceInfo

logger = logging.getLogger(__name__)

_WS_URL        = "wss://api.elections.kalshi.com/trade-api/ws/v2"
_TENNIS_SERIES = ["KXATPMATCH", "KXWTAMATCH"]
_RECONNECT_DELAY = 10        # seconds between reconnect attempts
_SNAPSHOT_WINDOW = 6.0       # seconds to drain initial snapshot silently

PriceMoveCallback = Callable[[KalshiMarket, "float | None"], Awaitable[None]]


class KalshiWSCache:
    """Real-time Kalshi price cache driven by WebSocket ticker feed."""

    def __init__(self, client: KalshiClient):
        self._client   = client
        self._markets:      dict[str, KalshiMarket] = {}   # ticker → current
        self._prev_ask:     dict[str, float]         = {}   # ticker → prev yes_ask
        self._title_map:    dict[str, str]            = {}   # ticker → display title
        self._callbacks:    list[PriceMoveCallback]   = []
        self._running = False

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def on_price_move(self, cb: PriceMoveCallback) -> None:
        self._callbacks.append(cb)

    @property
    def markets(self) -> list[KalshiMarket]:
        return list(self._markets.values())

    def prev_yes_ask(self, ticker: str) -> float | None:
        return self._prev_ask.get(ticker)

    def get_prices(
        self, player1: str, player2: str
    ) -> tuple[PriceInfo | None, PriceInfo | None]:
        return self._find_price(player1, player2), self._find_price(player2, player1)

    def live_tradeable(self, live_matches: dict) -> tuple[list[str], int]:
        names: list[str] = []
        n_markets = 0
        for match in live_matches.values():
            i1, i2 = self.get_prices(match.first_player, match.second_player)
            n = (i1 is not None) + (i2 is not None)
            if n:
                names.append(f"{match.first_player} vs {match.second_player}")
                n_markets += n
        return names, n_markets

    async def run(self) -> None:
        self._running = True
        while self._running:
            try:
                await self._connect()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Kalshi WS error: %s — reconnecting in %ds", e, _RECONNECT_DELAY)
                await asyncio.sleep(_RECONNECT_DELAY)

    async def stop(self) -> None:
        self._running = False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _connect(self) -> None:
        await self._seed_markets()
        if not self._markets:
            logger.warning("Kalshi WS: no open tennis markets — retrying in 60s")
            await asyncio.sleep(60)
            return

        tickers = list(self._markets.keys())
        logger.info("Kalshi WS: subscribing to %d tickers", len(tickers))

        ws_headers = self._client._auth_headers("GET", "/trade-api/ws/v2")
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(
                _WS_URL, headers=ws_headers, heartbeat=20
            ) as ws:
                logger.info("Kalshi WS connected")
                await ws.send_str(json.dumps({
                    "id": 1,
                    "cmd": "subscribe",
                    "params": {"channels": ["ticker"], "market_tickers": tickers},
                }))

                snapshot_deadline = asyncio.get_event_loop().time() + _SNAPSHOT_WINDOW
                snapshot_logged   = False

                async for msg in ws:
                    if not self._running:
                        break
                    if msg.type == aiohttp.WSMsgType.ERROR:
                        logger.error("Kalshi WS error frame: %s", ws.exception())
                        break
                    if msg.type not in (aiohttp.WSMsgType.TEXT,):
                        continue

                    data = json.loads(msg.data)
                    mtype = data.get("type")

                    if mtype == "subscribed":
                        logger.info("Kalshi WS subscribed (sid=%s)",
                                    data.get("msg", {}).get("sid"))
                        continue
                    if mtype != "ticker":
                        continue

                    d      = data.get("msg", {})
                    ticker = d.get("market_ticker", "")
                    if not ticker:
                        continue

                    try:
                        ya = float(d["yes_ask_dollars"])
                        na = float(d["no_ask_dollars"]) if d.get("no_ask_dollars") else None
                    except (KeyError, ValueError, TypeError):
                        continue

                    title    = self._title_map.get(ticker, "")
                    cached   = self._markets.get(ticker)
                    # WS sometimes omits no_ask_dollars — fall back to last known value
                    no_ask   = na if na is not None else (cached.no_ask if cached else 0.0)
                    market   = KalshiMarket(
                        ticker  = ticker,
                        title   = title,
                        yes_ask = ya,
                        no_ask  = no_ask,
                    )

                    now_t   = asyncio.get_event_loop().time()
                    in_snap = now_t < snapshot_deadline

                    # Always update cache
                    if ticker in self._markets:
                        self._prev_ask[ticker] = self._markets[ticker].yes_ask
                    self._markets[ticker] = market

                    # Drain initial snapshot silently
                    if in_snap:
                        continue

                    if not snapshot_logged:
                        snapshot_logged = True
                        logger.info("Kalshi WS snapshot done — watching for real moves")

                    # Only fire callback on meaningful price change (≥0.5¢)
                    prev = self._prev_ask.get(ticker)
                    if prev is None or abs(ya - prev) < 0.005:
                        continue

                    for cb in self._callbacks:
                        try:
                            await cb(market, prev)
                        except Exception as e:
                            logger.error("Kalshi price-move callback error: %s", e)

    async def _seed_markets(self) -> None:
        """Populate market list and title map from REST before WS connects."""
        markets: dict[str, KalshiMarket] = {}
        for series in _TENNIS_SERIES:
            try:
                data = await self._client.get(
                    "/markets", params={"series_ticker": series, "limit": 1000}
                )
                for m in data.get("markets", []):
                    try:
                        ya = float(m["yes_ask_dollars"])
                        na = float(m["no_ask_dollars"])
                        if 0.01 < ya < 0.99:
                            t     = m["ticker"]
                            title = m.get("yes_sub_title") or m.get("title") or ""
                            markets[t] = KalshiMarket(ticker=t, title=title,
                                                      yes_ask=ya, no_ask=na)
                            self._title_map[t] = title
                    except (KeyError, ValueError, TypeError):
                        pass
            except Exception as e:
                logger.error("Kalshi WS REST seed failed (%s): %s", series, e)

        self._markets = markets
        logger.info("Kalshi WS seeded: %d open markets", len(markets))

    def _find_price(self, player: str, opponent: str = "") -> PriceInfo | None:
        if not self._markets:
            return None
        last = player.strip().split()[-1]
        opp_abbrs = [
            w.upper()[:3] for w in opponent.split()
            if len(w) >= 3 and not w.endswith(".")
        ] if opponent else []
        pat = re.compile(r"\b" + re.escape(last) + r"\b", re.IGNORECASE)

        for market in self._markets.values():
            if not pat.search(market.title):
                continue
            if opp_abbrs and not any(a in market.ticker.upper() for a in opp_abbrs):
                continue
            prev   = self._prev_ask.get(market.ticker)
            spread = round(market.yes_ask + market.no_ask - 1.0, 4)
            return PriceInfo(price=market.yes_ask, prev_price=prev, spread=spread)
        return None
