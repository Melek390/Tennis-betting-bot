from dataclasses import dataclass
from datetime import datetime, timezone

from modules.tennis_api.models import MatchState

_TIME_EXIT_SECS = 9 * 60   # 9 minutes
_MIN_PRICE_GAIN = 0.05      # price must have moved +5¢ to avoid time exit


@dataclass
class _R3State:
    # Game-level tracking (updated every WebSocket tick)
    prev_games: tuple[int, int] = (0, 0)
    prev_server: str = ""
    initialized: bool = False

    # Break counts in set 2 (relative to the favourite)
    fav_first_serve_seen: bool = False
    fav_first_serve_broken: bool = False
    games_after_first_break: int = 0
    score_even_after_first_break: bool = False
    set2_breaks_against: int = 0
    break_back_occurred: bool = False   # opponent broken after fav was broken

    # Set at entry
    entry_price: float | None = None
    entry_time: datetime | None = None
    player_name: str = ""
    match_name: str = ""


_Key = tuple[str, str]  # (match_id, player_side)


class R3Tracker:
    def __init__(self):
        self._data: dict[_Key, _R3State] = {}

    def _get(self, match_id: str, player: str) -> _R3State:
        return self._data.setdefault((match_id, player), _R3State())

    # ------------------------------------------------------------------
    # Called by main.py on every WebSocket update (before entry check)
    # ------------------------------------------------------------------

    def update(self, match_id: str, player: str, match: MatchState) -> None:
        """Track game completions and breaks in set 2."""
        if match.current_set != 2:
            return

        d = self._get(match_id, player)
        cur = (match.games_first, match.games_second)
        prev_total = d.prev_games[0] + d.prev_games[1]
        cur_total  = cur[0] + cur[1]

        if d.initialized and cur_total == prev_total + 1 and d.prev_server:
            # One game just completed; skip tiebreak (happens at 6-6)
            if d.prev_games != (6, 6):
                game_winner = "first" if cur[0] > d.prev_games[0] else "second"
                opponent    = "second" if player == "first" else "first"
                server_broke = (game_winner != d.prev_server)

                if d.prev_server == player:
                    # Favourite's service game
                    if not d.fav_first_serve_seen:
                        d.fav_first_serve_seen = True
                        if server_broke:
                            d.fav_first_serve_broken = True
                            d.set2_breaks_against += 1
                    elif server_broke:
                        d.set2_breaks_against += 1

                elif d.prev_server == opponent and server_broke:
                    # Opponent broken → break back for favourite
                    d.break_back_occurred = True

                # Track recovery after first break
                if d.fav_first_serve_broken:
                    d.games_after_first_break += 1
                    if cur[0] == cur[1]:
                        d.score_even_after_first_break = True

        d.prev_games  = cur
        d.prev_server = match.serving
        d.initialized = True

    # ------------------------------------------------------------------
    # Called by main.py when a position is entered / exited
    # ------------------------------------------------------------------

    def set_entry(self, match_id: str, player: str, price: float,
                  player_name: str = "", match_name: str = "") -> None:
        d = self._get(match_id, player)
        d.entry_price  = price
        d.entry_time   = datetime.now(timezone.utc)
        d.player_name  = player_name
        d.match_name   = match_name

    def reset_entry(self, match_id: str, player: str) -> None:
        d = self._get(match_id, player)
        d.entry_price = None
        d.entry_time  = None

    # ------------------------------------------------------------------
    # Exit condition check
    # ------------------------------------------------------------------

    def check_exit(self, match_id: str, player: str, match: MatchState, price: float) -> str | None:
        d = self._data.get((match_id, player))
        if d is None or d.entry_price is None or d.entry_time is None:
            return None

        # 1. Set 2 ended — only trust this once current_set has moved past 2.
        # Stale Tennis API messages (current_set=1 delayed) can put set-2 data
        # in completed_sets while set 2 is still in progress, causing false exits.
        if match.current_set > 2:
            s2 = match.set_score(2)
            winner_side = s2.winner() if s2 is not None else "none"
            tag = "won" if winner_side == player else "lost"
            return f"Set 2 {tag}"

        # 2. Broken in first service game, score not recovered within 2 games
        if (d.fav_first_serve_broken
                and d.games_after_first_break >= 2
                and not d.score_even_after_first_break):
            return "Broken early, no recovery"

        # 3. Broken twice in set 2
        if d.set2_breaks_against >= 2:
            return "Broken twice in Set 2"

        # 4. Time exit — 9 min, no momentum
        elapsed = (datetime.now(timezone.utc) - d.entry_time).total_seconds()
        games_even = match.games_first == match.games_second
        if (elapsed >= _TIME_EXIT_SECS
                and not d.break_back_occurred
                and not games_even
                and (price - d.entry_price) < _MIN_PRICE_GAIN):
            return f"Time exit — {int(elapsed / 60)}m, no momentum"

        return None

    # ------------------------------------------------------------------

    def cleanup(self, active_match_ids: set[str]) -> None:
        dead = [k for k in self._data if k[0] not in active_match_ids]
        for k in dead:
            del self._data[k]
