from modules.tennis_api.models import MatchState

# Break-point scores when first player serves (second is returner with 40)
_BP_SECOND_RETURNS = frozenset({"0 - 40", "15 - 40", "30 - 40"})
# Break-point scores when second player serves (first is returner with 40)
_BP_FIRST_RETURNS  = frozenset({"40 - 0", "40 - 15", "40 - 30"})

_BP_RAW = frozenset({"0 - 40", "15 - 40", "30 - 40", "40 - 0", "40 - 15", "40 - 30"})


def fmt_point_score(ps: str) -> str:
    """Format raw point score: '30 - 40' → '30–40 BP', '0 - 0' → '0–0'."""
    formatted = ps.replace(" - ", "–")
    if "AD" in ps:
        return f"{formatted} AD"
    if ps in _BP_RAW:
        return f"{formatted} BP"
    return formatted


def compact_score(match: MatchState) -> str:
    """Returns 'S0–1 | G2–5 | 15–40 BP' style line for alerts."""
    return (
        f"S{match.sets_first}–{match.sets_second} | "
        f"G{match.games_first}–{match.games_second} | "
        f"{fmt_point_score(match.point_score)}"
    )


# ------------------------------------------------------------------
# Rule 3 — Back Favourite after Set Loss
# ------------------------------------------------------------------

_R3_PRICE_MIN      = 0.65   # player must HAVE BEEN a strong favourite (prev_price)
_R3_PRICE_FLOOR    = 0.35   # player must still have a meaningful chance
_R3_MAX_SET2_GAMES = 4      # enter within first 4 games of set 2

# Set 1 must have been a close loss (not a bagel or 1-6/2-6)
_SET1_CLOSE_LOSSES = frozenset({"4-6", "5-7", "6-7"})


def check_entry_r3(
    match: MatchState,
    player: str,
    price: float,
    prev_price: float | None,
) -> str | None:
    """
    Returns the set-1 score string (e.g. '5-7') if all R3 entry conditions
    are met, or None if they are not.  Truthy = enter; None = pass.
    """
    if prev_price is None:
        return None
    if prev_price < _R3_PRICE_MIN:   # was a strong favourite before set loss
        return None
    if price >= prev_price:           # price must have actually dropped
        return None
    if price < _R3_PRICE_FLOOR:       # still a live contender
        return None
    if match.current_set != 2:
        return None
    if match.games_first + match.games_second > _R3_MAX_SET2_GAMES:
        return None

    s1 = match.set_score(1)
    if s1 is None or s1.winner() == player:
        return None

    loser_g  = s1.first  if player == "first"  else s1.second
    winner_g = s1.second if player == "first"  else s1.first
    score_str = f"{loser_g}-{winner_g}"
    if score_str not in _SET1_CLOSE_LOSSES:
        return None

    return score_str  # truthy + carries set-1 score for alert text


# ------------------------------------------------------------------
# Rule 2 — Kalshi Spike Fade (price drop mean-reversion)
# ------------------------------------------------------------------

_R2_DROP_MIN       = 0.12   # entry: YES price must have dropped ≥12¢
_R2_PRICE_MIN      = 0.20
_R2_PRICE_MAX      = 0.75
_R2_HARD_STOP      = 0.08   # stop loss at -8¢
_R2_TAKE_PROFIT    = 0.10   # take profit at +10¢
_R2_MAX_OPEN_SECS  = 15 * 60  # 15-minute time exit


def check_entry_r2(price: float, prev_price: float | None) -> bool:
    if prev_price is None:
        return False
    drop = prev_price - price
    return drop >= _R2_DROP_MIN and _R2_PRICE_MIN <= price <= _R2_PRICE_MAX


def check_exit_r2(
    price: float,
    entry_price: float | None,
    elapsed_seconds: float = 0,
) -> str | None:
    if entry_price is None:
        return None
    pnl = price - entry_price
    if pnl <= -_R2_HARD_STOP:
        return f"Stop loss ({round(pnl * 100)}¢)"
    if pnl >= _R2_TAKE_PROFIT:
        return f"Take profit (+{round(pnl * 100)}¢)"
    if elapsed_seconds >= _R2_MAX_OPEN_SECS:
        return f"Time exit — {int(elapsed_seconds / 60)}m"
    return None
