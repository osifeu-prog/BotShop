
import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
BOT_USERNAME = os.getenv("BOT_USERNAME", "Buy_My_Shop_bot")

WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")

DATABASE_URL = os.getenv("DATABASE_URL", "")

# Telegram groups / channels
# Must be numeric chat IDs (e.g. -1001234567890)
ADMIN_LOGS_CHAT_ID = int(os.getenv("ADMIN_LOGS_CHAT_ID", "0") or "0")
SUPPORT_GROUP_CHAT_ID = int(os.getenv("SUPPORT_GROUP_CHAT_ID", "0") or "0")

# Public invite links (only shown to users)
BUSINESS_GROUP_URL = os.getenv("BUSINESS_GROUP_URL", "")
SUPPORT_GROUP_URL = os.getenv("SUPPORT_GROUP_URL", "")

# Payment & business config
SLH_NIS = float(os.getenv("SLH_NIS", "39"))
BIT_URL = os.getenv("BIT_URL", "")
PAYBOX_URL = os.getenv("PAYBOX_URL", "")
PAYPAL_URL = os.getenv("PAYPAL_URL", "")

LANDING_URL = os.getenv("LANDING_URL", "https://slh-nft.com")

DEFAULT_LANG = os.getenv("DEFAULT_LANG", "he")
