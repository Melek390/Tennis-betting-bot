from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class _R2Tick:
    mid: float
    serving: str = ""
    set_score: str = ""
    game_score: str = ""
    point_score: str = ""      # e.g. "30–40 [BP]"
    second_break: bool = False


@dataclass
class _R2State:
    # Entry snapshot
    entry_time: datetime | None = None
    entry_ask: float | None = None
    entry_mid: float | None = None
    entry_spread: float | None = None
    entry_drop: int | None = None        # ¢ dropped from prev_ask to ask
    entry_prev_ask: float | None = None
    # Tennis state at entry
    entry_serving: str = ""
    entry_set_score: str = ""
    entry_game_score: str = ""
    entry_break_game: int | None = None  # total games in set when break fired
    entry_sets_total: int = 0            # sets_first + sets_second at entry (stale-tick guard)
    # In-position ticks (one per Tennis API point played)
    ticks: list = field(default_factory=list)
    last_tick_state: str = ""   # "set|game|point" — dedup guard
    # Exit snapshot
    exit_time: datetime | None = None
    exit_ask: float | None = None
    exit_mid: float | None = None
    exit_reason: str = ""
    match_state_exit: str = ""
    # Post-exit ticks for LOG
    post_ticks: list = field(default_factory=list)
    last_post_tick_at: datetime | None = None
    log_sent: bool = False


class R2Tracker:
    _POST_TICK_INTERVAL = 25.0  # seconds minimum between post-exit ticks

    def __init__(self):
        self._data: dict[str, _R2State] = {}

    def set_entry(
        self,
        ticker: str,
        ask: float,
        mid: float,
        spread: float,
        prev_ask: float | None,
        match=None,
    ) -> None:
        d = _R2State()
        d.entry_time     = datetime.now(timezone.utc)
        d.entry_ask      = ask
        d.entry_mid      = mid
        d.entry_spread   = spread
        d.entry_drop     = round((prev_ask - ask) * 100) if prev_ask is not None else None
        d.entry_prev_ask = prev_ask
        if match is not None:
            d.entry_serving    = match.player_name(match.serving)
            d.entry_set_score  = f"{match.sets_first}-{match.sets_second}"
            d.entry_game_score = f"{match.games_first}-{match.games_second}"
            d.entry_break_game = match.games_first + match.games_second
            d.entry_sets_total = match.sets_first + match.sets_second
        self._data[ticker] = d

    def tick(
        self,
        ticker: str,
        mid: float,
        match=None,
        second_break: bool = False,
    ) -> None:
        d = self._data.get(ticker)
        if d is None or d.entry_time is None or d.exit_time is not None:
            return
        t = _R2Tick(mid=mid, second_break=second_break)
        if match is not None:
            # Skip stale Tennis API messages delivered late around set transitions —
            # if the sets total went backwards vs entry, the update is from the
            # previous set and would show e.g. "5-4" instead of "0-0".
            if match.sets_first + match.sets_second >= d.entry_sets_total:
                from rules import fmt_point_score
                t.serving     = match.player_name(match.serving)
                t.set_score   = f"{match.sets_first}-{match.sets_second}"
                t.game_score  = f"{match.games_first}-{match.games_second}"
                t.point_score = fmt_point_score(
                    match.point_score, match.serving,
                    match.match_point_first, match.match_point_second,
                )

        # Only record one tick per point played — skip if Tennis state unchanged
        state_key = f"{t.set_score}|{t.game_score}|{t.point_score}"
        if state_key == d.last_tick_state:
            return
        d.last_tick_state = state_key
        d.ticks.append(t)

    def set_exit(
        self,
        ticker: str,
        ask: float,
        mid: float,
        reason: str,
        match_state_exit: str = "",
    ) -> None:
        d = self._data.get(ticker)
        if d is None:
            return
        d.exit_time       = datetime.now(timezone.utc)
        d.exit_ask        = ask
        d.exit_mid        = mid
        d.exit_reason     = reason
        d.match_state_exit = match_state_exit

    def tick_post_exit(self, ticker: str, mid: float, match=None) -> bool:
        """Collect one post-exit tick (rate-limited). Returns True when 2 ticks collected."""
        d = self._data.get(ticker)
        if d is None or d.exit_time is None or d.log_sent:
            return False
        if len(d.post_ticks) >= 2:
            return False
        now = datetime.now(timezone.utc)
        if d.last_post_tick_at is not None:
            if (now - d.last_post_tick_at).total_seconds() < self._POST_TICK_INTERVAL:
                return False
        t = _R2Tick(mid=mid)
        if match is not None:
            from rules import fmt_point_score
            t.set_score   = f"{match.sets_first}-{match.sets_second}"
            t.game_score  = f"{match.games_first}-{match.games_second}"
            t.point_score = fmt_point_score(
                match.point_score, match.serving,
                match.match_point_first, match.match_point_second,
            )
        d.post_ticks.append(t)
        d.last_post_tick_at = now
        return len(d.post_ticks) >= 2

    def mark_log_sent(self, ticker: str) -> None:
        d = self._data.get(ticker)
        if d:
            d.log_sent = True

    def has_active(self, ticker: str) -> bool:
        """True when in position (entry set, exit not set)."""
        d = self._data.get(ticker)
        return d is not None and d.entry_time is not None and d.exit_time is None

    def has_pending_log(self, ticker: str) -> bool:
        """True when exited but LOG not yet sent."""
        d = self._data.get(ticker)
        return d is not None and d.exit_time is not None and not d.log_sent

    def get_log_data(self, ticker: str) -> dict | None:
        d = self._data.get(ticker)
        if d is None:
            return None
        return {
            "entry_time":        d.entry_time,
            "entry_ask":         d.entry_ask,
            "entry_mid":         d.entry_mid,
            "entry_spread":      d.entry_spread,
            "entry_drop":        d.entry_drop,
            "entry_prev_ask":    d.entry_prev_ask,
            "entry_serving":     d.entry_serving,
            "entry_set_score":   d.entry_set_score,
            "entry_game_score":  d.entry_game_score,
            "entry_break_game":  d.entry_break_game,
            "ticks": [
                {
                    "mid":          t.mid,
                    "serving":      t.serving,
                    "set_score":    t.set_score,
                    "game_score":   t.game_score,
                    "point_score":  t.point_score,
                    "second_break": t.second_break,
                }
                for t in d.ticks
            ],
            "exit_time":        d.exit_time,
            "exit_ask":         d.exit_ask,
            "exit_mid":         d.exit_mid,
            "exit_reason":      d.exit_reason,
            "match_state_exit": d.match_state_exit,
            "post_ticks": [
                {
                    "mid":         t.mid,
                    "set_score":   t.set_score,
                    "game_score":  t.game_score,
                    "point_score": t.point_score,
                }
                for t in d.post_ticks
            ],
        }

    def cleanup(self, active_tickers: set[str]) -> None:
        dead = [k for k in self._data if k not in active_tickers]
        for k in dead:
            del self._data[k]
