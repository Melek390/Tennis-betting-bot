"""
Entry and exit conditions for all 4 rules.
All functions take a MatchState and a player ("first" or "second").
Price is a float in dollars (e.g. 0.75 = 75¢).

Original client rules — do NOT change without client approval:
  Rule 1: match point + price ≤ 75¢  | exit: match point lost
  Rule 2: leads 1-0 sets + ≥2 game lead in set 2 + price ≤ 65¢ | exit: lead < 2
  Rule 3: sets 1-1 + ≥2 game lead in set 3 + price ≤ 62¢ | exit: lead < 2
  Rule 4: won set 1 by ≥2 games + ≥1 game lead in set 2 + price ≤ 58¢ | exit: lead < 1
"""
from modules.tennis_api.models import MatchState

# Price cap per rule — single source of truth used in checks AND alert detail text
_PRICE_CAP   = {1: 0.75, 2: 0.65, 3: 0.62, 4: 0.58, 5: 0.60}
# Minimum price — entries below this are skipped (not enough room for a meaningful move)
_PRICE_FLOOR = 0.10


def check_entry(
    rule: int,
    match: MatchState,
    player: str,
    price: float,
    prev_price: float | None = None,
    spread: float | None = None,
) -> bool:
    if rule == 1:
        return _rule1_entry(match, player, price)
    if rule == 2:
        return _rule2_entry(match, player, price)
    if rule == 3:
        return _rule3_entry(match, player, price)
    if rule == 4:
        return _rule4_entry(match, player, price)
    if rule == 5:
        return _rule5_entry(match, player, price, prev_price, spread)
    return False


def check_exit(
    rule: int,
    match: MatchState,
    player: str,
    price: float = 0.0,
    entry_price: float | None = None,
    elapsed_seconds: float = 0.0,
    no_pressure_ticks: int = 0,
) -> str | None:
    """Returns the exit reason string if exit condition is met, None otherwise."""
    if rule == 1:
        return "Match point lost" if _rule1_exit(match, player) else None
    if rule == 2:
        return "Game lead dropped below 2" if _rule2_exit(match, player) else None
    if rule == 3:
        return "Game lead dropped below 2" if _rule3_exit(match, player) else None
    if rule == 4:
        return "Set 2 lead disappeared" if _rule4_exit(match, player) else None
    if rule == 5:
        return _rule5_exit_reason(match, player, price, entry_price, elapsed_seconds, no_pressure_ticks)
    return None


def has_returner_pressure(match: MatchState, player: str) -> bool:
    """Public wrapper — used by main.py to drive Rule 5 pressure tracking."""
    return _has_returner_pressure(match, player)


def rule5_state_label(match: MatchState) -> str:
    """Human-readable entry state for Rule 5: 'Advantage (AD - 40)' etc."""
    ps = match.point_score
    if "AD" in ps:
        return f"Advantage ({ps})"
    return f"Break Point ({ps})"


# ------------------------------------------------------------------
# Rule 1 — Match point + price ≤ 75¢
# ------------------------------------------------------------------

def _rule1_entry(match: MatchState, player: str, price: float) -> bool:
    return match.has_match_point(player) and _PRICE_FLOOR <= price <= _PRICE_CAP[1]


def _rule1_exit(match: MatchState, player: str) -> bool:
    return not match.has_match_point(player)


# ------------------------------------------------------------------
# Rule 2 — Leading 1-0 sets + 2+ game lead in set 2 + price ≤ 65¢
# ------------------------------------------------------------------

def _rule2_entry(match: MatchState, player: str, price: float) -> bool:
    sets_won, sets_lost = _set_record(match, player)
    return (
        match.point_score == "0 - 0"
        and sets_won == 1
        and sets_lost == 0
        and match.current_set == 2
        and match.game_lead(player) >= 2
        and not match.is_tiebreak
        and _PRICE_FLOOR <= price <= _PRICE_CAP[2]
    )


def _rule2_exit(match: MatchState, player: str) -> bool:
    return match.point_score == "0 - 0" and not match.is_tiebreak and match.game_lead(player) < 2


# ------------------------------------------------------------------
# Rule 3 — Sets 1-1 + 2+ game lead in set 3 + price ≤ 62¢
# ------------------------------------------------------------------

def _rule3_entry(match: MatchState, player: str, price: float) -> bool:
    sets_won, sets_lost = _set_record(match, player)
    return (
        match.point_score == "0 - 0"
        and sets_won == 1
        and sets_lost == 1
        and match.current_set == 3
        and match.game_lead(player) >= 2
        and not match.is_tiebreak
        and _PRICE_FLOOR <= price <= _PRICE_CAP[3]
    )


def _rule3_exit(match: MatchState, player: str) -> bool:
    return match.point_score == "0 - 0" and not match.is_tiebreak and match.game_lead(player) < 2


# ------------------------------------------------------------------
# Rule 4 — Won set 1 by 2+ games + 1+ game lead in set 2 + price ≤ 58¢
# ------------------------------------------------------------------

def _rule4_entry(match: MatchState, player: str, price: float) -> bool:
    set1 = match.set_score(1)
    return (
        match.point_score == "0 - 0"
        and set1 is not None
        and set1.winner() == player
        and set1.margin() >= 2
        and match.current_set == 2
        and match.game_lead(player) >= 1
        and not match.is_tiebreak
        and _PRICE_FLOOR <= price <= _PRICE_CAP[4]
    )


def _rule4_exit(match: MatchState, player: str) -> bool:
    return match.point_score == "0 - 0" and not match.is_tiebreak and match.game_lead(player) < 1


# ------------------------------------------------------------------
# Human-readable explanation shown in the alert (so user can verify fast)
# ------------------------------------------------------------------

def rule_detail(rule: int, match: MatchState, player: str, player_name: str, price: float) -> str:
    cap  = int(_PRICE_CAP[rule] * 100)
    p    = int(round(price * 100))
    lead = match.game_lead(player)
    games = f"{lead} game{'s' if lead != 1 else ''}"
    sets_won, sets_lost = _set_record(match, player)

    if rule == 1:
        return f"{player_name} has a match point | Price {p}¢ ≤ {cap}¢"

    if rule == 2:
        return (
            f"{player_name} leads {sets_won}-{sets_lost} in sets | "
            f"Leads Set {match.current_set} by {games} | "
            f"Price {p}¢ ≤ {cap}¢"
        )

    if rule == 3:
        return (
            f"Sets tied {sets_won}-{sets_lost} | "
            f"{player_name} leads Set {match.current_set} by {games} | "
            f"Price {p}¢ ≤ {cap}¢"
        )

    if rule == 4:
        return (
            f"{player_name} won Set 1 by 2+ games | "
            f"Leads Set {match.current_set} by {games} | "
            f"Price {p}¢ ≤ {cap}¢"
        )

    if rule == 5:
        return (
            f"{player_name} is returning | "
            f"Break point / Advantage | "
            f"Score {match.point_score} | "
            f"Price {p}¢ ≤ {cap}¢"
        )

    return ""


# ------------------------------------------------------------------
# Rule 5 — Returner has break point or advantage + price ≤ 60¢
# ------------------------------------------------------------------

# Break-point scores when first player serves (second is returner with 40)
_BP_SECOND_RETURNS = frozenset({"0 - 40", "15 - 40", "30 - 40"})
# Break-point scores when second player serves (first is returner with 40)
_BP_FIRST_RETURNS  = frozenset({"40 - 0", "40 - 15", "40 - 30"})


def _has_returner_pressure(match: MatchState, player: str) -> bool:
    """True when player is the returner and has a break point or advantage."""
    if match.serving == player or match.is_tiebreak:
        return False
    ps = match.point_score
    if match.serving == "first":
        return player == "second" and (ps in _BP_SECOND_RETURNS or ps == "40 - AD")
    return player == "first" and (ps in _BP_FIRST_RETURNS or ps == "AD - 40")


_JUMP_THRESHOLD    = 0.07   # skip entry if price moved more than 7¢ last tick
_SPREAD_MAX        = 0.05   # skip entry if bid-ask spread > 5¢

_PROFIT_TARGET     = 0.10   # exit on +10¢ move
_STOP_LOSS         = 0.10   # exit on -10¢ move
_TIME_EXIT_SECONDS = 90     # exit if price hasn't moved enough after this many seconds
_TIME_EXIT_MIN     = 0.04   # minimum move required to stay in past TIME_EXIT_SECONDS
_PRESSURE_EXIT     = 2      # exit after this many consecutive no-pressure ticks


def _rule5_entry(
    match: MatchState,
    player: str,
    price: float,
    prev_price: float | None,
    spread: float | None,
) -> bool:
    if spread is not None and spread > _SPREAD_MAX:
        return False
    if prev_price is not None and abs(price - prev_price) > _JUMP_THRESHOLD:
        return False
    return _has_returner_pressure(match, player) and _PRICE_FLOOR <= price <= _PRICE_CAP[5]


def _rule5_exit_reason(
    match: MatchState,
    player: str,
    price: float,
    entry_price: float | None,
    elapsed_seconds: float,
    no_pressure_ticks: int,
) -> str | None:
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


# ------------------------------------------------------------------
# Helper
# ------------------------------------------------------------------

def _set_record(match: MatchState, player: str) -> tuple[int, int]:
    """Return (sets_won, sets_lost) for the given player."""
    if player == "first":
        return match.sets_first, match.sets_second
    return match.sets_second, match.sets_first
