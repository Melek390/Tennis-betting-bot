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
_PRICE_CAP = {1: 0.75, 2: 0.65, 3: 0.62, 4: 0.58}


def check_entry(rule: int, match: MatchState, player: str, price: float) -> bool:
    if rule == 1:
        return _rule1_entry(match, player, price)
    if rule == 2:
        return _rule2_entry(match, player, price)
    if rule == 3:
        return _rule3_entry(match, player, price)
    if rule == 4:
        return _rule4_entry(match, player, price)
    return False


def check_exit(rule: int, match: MatchState, player: str) -> bool:
    if rule == 1:
        return _rule1_exit(match, player)
    if rule == 2:
        return _rule2_exit(match, player)
    if rule == 3:
        return _rule3_exit(match, player)
    if rule == 4:
        return _rule4_exit(match, player)
    return False


# ------------------------------------------------------------------
# Rule 1 — Match point + price ≤ 75¢
# ------------------------------------------------------------------

def _rule1_entry(match: MatchState, player: str, price: float) -> bool:
    return match.has_match_point(player) and price <= _PRICE_CAP[1]


def _rule1_exit(match: MatchState, player: str) -> bool:
    return not match.has_match_point(player)


# ------------------------------------------------------------------
# Rule 2 — Leading 1-0 sets + 2+ game lead in set 2 + price ≤ 65¢
# ------------------------------------------------------------------

def _rule2_entry(match: MatchState, player: str, price: float) -> bool:
    sets_won, sets_lost = _set_record(match, player)
    return (
        sets_won == 1
        and sets_lost == 0
        and match.current_set == 2
        and match.game_lead(player) >= 2
        and price <= _PRICE_CAP[2]
    )


def _rule2_exit(match: MatchState, player: str) -> bool:
    return match.game_lead(player) < 2


# ------------------------------------------------------------------
# Rule 3 — Sets 1-1 + 2+ game lead in set 3 + price ≤ 62¢
# ------------------------------------------------------------------

def _rule3_entry(match: MatchState, player: str, price: float) -> bool:
    sets_won, sets_lost = _set_record(match, player)
    return (
        sets_won == 1
        and sets_lost == 1
        and match.current_set == 3
        and match.game_lead(player) >= 2
        and price <= _PRICE_CAP[3]
    )


def _rule3_exit(match: MatchState, player: str) -> bool:
    return match.game_lead(player) < 2


# ------------------------------------------------------------------
# Rule 4 — Won set 1 by 2+ games + 1+ game lead in set 2 + price ≤ 58¢
# ------------------------------------------------------------------

def _rule4_entry(match: MatchState, player: str, price: float) -> bool:
    set1 = match.set_score(1)
    return (
        set1 is not None
        and set1.winner() == player
        and set1.margin() >= 2
        and match.current_set == 2
        and match.game_lead(player) >= 1
        and price <= _PRICE_CAP[4]
    )


def _rule4_exit(match: MatchState, player: str) -> bool:
    return match.game_lead(player) < 1


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

    return ""


# ------------------------------------------------------------------
# Helper
# ------------------------------------------------------------------

def _set_record(match: MatchState, player: str) -> tuple[int, int]:
    """Return (sets_won, sets_lost) for the given player."""
    if player == "first":
        return match.sets_first, match.sets_second
    return match.sets_second, match.sets_first
