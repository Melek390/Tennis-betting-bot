from dataclasses import dataclass
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
    ) -> str | None:
        """
        Returns "entry", "exit", "reentry", or None.
        PENDING states are sticky — no signal fires until user responds.
        """
        e = self._get(match_id, player, rule)

        if e.state == RuleState.WATCHING and entry_met:
            e.state = RuleState.PENDING_ENTRY
            return "entry"

        if e.state == RuleState.IN_POSITION and exit_met:
            e.state = RuleState.PENDING_EXIT
            return "exit"

        if e.state == RuleState.WATCHING_REENTRY and entry_met:
            e.state = RuleState.PENDING_REENTRY
            return "reentry"

        return None

    # ------------------------------------------------------------------
    # User-action transitions — called from Telegram button callbacks
    # ------------------------------------------------------------------

    def confirm_entry(self, match_id: str, player: str, rule: int) -> None:
        e = self._get(match_id, player, rule)
        if e.state == RuleState.PENDING_ENTRY:
            e.state = RuleState.IN_POSITION

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

    def skip_reentry(self, match_id: str, player: str, rule: int) -> None:
        e = self._get(match_id, player, rule)
        if e.state == RuleState.PENDING_REENTRY:
            e.state = RuleState.WATCHING_REENTRY

    # ------------------------------------------------------------------

    def cleanup(self, active_match_ids: set[str]) -> None:
        dead = [k for k in self._data if k[0] not in active_match_ids]
        for k in dead:
            del self._data[k]
