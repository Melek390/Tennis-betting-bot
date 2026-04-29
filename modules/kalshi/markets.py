import logging
import re

from .client import KalshiClient
from .models import KalshiMarket, PriceInfo

logger = logging.getLogger(__name__)

_TENNIS_SERIES = ["KXATPMATCH", "KXWTAMATCH"]


class MarketCache:
    REFRESH_INTERVAL = 30  # seconds

    def __init__(self, client: KalshiClient):
        self._client = client
        self._markets: list[KalshiMarket] = []
        self._prev_yes_ask: dict[str, float] = {}   # ticker → yes_ask from last refresh

    async def refresh(self) -> None:
        # Snapshot current prices before overwriting
        prev = {m.ticker: m.yes_ask for m in self._markets}

        markets: list[KalshiMarket] = []
        for series in _TENNIS_SERIES:
            try:
                data = await self._client.get(
                    "/markets",
                    params={"series_ticker": series, "limit": 1000},
                )
                for m in data.get("markets", []):
                    market = _parse_market(m)
                    if market:
                        markets.append(market)
            except Exception as e:
                logger.error("Kalshi refresh failed for %s: %s", series, e)

        self._prev_yes_ask = prev
        self._markets = markets
        logger.info("Kalshi cache: %d active tennis markets", len(markets))

    def get_prices(
        self, player1: str, player2: str
    ) -> tuple[PriceInfo | None, PriceInfo | None]:
        """
        Each Kalshi tennis market covers ONE player (title = full name).
        Match each player's last name against market titles independently.
        Returns (PriceInfo_for_player1, PriceInfo_for_player2).
        """
        return self._find_price(player1), self._find_price(player2)

    def _find_price(self, player: str) -> PriceInfo | None:
        if not self._markets:
            return None

        last_name = _last_name(player)
        # Word-boundary match: "Martineau" must appear as a whole word,
        # not as a substring of "Martin" inside "Martin Damm Jr".
        pattern = re.compile(r"\b" + re.escape(last_name) + r"\b", re.IGNORECASE)

        for market in self._markets:
            if pattern.search(market.title):
                prev  = self._prev_yes_ask.get(market.ticker)
                spread = round(market.yes_ask + market.no_ask - 1.0, 4)
                logger.debug(
                    "Matched '%s' → '%s' (price %.2f, spread %.2f)",
                    player, market.title, market.yes_ask, spread,
                )
                return PriceInfo(price=market.yes_ask, prev_price=prev, spread=spread)

        logger.debug("No Kalshi market found for player: %s", player)
        return None


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _parse_market(raw: dict) -> KalshiMarket | None:
    try:
        yes_ask = float(raw["yes_ask_dollars"])
        no_ask  = float(raw["no_ask_dollars"])
        # Skip settled markets (priced at exactly 1¢ or 100¢)
        if yes_ask <= 0.01 or yes_ask >= 0.99:
            return None
        title = raw.get("yes_sub_title") or raw.get("title") or ""
        return KalshiMarket(
            ticker=raw["ticker"],
            title=title,
            yes_ask=yes_ask,
            no_ask=no_ask,
        )
    except (KeyError, ValueError, TypeError):
        return None


def _last_name(player: str) -> str:
    """'F. Moroni' → 'Moroni',  'Putintseva' → 'Putintseva'"""
    return player.strip().split()[-1]
