from dataclasses import dataclass, field
from enum import Enum
import time

class OrderType(str, Enum):
    BUY="buy"; SELL="sell"; TRANSFER="transfer"

@dataclass
class Order:
    id: int
    type: OrderType
    frm: int
    to: int
    amount: float
    asset: str = "SLH"
    status: str = "open"
    ts: int = field(default_factory=lambda: int(time.time()))