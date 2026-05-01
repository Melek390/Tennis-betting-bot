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


def _has_returner_pressure(match: MatchState, player: str) -> bool:
    if match.serving == player or match.is_tiebreak:
        return False
    ps = match.point_score
    if match.serving == "first":
        return player == "second" and (ps in _BP_SECOND_RETURNS or ps == "40 - AD")
    return player == "first" and (ps in _BP_FIRST_RETURNS or ps == "AD - 40")
