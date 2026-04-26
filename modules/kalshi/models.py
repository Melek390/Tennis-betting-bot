from dataclasses import dataclass


@dataclass
class KalshiMarket:
    ticker: str
    title: str
    yes_ask: float      # price for YES = first-named player wins  (e.g. 0.62 = 62¢)
    no_ask: float       # price for NO  = second-named player wins

    def price_for(self, side: str) -> float:
        """Return price for 'yes' or 'no' side."""
        return self.yes_ask if side == "yes" else self.no_ask
