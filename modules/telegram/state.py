from dataclasses import dataclass

STATE_KEY     = "bot_state"
STATE_MGR_KEY = "state_mgr"


@dataclass
class BotState:
    enabled: bool = True    # Rule 1 on/off
    enabled_r2: bool = True # Rule 2 on/off
    enabled_r3: bool = True # Rule 3 on/off
