from dataclasses import dataclass


@dataclass
class KalshiMarket:
    ticker: str
    title: str
    yes_ask: float   # best ask for YES  (e.g. 0.62 = 62¢)
    yes_bid: float   # best bid for YES  (e.g. 0.58 = 58¢)

    @property
    def spread(self) -> float:
        return round(self.yes_ask - self.yes_bid, 4)

    @property
    def mid(self) -> float:
        return round((self.yes_ask + self.yes_bid) / 2, 4)

    def price_for(self, side: str) -> float:
        return self.yes_ask if side == "yes" else self.yes_bid


@dataclass
class PriceInfo:
    price: float
    prev_price: float | None   # price from previous WS tick (None on first tick)
    spread: float              # yes_ask - yes_bid (bid-ask spread in dollars)
