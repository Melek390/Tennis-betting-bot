from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class RuleState(Enum):
    WATCHING         = "watching"
    IN_POSITION      = "in_position"
    WATCHING_REENTRY = "watching_reentry"


@dataclass
class _Entry:
    state: RuleState = RuleState.WATCHING
    entry_price: float | None = None
    entry_mid: float | None = None
    entry_timestamp: datetime | None = None
    entry_state: str = ""
    entry_point_score: str = ""
    entry_spread: float | None = None
    ticks_in_position: int = 0
    tick_history: list = field(default_factory=list)   # (price, mid, point_score)
    mae: float = 0.0
    mfe: float = 0.0
    # Exit snapshot
    exit_price: float | None = None
    exit_mid: float | None = None
    exit_timestamp: datetime | None = None
    exit_point_score: str = ""
    exit_reason_str: str = ""
    # Post-exit log
    post_exit_ticks: list = field(default_factory=list)  # (price, mid, point_score)
    last_post_exit_tick_at: datetime | None = None
    log_sent: bool = False


_StateKey = tuple[str, str]


class StateManager:
    def __init__(self):
        self._data: dict[_StateKey, _Entry] = {}

    def _get(self, match_id: str, player: str) -> _Entry:
        return self._data.setdefault((match_id, player), _Entry())

    # ------------------------------------------------------------------
    # Called on every WebSocket update
    # ------------------------------------------------------------------

    def process(
        self,
        match_id: str,
        player: str,
        entry_met: bool,
        exit_met: bool,
        price: float | None = None,
        entry_state: str = "",
        entry_spread: float | None = None,
        entry_mid: float | None = None,
        entry_point_score: str = "",
        exit_mid: float | None = None,
        exit_point_score: str = "",
        exit_reason_str: str = "",
    ) -> str | None:
        """Returns 'entry', 'exit', 'reentry', or None."""
        e = self._get(match_id, player)

        if e.state == RuleState.WATCHING and entry_met:
            e.state = RuleState.IN_POSITION
            e.ticks_in_position = 0
            e.entry_price = price
            e.entry_mid = entry_mid
            e.entry_timestamp = datetime.now(timezone.utc)
            e.entry_state = entry_state
            e.entry_point_score = entry_point_score
            e.entry_spread = entry_spread
            e.tick_history = []
            e.mae = 0.0
            e.mfe = 0.0
            e.exit_price = None
            e.exit_mid = None
            e.exit_timestamp = None
            e.exit_point_score = ""
            e.exit_reason_str = ""
            e.post_exit_ticks = []
            e.last_post_exit_tick_at = None
            e.log_sent = False
            return "entry"

        if e.state == RuleState.IN_POSITION and exit_met:
            e.state = RuleState.WATCHING_REENTRY
            e.exit_price = price
            e.exit_mid = exit_mid
            e.exit_timestamp = datetime.now(timezone.utc)
            e.exit_point_score = exit_point_score
            e.exit_reason_str = exit_reason_str
            if price is not None and e.entry_price is not None:
                move = price - e.entry_price
                e.mae = min(e.mae, move)
                e.mfe = max(e.mfe, move)
            return "exit"

        if e.state == RuleState.WATCHING_REENTRY and entry_met:
            e.state = RuleState.IN_POSITION
            e.ticks_in_position = 0
            e.entry_price = price
            e.entry_mid = entry_mid
            e.entry_timestamp = datetime.now(timezone.utc)
            e.entry_state = entry_state
            e.entry_point_score = entry_point_score
            e.entry_spread = entry_spread
            e.tick_history = []
            e.mae = 0.0
            e.mfe = 0.0
            e.exit_price = None
            e.exit_mid = None
            e.exit_timestamp = None
            e.exit_point_score = ""
            e.exit_reason_str = ""
            e.post_exit_ticks = []
            e.log_sent = False
            return "reentry"

        return None

    def tick_position(
        self,
        match_id: str,
        player: str,
        price: float | None = None,
        mid: float | None = None,
        point_score: str = "",
    ) -> None:
        e = self._get(match_id, player)
        if e.state != RuleState.IN_POSITION:
            return
        e.ticks_in_position += 1
        if price is not None and len(e.tick_history) < 2:
            e.tick_history.append((price, mid, point_score))
        if price is not None and e.entry_price is not None:
            move = price - e.entry_price
            e.mae = min(e.mae, move)
            e.mfe = max(e.mfe, move)

    _POST_EXIT_TICK_INTERVAL = 25.0  # seconds between post-exit ticks

    def tick_post_exit(
        self,
        match_id: str,
        player: str,
        price: float,
        mid: float | None,
        point_score: str = "",
    ) -> bool:
        """Collect one post-exit tick (rate-limited to ~25s apart). Returns True when 2 ticks collected."""
        e = self._get(match_id, player)
        if e.state != RuleState.WATCHING_REENTRY:
            return False
        if e.log_sent or len(e.post_exit_ticks) >= 2:
            return False
        now = datetime.now(timezone.utc)
        if e.last_post_exit_tick_at is not None:
            elapsed = (now - e.last_post_exit_tick_at).total_seconds()
            if elapsed < self._POST_EXIT_TICK_INTERVAL:
                return False
        e.post_exit_ticks.append((price, mid, point_score))
        e.last_post_exit_tick_at = now
        return len(e.post_exit_ticks) >= 2

    def mark_log_sent(self, match_id: str, player: str) -> None:
        self._get(match_id, player).log_sent = True

    def get_exit_context(self, match_id: str, player: str) -> dict:
        e = self._get(match_id, player)
        return {
            "entry_price":        e.entry_price,
            "updates_since_entry": e.ticks_in_position,
        }

    def get_position_stats(self, match_id: str, player: str) -> dict:
        e = self._get(match_id, player)
        return {
            "entry_price":      e.entry_price,
            "entry_timestamp":  e.entry_timestamp,
            "entry_state":      e.entry_state,
            "entry_spread":     e.entry_spread,
            "price_after_tick": [t[0] for t in e.tick_history],
        }

    def get_log_data(self, match_id: str, player: str) -> dict:
        e = self._get(match_id, player)
        return {
            "entry_price":       e.entry_price,
            "entry_mid":         e.entry_mid,
            "entry_timestamp":   e.entry_timestamp,
            "entry_point_score": e.entry_point_score,
            "entry_spread":      e.entry_spread,
            "tick_history":      list(e.tick_history),
            "mae":               e.mae,
            "mfe":               e.mfe,
            "exit_price":        e.exit_price,
            "exit_mid":          e.exit_mid,
            "exit_timestamp":    e.exit_timestamp,
            "exit_point_score":  e.exit_point_score,
            "exit_reason_str":   e.exit_reason_str,
            "post_exit_ticks":   list(e.post_exit_ticks),
        }

    # ------------------------------------------------------------------

    def cleanup(self, active_match_ids: set[str]) -> None:
        dead = [k for k in self._data if k[0] not in active_match_ids]
        for k in dead:
            del self._data[k]
