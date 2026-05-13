import logging

from .models import MatchState, SetScore

logger = logging.getLogger(__name__)


def parse_match(raw: dict) -> MatchState | None:
    """Parse a single match object into a MatchState. Returns None on failure."""
    try:
        return _parse(raw)
    except Exception as e:
        logger.debug("Failed to parse match %s: %s", raw.get("event_key"), e)
        return None


def parse_message(data: dict | list) -> list[MatchState]:
    """Parse a full WebSocket message which may contain one or many matches."""
    if isinstance(data, list):
        raws = data
    elif isinstance(data, dict):
        raws = data.get("result", [data])
    else:
        return []

    states = []
    for raw in raws:
        if not isinstance(raw, dict):
            continue
        if str(raw.get("event_live")) != "1":
            continue
        state = parse_match(raw)
        if state:
            states.append(state)
    return states


def parse_finished(data: dict | list) -> list[str]:
    """Return match_ids for matches the API has marked as finished (event_live=0)."""
    if isinstance(data, list):
        raws = data
    elif isinstance(data, dict):
        raws = data.get("result", [data])
    else:
        return []

    finished = []
    for raw in raws:
        if not isinstance(raw, dict):
            continue
        if str(raw.get("event_live")) == "0":
            key = raw.get("event_key")
            if key is not None:
                finished.append(str(key))
    return finished


# ------------------------------------------------------------------
# Internal
# ------------------------------------------------------------------

def _parse(raw: dict) -> MatchState:
    sets_first, sets_second = _parse_score_string(raw.get("event_final_result", "0 - 0"))
    current_set = _set_number_from_status(raw.get("event_status", "Set 1"))
    serving = "first" if "First" in raw.get("event_serve", "") else "second"

    completed_sets, games_first, games_second = _parse_scores(
        raw.get("scores", []), current_set
    )
    mp_first, mp_second = _parse_match_points(raw.get("pointbypoint", []))

    return MatchState(
        match_id=str(raw["event_key"]),
        first_player=raw.get("event_first_player", ""),
        second_player=raw.get("event_second_player", ""),
        sets_first=sets_first,
        sets_second=sets_second,
        current_set=current_set,
        games_first=games_first,
        games_second=games_second,
        point_score=raw.get("event_game_result", "0 - 0"),
        serving=serving,
        match_point_first=mp_first,
        match_point_second=mp_second,
        completed_sets=completed_sets,
        tournament=raw.get("tournament_name", ""),
    )


def _parse_score_string(score: str) -> tuple[int, int]:
    """'1 - 1' → (1, 1)"""
    try:
        a, b = score.split(" - ")
        return int(a.strip()), int(b.strip())
    except (ValueError, AttributeError):
        return 0, 0


def _set_number_from_status(status: str) -> int:
    """'Set 3' → 3"""
    parts = status.strip().split()
    if len(parts) >= 2 and parts[0].lower() == "set":
        try:
            return int(parts[1])
        except ValueError:
            pass
    return 1


def _parse_scores(
    scores: list, current_set: int
) -> tuple[list[SetScore], int, int]:
    """
    scores[] uses score_set = "1" / "2" / "3" (plain number string).
    Returns (completed_sets, games_first_current, games_second_current).
    All sets — including the in-progress one — appear in this array.
    """
    completed: list[SetScore] = []
    games_first = 0
    games_second = 0

    for s in scores:
        if not isinstance(s, dict):
            continue
        try:
            set_num = int(s.get("score_set", 0))
            f = int(s.get("score_first", 0))
            sec = int(s.get("score_second", 0))
        except (ValueError, TypeError):
            continue

        if set_num == current_set:
            games_first = f
            games_second = sec
        else:
            completed.append(SetScore(set_number=set_num, first=f, second=sec))

    return completed, games_first, games_second


def _parse_match_points(pointbypoint: list) -> tuple[bool, bool]:
    """
    pointbypoint is a flat list of game objects across all sets.
    The last entry is the most recent game.
    Each point has: match_point = null | "First Player" | "Second Player"
    We check the last point of the last game.
    """
    if not pointbypoint or not isinstance(pointbypoint, list):
        return False, False

    last_game = pointbypoint[-1]
    if not isinstance(last_game, dict):
        return False, False

    points = last_game.get("points") or []
    if not points:
        return False, False

    last_point = points[-1]
    mp = last_point.get("match_point")

    if not mp:
        return False, False

    return "First" in mp, "Second" in mp
