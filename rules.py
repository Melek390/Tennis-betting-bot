from modules.tennis_api.models import MatchState

_PRICE_CAP   = 0.60
_PRICE_FLOOR = 0.10

_JUMP_THRESHOLD    = 0.07
_SPREAD_MAX        = 0.05

_FAST_PROFIT_TARGET = 0.08   # exit at +8¢ if move happens within first Kalshi cycle
_FAST_PROFIT_WINDOW = 30.0   # seconds — first Kalshi refresh window
_EXTENDED_TARGET    = 0.14   # hold to +14¢ if move develops slowly after first cycle
_STOP_LOSS          = 0.06   # hard stop at -6¢...
_STOP_HOLD_WINDOW   = 30.0   # ...but hold if pressure still active within first 30s
_TIME_EXIT_SECONDS  = 90
_TIME_EXIT_MIN      = 0.04
_PRESSURE_EXIT      = 2

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

        # Profit — time-aware split
        if elapsed_seconds <= _FAST_PROFIT_WINDOW and move >= _FAST_PROFIT_TARGET:
            return f"Fast profit (+{round(move*100)}¢)"
        if elapsed_seconds > _FAST_PROFIT_WINDOW and move >= _EXTENDED_TARGET:
            return f"Profit target hit (+{round(move*100)}¢)"

        # Context-aware stop loss
        # Hold through shakeout if pressure is still active and entry is fresh
        if move <= -_STOP_LOSS:
            if no_pressure_ticks == 0 and elapsed_seconds <= _STOP_HOLD_WINDOW:
                pass
            else:
                return f"Stop loss hit ({round(move*100)}¢)"

        # No progress
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
