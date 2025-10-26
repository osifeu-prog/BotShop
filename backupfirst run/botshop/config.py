import os, logging

def parse_admins(raw: str) -> set[int]:
    s = set()
    for part in (raw or "").replace(";",",").replace(" ","").split(","):
        if part.isdigit(): s.add(int(part))
    return s

class Config:
    def __init__(self) -> None:
        self.token = os.getenv("TELEGRAM_BOT_TOKEN","").strip()
        self.log_level = os.getenv("LOG_LEVEL","INFO").upper()
        self.admin_ids = parse_admins(os.getenv("ADMIN_IDS",""))
        self.admin_name = os.getenv("ADMIN_NAME","Admin")
        self.entry_price_nis = float(os.getenv("ENTRY_PRICE_NIS","39") or 39)
        self.demo_grant_slh = float(os.getenv("DEMO_GRANT_SLH","39") or 39)
        self.demo_grant_bnb = float(os.getenv("DEMO_GRANT_BNB","0.05") or 0.05)
        self.store_path = os.getenv("STORE_PATH","/data/store.json")
        self.group_chat_id = os.getenv("GROUP_CHAT_ID","")
        self.group_invite_link = os.getenv("GROUP_INVITE_LINK","")
        if not self.token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is missing")

def setup_logging(level: str = "INFO"):
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )