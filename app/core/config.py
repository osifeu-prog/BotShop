import os
from functools import lru_cache
from typing import List

class Settings:
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_ADMIN_IDS: List[int]
    DATABASE_URL: str
    SERVICE_NAME: str
    WEBHOOK_BASE_URL: str
    WEBHOOK_PATH: str
    LOG_LEVEL: str

    def __init__(self) -> None:
        self.TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not self.TELEGRAM_BOT_TOKEN:
            raise RuntimeError("TELEGRAM_BOT_TOKEN env var is required")

        admin_raw = os.getenv("TELEGRAM_ADMIN_IDS", "").strip()
        self.TELEGRAM_ADMIN_IDS = []
        if admin_raw:
            for part in admin_raw.split(","):
                part = part.strip()
                if not part:
                    continue
                try:
                    self.TELEGRAM_ADMIN_IDS.append(int(part))
                except ValueError:
                    pass

        self.DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
        if not self.DATABASE_URL:
            raise RuntimeError("DATABASE_URL env var is required (Railway Postgres URL)")

        self.SERVICE_NAME = os.getenv("SERVICE_NAME", "botshop").strip()
        self.WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "").strip()
        self.WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "telegram/webhook").strip()
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

@lru_cache()
def get_settings() -> Settings:
    return Settings()
