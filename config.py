import os
from typing import Dict, Any
from dotenv import load_dotenv

load_dotenv()

class Config:
    """System-wide configuration and env bindings"""

    # Telegram Bot
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    BOT_USERNAME = os.getenv("BOT_USERNAME", "Buy_My_Shop_bot")
    WEBHOOK_URL = os.getenv("WEBHOOK_URL")

    # Database
    DATABASE_URL = os.getenv("DATABASE_URL")
    DATABASE_PUBLIC_URL = os.getenv("DATABASE_PUBLIC_URL")  # optional, for read-only/public
    DATABASE_POOL_SIZE = int(os.getenv("DATABASE_POOL_SIZE", "10"))

    # API & Web
    SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here")
    ADMIN_DASH_TOKEN = os.getenv("ADMIN_DASH_TOKEN", "changeme-admin-dash")
    CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
    LANDING_URL = os.getenv("LANDING_URL", "https://slh-nft.com/")

    # Community & Support Links
    COMMUNITY_GROUP_LINK = os.getenv("COMMUNITY_GROUP_LINK")
    SUPPORT_GROUP_LINK = os.getenv("SUPPORT_GROUP_LINK")

    # Payment Links
    PAYMENT_LINKS: Dict[str, str] = {
        "paybox": os.getenv("PAYBOX_URL", ""),
        "bit": os.getenv("BIT_URL", ""),
        "paypal": os.getenv("PAYPAL_URL", ""),
    }

    # Media / Assets
    START_IMAGE_PATH = os.getenv("START_IMAGE_PATH", "assets/start_banner.jpg")

    # Payment Settings
    PAYMENT_SETTINGS: Dict[str, Any] = {
        'default_currency': 'ILS',
        'commission_rates': {
            'direct': 0.10,
            'level_2': 0.05,
            'level_3': 0.02,
        },
        'min_payout': 50,
        'payout_schedule': 'weekly',
    }

    # Asset Tiers
    ASSET_TIERS: Dict[str, Any] = {
        'basic': {
            'name': 'נכס בסיסי',
            'price': 39,
            'features': ['לינק אישי', 'דשבורד בסיסי', 'הפניות 3 רמות'],
            'max_assets': 1,
        },
        'premium': {
            'name': 'נכס פרמיום',
            'price': 99,
            'features': ['בוט אישי', 'דשבורד מתקדם', 'ניתוחים'],
            'max_assets': 3,
        },
        'business': {
            'name': 'נכס עסקי',
            'price': 199,
            'features': ['ניהול צוות', 'API גישה', 'אנליטיקס מתקדם'],
            'max_assets': 10,
        },
        'enterprise': {
            'name': 'נכס ארגוני',
            'price': 499,
            'features': ['צוות מלא', 'ליווי אסטרטגי', 'הטבות בלעדיות'],
            'max_assets': 999,
        },
    }

    # Blockchain
    BLOCKCHAIN_SETTINGS: Dict[str, Any] = {
        'network': os.getenv("BLOCKCHAIN_NETWORK", "bsc-testnet"),
        'slh_token_address': os.getenv("SLH_TOKEN_ADDRESS"),
        'web3_provider': os.getenv("WEB3_PROVIDER", "https://bsc-dataseed.binance.org/"),
        'ton_wallet_address': os.getenv("TON_WALLET_ADDRESS"),
    }

    # Notifications
    NOTIFICATION_SETTINGS: Dict[str, Any] = {
        'telegram_log_chat': os.getenv("TELEGRAM_LOG_CHAT", "-1001748319682"),
        'support_chat': os.getenv("SUPPORT_CHAT", "-1001748319682"),
        'email_enabled': os.getenv("EMAIL_ENABLED", "false").lower() == "true",
        'community_group_link': os.getenv("COMMUNITY_GROUP_LINK"),
        'support_group_link': os.getenv("SUPPORT_GROUP_LINK"),
    }

    # Analytics
    ANALYTICS_SETTINGS: Dict[str, Any] = {
        'track_performance': True,
        'calculate_roi': True,
        'predictive_analytics': True,
    }

config = Config()
