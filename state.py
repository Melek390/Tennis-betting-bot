from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class RuleState(Enum):
    WATCHING          = "watching"
    PENDING_ENTRY     = "pending_entry"
    IN_POSITION       = "in_position"
    PENDING_EXIT      = "pending_exit"
    WATCHING_REENTRY  = "watching_reentry"
    PENDING_REENTRY   = "pending_reentry"


@dataclass
class _Entry:
    state: RuleState = RuleState.WATCHING
    entry_price: float | None = None
    entry_timestamp: datetime | None = None
    entry_state: str = ""
    entry_spread: float | None = None
    position_confirmed_at: datetime | None = None  # when user pressed "Confirmed entry"
    ticks_in_position: int = 0
    no_pressure_ticks: int = 0
    price_after_tick: list = field(default_factory=list)


# (match_id, player_side, rule_number) → _Entry
_StateKey = tuple[str, str, int]


class StateManager:
    def __init__(self):
        self._data: dict[_StateKey, _Entry] = {}

    def _get(self, match_id: str, player: str, rule: int) -> _Entry:
        return self._data.setdefault((match_id, player, rule), _Entry())

    # ------------------------------------------------------------------
    # Called on every WebSocket update — drives the monitoring signals
    # ------------------------------------------------------------------

    def process(
        self,
        match_id: str,
        player: str,
        rule: int,
        entry_met: bool,
        exit_met: bool,
        price: float | None = None,
        entry_state: str = "",
        entry_spread: float | None = None,
    ) -> str | None:
        """
        Returns "entry", "exit", "reentry", or None.
        PENDING states are sticky — no signal fires until user responds.
        """
        e = self._get(match_id, player, rule)

        if e.state == RuleState.WATCHING and entry_met:
            e.state = RuleState.PENDING_ENTRY
            e.entry_price = price
            e.entry_timestamp = datetime.now(timezone.utc)
            e.entry_state = entry_state
            e.entry_spread = entry_spread
            e.price_after_tick = []
            return "entry"

        if e.state == RuleState.IN_POSITION and exit_met:
            e.state = RuleState.PENDING_EXIT
            return "exit"

        if e.state == RuleState.WATCHING_REENTRY and entry_met:
            e.state = RuleState.PENDING_REENTRY
            e.entry_price = price
            e.entry_timestamp = datetime.now(timezone.utc)
            e.entry_state = entry_state
            e.entry_spread = entry_spread
            e.price_after_tick = []
            return "reentry"

        return None

    # ------------------------------------------------------------------
    # User-action transitions — called from Telegram button callbacks
    # ------------------------------------------------------------------

    def confirm_entry(self, match_id: str, player: str, rule: int) -> None:
        e = self._get(match_id, player, rule)
        if e.state == RuleState.PENDING_ENTRY:
            e.state = RuleState.IN_POSITION
            e.position_confirmed_at = datetime.now(timezone.utc)
            e.ticks_in_position = 0
            e.no_pressure_ticks = 0

    def skip_entry(self, match_id: str, player: str, rule: int) -> None:
        e = self._get(match_id, player, rule)
        if e.state == RuleState.PENDING_ENTRY:
            e.state = RuleState.WATCHING

    def confirm_exit(self, match_id: str, player: str, rule: int) -> None:
        e = self._get(match_id, player, rule)
        if e.state == RuleState.PENDING_EXIT:
            e.state = RuleState.WATCHING_REENTRY

    def keep_position(self, match_id: str, player: str, rule: int) -> None:
        e = self._get(match_id, player, rule)
        if e.state == RuleState.PENDING_EXIT:
            e.state = RuleState.IN_POSITION

    def confirm_reentry(self, match_id: str, player: str, rule: int) -> None:
        e = self._get(match_id, player, rule)
        if e.state == RuleState.PENDING_REENTRY:
            e.state = RuleState.IN_POSITION
            e.position_confirmed_at = datetime.now(timezone.utc)
            e.ticks_in_position = 0
            e.no_pressure_ticks = 0

    def skip_reentry(self, match_id: str, player: str, rule: int) -> None:
        e = self._get(match_id, player, rule)
        if e.state == RuleState.PENDING_REENTRY:
            e.state = RuleState.WATCHING_REENTRY

    def tick_position(
        self, match_id: str, player: str, rule: int, has_pressure: bool, price: float | None = None
    ) -> None:
        """Increment per-position counters. Only acts when IN_POSITION."""
        e = self._get(match_id, player, rule)
        if e.state != RuleState.IN_POSITION:
            return
        e.ticks_in_position += 1
        if price is not None and len(e.price_after_tick) < 2:
            e.price_after_tick.append(price)
        if has_pressure:
            e.no_pressure_ticks = 0
        else:
            e.no_pressure_ticks += 1

    def get_exit_context(self, match_id: str, player: str, rule: int) -> dict:
        """Return position context needed by rule exit conditions."""
        e = self._get(match_id, player, rule)
        if e.position_confirmed_at is not None:
            elapsed = (datetime.now(timezone.utc) - e.position_confirmed_at).total_seconds()
        else:
            elapsed = 0.0
        return {
            "entry_price":      e.entry_price,
            "elapsed_seconds":  elapsed,
            "no_pressure_ticks": e.no_pressure_ticks,
        }

    def get_position_stats(self, match_id: str, player: str, rule: int) -> dict:
        """Return full entry stats for display in the exit alert."""
        e = self._get(match_id, player, rule)
        return {
            "entry_price":     e.entry_price,
            "entry_timestamp": e.entry_timestamp,
            "entry_state":     e.entry_state,
            "entry_spread":    e.entry_spread,
            "price_after_tick": list(e.price_after_tick),
        }

    # ------------------------------------------------------------------

    def cleanup(self, active_match_ids: set[str]) -> None:
        dead = [k for k in self._data if k[0] not in active_match_ids]
        for k in dead:
            del self._data[k]
