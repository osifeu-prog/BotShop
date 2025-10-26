import os
from dataclasses import dataclass
from typing import List

@dataclass
class Config:
    token: str
    admin_ids: List[int]
    admin_name: str
    store_path: str
    entry_price_nis: float
    demo_grant_slh: float
    demo_grant_bnb: float
    payment_link_base: str
    group_chat_id: int
    group_invite_link: str
    tz: str

    @staticmethod
    def from_env() -> "Config":
        token = os.getenv("TELEGRAM_BOT_TOKEN","").strip()
        if not token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN missing")
        ids = [int(x) for x in (os.getenv("ADMIN_IDS","").replace(";",
               ",").split(",") if os.getenv("ADMIN_IDS") else []) if x.strip().isdigit()]
        if not ids:
            raise RuntimeError("ADMIN_IDS missing")
        return Config(
            token=token,
            admin_ids=ids,
            admin_name=os.getenv("ADMIN_NAME","Admin"),
            store_path=os.getenv("STORE_PATH","/data/store.json"),
            entry_price_nis=float(os.getenv("ENTRY_PRICE_NIS","39")),
            demo_grant_slh=float(os.getenv("DEMO_GRANT_SLH","39")),
            demo_grant_bnb=float(os.getenv("DEMO_GRANT_BNB","0.05")),
            payment_link_base=os.getenv("PAYMENT_LINK_BASE","https://pay.example.com/checkout").strip(),
            group_chat_id=int(os.getenv("GROUP_CHAT_ID","0") or 0),
            group_invite_link=os.getenv("GROUP_INVITE_LINK","").strip(),
            tz=os.getenv("TZ","Asia/Jerusalem"),
        )