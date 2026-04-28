from dataclasses import dataclass, field

STATE_KEY    = "bot_state"
STATE_MGR_KEY = "state_mgr"


@dataclass
class BotState:
    enabled_rules: dict[int, bool] = field(
        default_factory=lambda: {1: True, 2: True, 3: True, 4: True, 5: True, 6: True, 7: True}
    )
