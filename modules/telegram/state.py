from dataclasses import dataclass

STATE_KEY     = "bot_state"
STATE_MGR_KEY = "state_mgr"


@dataclass
class BotState:
    enabled: bool = True   # Rule 5 on/off
