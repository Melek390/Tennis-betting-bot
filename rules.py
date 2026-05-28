from modules.tennis_api.models import MatchState

# Tennis API sends "A" for advantage (not "AD")
_POINT_VAL = {"0": 0, "15": 1, "30": 2, "40": 3, "A": 4}


def fmt_point_score(
    ps: str,
    serving: str = "",
    mp_first: bool = False,
    mp_second: bool = False,
    is_tiebreak: bool = False,
) -> str:
    """
    Format raw Tennis API point score with serving-aware annotations.

    ps:      "30 - 40", "40 - A", "A - 40", "0 - 0", "5 - 3" (tiebreak) …
    serving: "first" or "second" (who is currently serving)
    Returns: "30–40 [BP]", "40–Ad [MP]", "Ad–40", "Deuce", "TB 5–3", "TB 6–7 [MP]" …
    """
    if not ps:
        return ""

    parts = ps.strip().split(" - ")
    if len(parts) != 2:
        prefix = "TB " if is_tiebreak else ""
        return prefix + ps.replace(" - ", "–")

    p1_raw, p2_raw = parts[0].strip(), parts[1].strip()

    if is_tiebreak:
        score = f"TB {p1_raw}–{p2_raw}"
        server_has_mp   = (serving == "first" and mp_first) or (serving == "second" and mp_second)
        returner_has_mp = (serving == "first" and mp_second) or (serving == "second" and mp_first)
        tag = " [MP]" if (server_has_mp or returner_has_mp) else ""
        return score + tag

    # Deuce
    if p1_raw == "40" and p2_raw == "40":
        return "Deuce"

    # Compact display — "A" → "Ad"
    p1_disp = "Ad" if p1_raw == "A" else p1_raw
    p2_disp = "Ad" if p2_raw == "A" else p2_raw
    score = f"{p1_disp}–{p2_disp}"

    # Determine tags
    tag = ""

    # Match Point takes priority
    server_has_mp   = (serving == "first" and mp_first) or (serving == "second" and mp_second)
    returner_has_mp = (serving == "first" and mp_second) or (serving == "second" and mp_first)

    if server_has_mp or returner_has_mp:
        tag = " [MP]"
    elif serving:
        # Break Point: returner is one point from winning the game
        sv_raw  = p1_raw if serving == "first" else p2_raw
        ret_raw = p2_raw if serving == "first" else p1_raw
        sv  = _POINT_VAL.get(sv_raw,  -1)
        ret = _POINT_VAL.get(ret_raw, -1)
        # BP when: returner at 40 and server below 40, OR returner at Ad
        if (ret == 3 and sv < 3) or ret == 4:
            tag = " [BP]"

    return score + tag


def compact_score(match: MatchState) -> str:
    """Returns 'S0–1 | G2–5 | 30–40 [BP]' style line for alerts."""
    return (
        f"S{match.sets_first}–{match.sets_second} | "
        f"G{match.games_first}–{match.games_second} | "
        f"{fmt_point_score(match.point_score, match.serving, match.match_point_first, match.match_point_second, is_tiebreak=match.is_tiebreak)}"
    )


# ------------------------------------------------------------------
# Rule 3 — Back Favourite after Set Loss
# ------------------------------------------------------------------

_R3_PRICE_FLOOR    = 0.35   # player must still have a meaningful chance
_R3_PRICE_CAP      = 0.75   # player must still be the favourite (above 50¢ with headroom)
_R3_MAX_SET2_GAMES = 4      # enter within first 4 games of set 2


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
    if price >= prev_price:           # price must have actually dropped
        return None
    if price < _R3_PRICE_FLOOR:       # still a live contender
        return None
    if price > _R3_PRICE_CAP:         # not already near certainty
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

    return score_str  # truthy + carries set-1 score for alert text


# ------------------------------------------------------------------
# Rule 2 — Kalshi Spike Fade (price drop mean-reversion)
# ------------------------------------------------------------------

_R2_DROP_MIN       = 0.16   # entry: YES price must have dropped ≥16¢
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


# ------------------------------------------------------------------
# Rule 4 — Set 1 Winner Spike Fade
# Player leads 1-0 in sets; buy a ≥15¢ drop back into 35-72¢ range
# ------------------------------------------------------------------

_R4_DROP_MIN      = 0.15   # ≥15¢ drop (30s rolling window)
_R4_PRICE_MIN     = 0.35
_R4_PRICE_MAX     = 0.72
_R4_SPREAD_MAX    = 0.08   # ≤8¢ spread (liquidity guard)
_R4_HARD_STOP     = 0.10   # stop loss at -10¢
_R4_TAKE_PROFIT   = 0.10   # take profit at +10¢
_R4_MAX_OPEN_SECS = 8 * 60  # 8-minute time exit


def check_entry_r4(price: float, prev_price: float | None, spread: float) -> bool:
    if prev_price is None:
        return False
    drop = prev_price - price
    return (drop >= _R4_DROP_MIN
            and _R4_PRICE_MIN <= price <= _R4_PRICE_MAX
            and spread <= _R4_SPREAD_MAX)


def check_exit_r4(
    mid: float,
    entry_mid: float | None,
    elapsed_seconds: float = 0,
) -> str | None:
    if entry_mid is None:
        return None
    pnl = mid - entry_mid
    if pnl <= -_R4_HARD_STOP:
        return f"Stop loss ({round(pnl * 100)}¢)"
    if pnl >= _R4_TAKE_PROFIT:
        return f"Take profit (+{round(pnl * 100)}¢)"
    if elapsed_seconds >= _R4_MAX_OPEN_SECS:
        return f"Time exit — {int(elapsed_seconds / 60)}m"
    return None
