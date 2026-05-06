from modules.tennis_api.models import MatchState

_PRICE_CAP   = 0.60
_PRICE_FLOOR = 0.10

_JUMP_THRESHOLD = 0.07
_SPREAD_MAX     = 0.05

_HARD_STOP           = 0.10   # hard stop at -10¢ regardless of context
_FAST_FAILURE_STOP   = 0.06   # early stop at -6¢ if move stalls (> 2 ticks in)
_FAST_FAILURE_TICKS  = 2      # updates_since_entry threshold for fast failure
_FAST_PROFIT         = 0.08   # take profit at +8¢ if within first 2 ticks
_FAST_PROFIT_TICKS   = 1      # updates_since_entry threshold for fast profit

# Break-point scores when first player serves (second is returner with 40)
_BP_SECOND_RETURNS = frozenset({"0 - 40", "15 - 40", "30 - 40"})
# Break-point scores when second player serves (first is returner with 40)
_BP_FIRST_RETURNS  = frozenset({"40 - 0", "40 - 15", "40 - 30"})


def check_entry(
    match: MatchState,
    player: str,
    price: float,
    prev_price: float | None = None,
    spread: float | None = None,
) -> bool:
    if spread is not None and spread > _SPREAD_MAX:
        return False
    if prev_price is not None and abs(price - prev_price) > _JUMP_THRESHOLD:
        return False
    return _has_returner_pressure(match, player) and _PRICE_FLOOR <= price <= _PRICE_CAP


def check_exit(
    match: MatchState,
    player: str,
    price: float = 0.0,
    entry_price: float | None = None,
    updates_since_entry: int = 0,
) -> str | None:
    """Returns exit reason string if exit condition is met, None otherwise."""
    # 1. Structural exit — pressure gone means the trade thesis is dead
    if not _has_returner_pressure(match, player):
        return "Pressure gone"

    if entry_price is None:
        return None

    pnl = price - entry_price

    # 2. Hard stop — always
    if pnl <= -_HARD_STOP:
        return f"Stop loss ({round(pnl * 100)}¢)"

    # 3. Fast failure — price moved against us and isn't recovering
    if pnl <= -_FAST_FAILURE_STOP and updates_since_entry > _FAST_FAILURE_TICKS:
        return f"Fast failure ({round(pnl * 100)}¢)"

    # 4. Fast profit — scalp immediately if move happens on entry tick
    if pnl >= _FAST_PROFIT and updates_since_entry <= _FAST_PROFIT_TICKS:
        return f"Fast profit (+{round(pnl * 100)}¢)"

    return None


def entry_state_label(match: MatchState) -> str:
    ps = match.point_score
    if "AD" in ps:
        return f"Advantage ({ps})"
    return f"Break Point ({ps})"


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


def entry_detail(match: MatchState, player_name: str, price: float) -> str:
    return compact_score(match)


# ------------------------------------------------------------------
# Rule 3 — Back Favourite after Set Loss
# ------------------------------------------------------------------

_R3_PRICE_MIN      = 0.65   # only back strong favourites (≥65¢)
_R3_PRICE_DROP_MIN = 0.10   # enter only when market overreacted ≥10¢ drop
_R3_MAX_SET2_GAMES = 2      # enter only in first 2 games of set 2

# Set 1 must have been a close loss (not a bagel)
_SET1_CLOSE_LOSSES = frozenset({"5-7", "6-7"})


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
    if prev_price is None or (prev_price - price) < _R3_PRICE_DROP_MIN:
        return None
    if price < _R3_PRICE_MIN:
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

_R2_DROP_THRESHOLD = 0.12   # enter when YES price dropped ≥ 12¢ since last refresh
_R2_PRICE_MIN      = 0.20   # don't enter below 20¢
_R2_PRICE_MAX      = 0.75   # don't enter above 75¢
_R2_HARD_STOP      = 0.08   # stop loss at -8¢
_R2_TAKE_PROFIT    = 0.10   # take profit at +10¢


def check_entry_r2(price: float, prev_price: float | None) -> bool:
    if prev_price is None:
        return False
    return (prev_price - price) >= _R2_DROP_THRESHOLD and _R2_PRICE_MIN <= price <= _R2_PRICE_MAX


def check_exit_r2(price: float, entry_price: float | None) -> str | None:
    if entry_price is None:
        return None
    pnl = price - entry_price
    if pnl <= -_R2_HARD_STOP:
        return f"Stop loss ({round(pnl * 100)}¢)"
    if pnl >= _R2_TAKE_PROFIT:
        return f"Take profit (+{round(pnl * 100)}¢)"
    return None


def _has_returner_pressure(match: MatchState, player: str) -> bool:
    if match.serving == player or match.is_tiebreak:
        return False
    ps = match.point_score
    if match.serving == "first":
        return player == "second" and (ps in _BP_SECOND_RETURNS or ps == "40 - AD")
    return player == "first" and (ps in _BP_FIRST_RETURNS or ps == "AD - 40")
