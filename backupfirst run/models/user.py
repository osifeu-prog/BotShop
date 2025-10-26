from dataclasses import dataclass, field
from typing import Optional
import time

def _now() -> int: return int(time.time())

@dataclass
class User:
    chat_id: int
    paid: bool = False
    wallet: str = ""
    joined_at: int = field(default_factory=_now)

@dataclass
class Balance:
    slh: float = 0.0
    bnb: float = 0.0

    def add(self, slh: float=0.0, bnb: float=0.0):
        self.slh = round(self.slh + slh, 8)
        self.bnb = round(self.bnb + bnb, 8)