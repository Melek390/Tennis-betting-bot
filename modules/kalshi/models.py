from dataclasses import dataclass


@dataclass
class KalshiMarket:
    ticker: str
    title: str
    yes_ask: float      # price for YES = first-named player wins  (e.g. 0.62 = 62¢)
    no_ask: float       # price for NO  = second-named player wins

    def price_for(self, side: str) -> float:
        return self.yes_ask if side == "yes" else self.no_ask


@dataclass
class PriceInfo:
    price: float
    prev_price: float | None   # price from previous Kalshi refresh (None on first refresh)
    spread: float              # yes_ask + no_ask - 1  (bid-ask spread in dollars)
