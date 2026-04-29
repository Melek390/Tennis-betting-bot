from modules.tennis_api.models import MatchState

_PRICE_CAP   = 0.60
_PRICE_FLOOR = 0.10

_JUMP_THRESHOLD    = 0.07
_SPREAD_MAX        = 0.05

_PROFIT_TARGET     = 0.10
_STOP_LOSS         = 0.10
_TIME_EXIT_SECONDS = 90
_TIME_EXIT_MIN     = 0.04
_PRESSURE_EXIT     = 2

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
    elapsed_seconds: float = 0.0,
    no_pressure_ticks: int = 0,
) -> str | None:
    """Returns exit reason string if exit condition is met, None otherwise."""
    if no_pressure_ticks >= _PRESSURE_EXIT:
        return "Break point pressure gone"
    if entry_price is not None:
        move = price - entry_price
        if move >= _PROFIT_TARGET:
            return f"Profit target hit (+{round(move*100)}¢)"
        if move <= -_STOP_LOSS:
            return f"Stop loss hit ({round(move*100)}¢)"
        if elapsed_seconds >= _TIME_EXIT_SECONDS and move < _TIME_EXIT_MIN:
            return f"No movement after {round(elapsed_seconds)}s"
    return None


def has_returner_pressure(match: MatchState, player: str) -> bool:
    return _has_returner_pressure(match, player)


def entry_state_label(match: MatchState) -> str:
    ps = match.point_score
    if "AD" in ps:
        return f"Advantage ({ps})"
    return f"Break Point ({ps})"


def entry_detail(match: MatchState, player_name: str, price: float) -> str:
    p   = int(round(price * 100))
    cap = int(_PRICE_CAP * 100)
    return (
        f"{player_name} is returning | "
        f"Break point / Advantage | "
        f"Score {match.point_score} | "
        f"Price {p}¢ ≤ {cap}¢"
    )


def _has_returner_pressure(match: MatchState, player: str) -> bool:
    if match.serving == player or match.is_tiebreak:
        return False
    ps = match.point_score
    if match.serving == "first":
        return player == "second" and (ps in _BP_SECOND_RETURNS or ps == "40 - AD")
    return player == "first" and (ps in _BP_FIRST_RETURNS or ps == "AD - 40")
