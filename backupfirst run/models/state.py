from dataclasses import dataclass, field
from enum import Enum, auto
import time
from typing import Dict, Any

class UserStateType(Enum):
    IDLE = auto()
    AWAIT_WALLET = auto()
    AWAIT_BUY_AMOUNT = auto()
    AWAIT_SELL_AMOUNT = auto()
    AWAIT_TRANSFER_TO = auto()
    AWAIT_TRANSFER_AMOUNT = auto()

@dataclass
class UserState:
    t: UserStateType = UserStateType.IDLE
    data: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)