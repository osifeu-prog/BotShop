from telegram.ext import MessageHandler, filters, CallbackQueryHandler
import os
import json
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from pathlib import Path
from typing import Optional, Dict, Any, List
from decimal import Decimal, InvalidOperation

from db import init_schema, get_approval_stats, get_monthly_payments, get_reserve_stats
from slh_internal_wallets import (
    init_internal_wallet_schema,
    ensure_internal_wallet,
    get_wallet_overview,
    transfer_between_users,
    create_stake_position,
    get_user_stakes,
    mint_slh_from_payment,
)

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, Response, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from decimal import Decimal, InvalidOperation

from slh_internal_wallets import (
    init_internal_wallet_schema,
    ensure_internal_wallet,
    get_wallet_overview,
    get_user_stakes,
    create_stake_position,
)

from pydantic import BaseModel

from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from fastapi.middleware.cors import CORSMiddleware

from telegram import Update
try:
    from slh_public_api import router as public_router
except Exception:
    public_router = None
try:
    from social_api import router as social_router
except Exception:
    social_router = None
try:
    from slh_core_api import router as core_router
except Exception:
    core_router = None
try:
    from slhnet_extra import router as slhnet_extra_router
except Exception:
    slhnet_extra_router = None

from telegram.ext import CommandHandler, ContextTypes, Application

# =========================
# קונפיגורציית לוגינג משופרת
# =========================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("slhnet_bot.log", encoding='utf-8')
    ]
)
logger = logging.getLogger("slhnet")

# =========================
# FastAPI app
# =========================
app = FastAPI(
    title="SLHNET Gateway Bot",
    description="בוט קהילה ושער API עבור SLHNET",
    version="2.0.0"
)

# CORS – מאפשר גישה לדשבורד מהדומיין slh-nft.com
allowed_origins = [
    os.getenv("FRONTEND_ORIGIN", "").rstrip("/") or "https://slh-nft.com",
    "https://slh-nft.com",
    "https://www.slh-nft.com",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# אתחול סכמת בסיס הנתונים (טבלאות + רזרבות 49%) + ארנקים פנימיים וסטייקינג
try:
    init_schema()
    init_internal_wallet_schema()
except Exception as e:
    logger.warning(f"init_schema or init_internal_wallet_schema failed: {e}")

BASE_DIR = Path(__file__).resolve().parent

# סטטיק וטמפלטס עם הגנות
try:
    static_dir = BASE_DIR / "static"
    templates_dir = BASE_DIR / "templates"
    
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    else:
        logger.warning("Static directory not found, skipping static files")
    
    if templates_dir.exists():
        templates = Jinja2Templates(directory=str(templates_dir))
    else:
        logger.warning("Templates directory not found, Jinja2 templates disabled")
        templates = None
except Exception as e:
    logger.error(f"Error setting up static/templates: {e}")
    templates = None


# רואטרים של API עם הגנות
try:
    if public_router is not None:
        app.include_router(public_router, prefix="/api/public", tags=["public"])
    if social_router is not None:
        app.include_router(social_router, prefix="/api/social", tags=["social"])
    if core_router is not None:
        app.include_router(core_router, prefix="/api/core", tags=["core"])
    if slhnet_extra_router is not None:
        app.include_router(slhnet_extra_router, prefix="/api/extra", tags=["extra"])
except Exception as e:
    logger.error(f"Error including routers: {e}")


# =========================
# ניהול referral משופר
# =========================
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
REF_FILE = DATA_DIR / "referrals.json"


def load_referrals() -> Dict[str, Any]:
    """טוען נתוני referrals עם הגנת שגיאות"""
    if not REF_FILE.exists():
        return {"users": {}, "statistics": {"total_users": 0}}
    
    try:
        with open(REF_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"Error loading referrals: {e}")
        return {"users": {}, "statistics": {"total_users": 0}}


def save_referrals(data: Dict[str, Any]) -> None:
    """שומר נתוני referrals עם הגנת שגיאות"""
    try:
        # עדכון סטטיסטיקות
        data["statistics"]["total_users"] = len(data["users"])
        
        with open(REF_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error saving referrals: {e}")


def register_referral(user_id: int, referrer_id: Optional[int] = None) -> bool:
    """רושם משתמש חדש עם referral"""
    try:
        data = load_referrals()
        suid = str(user_id)
        
        if suid in data["users"]:
            return False  # כבר רשום
            
        user_data = {
            "referrer": str(referrer_id) if referrer_id else None,
            "joined_at": datetime.now().isoformat(),
            "referral_count": 0
        }
        
        data["users"][suid] = user_data
        
        # עדכן סטטיסטיקת referrer אם קיים
        if referrer_id:
            referrer_str = str(referrer_id)
            if referrer_str in data["users"]:
                data["users"][referrer_str]["referral_count"] = data["users"][referrer_str].get("referral_count", 0) + 1
        
        save_referrals(data)
        logger.info(f"Registered new user {user_id} with referrer {referrer_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error registering referral: {e}")
        return False


# =========================
# ניהול הודעות משופר
# =========================
MESSAGES_FILE = BASE_DIR / "bot_messages_slhnet.txt"


def load_message_block(block_name: str, fallback: str = "") -> str:
    """
    טוען בלוק טקסט מהקובץ עם הגנות וטקסט ברירת מחדל
    """
    if not MESSAGES_FILE.exists():
        logger.warning(f"Messages file not found: {MESSAGES_FILE}")
        return fallback or f"[שגיאה: קובץ הודעות לא נמצא]"

    try:
        content = MESSAGES_FILE.read_text(encoding="utf-8")
        lines = content.splitlines()

        result_lines = []
        in_block = False
        found_block = False
        
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("===") and block_name in stripped:
                in_block = True
                found_block = True
                continue
            if in_block and stripped.startswith("=== END"):
                break
            if in_block:
                result_lines.append(line)

        if not found_block and not fallback:
            logger.warning(f"Message block '{block_name}' not found")
            return f"[שגיאה: בלוק {block_name} לא נמצא]"
            
        if not result_lines and fallback:
            return fallback
            
        return "\n".join(result_lines).strip() or fallback
        
    except Exception as e:
        logger.error(f"Error loading message block '{block_name}': {e}")
        return fallback or f"[שגיאה בטעינת בלוק {block_name}]"


# =========================
# מודלים עם ולידציה
# =========================
class TelegramWebhookUpdate(BaseModel):
    update_id: int
    message: Optional[Dict[str, Any]] = None
    callback_query: Optional[Dict[str, Any]] = None
    edited_message: Optional[Dict[str, Any]] = None


class HealthResponse(BaseModel):
    status: str
    service: str
    timestamp: str
    version: str


# =========================
# קונפיגורציה ומשתני סביבה
# =========================
class Config:
    """מחלקה לניהול קונפיגורציה"""
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    WEBHOOK_URL: str = os.getenv("WEBHOOK_URL", "")
    ADMIN_ALERT_CHAT_ID: str = os.getenv("ADMIN_ALERT_CHAT_ID", "")
    LANDING_URL: str = os.getenv("LANDING_URL", "https://slh-nft.com")
    BUSINESS_GROUP_URL: str = os.getenv("BUSINESS_GROUP_URL", "")
    GROUP_STATIC_INVITE: str = os.getenv("GROUP_STATIC_INVITE", "")
    PAYBOX_URL: str = os.getenv("PAYBOX_URL", "")
    BIT_URL: str = os.getenv("BIT_URL", "")
    PAYPAL_URL: str = os.getenv("PAYPAL_URL", "")
    START_IMAGE_PATH: str = os.getenv("START_IMAGE_PATH", "assets/start_banner.jpg")
    TON_WALLET_ADDRESS: str = os.getenv("TON_WALLET_ADDRESS", "")
    LOGS_GROUP_CHAT_ID: str = os.getenv("LOGS_GROUP_CHAT_ID", ADMIN_ALERT_CHAT_ID or "")

    @classmethod
    def validate(cls) -> List[str]:
        """בודק תקינות קונפיגורציה ומחזיר רשימת אזהרות"""
        warnings = []
        if not cls.BOT_TOKEN:
            warnings.append("⚠️ BOT_TOKEN לא מוגדר")
        if not cls.WEBHOOK_URL:
            warnings.append("⚠️ WEBHOOK_URL לא מוגדר")
        if not cls.ADMIN_ALERT_CHAT_ID:
            warnings.append("⚠️ ADMIN_ALERT_CHAT_ID לא מוגדר")
        return warnings


# =========================
# Telegram Application (singleton משופר)
# =========================
class TelegramAppManager:
    """מנהל אפליקציית הטלגרם"""
    _instance: Optional[Application] = None
    _initialized: bool = False

    @classmethod
    def get_app(cls) -> Application:
        if cls._instance is None:
            if not Config.BOT_TOKEN:
                raise RuntimeError("BOT_TOKEN is not set")
            
            cls._instance = Application.builder().token(Config.BOT_TOKEN).build()
            logger.info("Telegram Application instance created")
            
        return cls._instance

    @classmethod
    def initialize_handlers(cls) -> None:
        """מאתחל handlers פעם אחת בלבד"""
        if cls._initialized:
            return
            
        app_instance = cls.get_app()
        
        # רישום handlers
        handlers = [
            CommandHandler("start", start_command),
            CommandHandler("whoami", whoami_command),
            CommandHandler("stats", stats_command),
            CommandHandler("wallet", wallet_command),
            CommandHandler("send_slh", send_slh_command),
            CommandHandler("stake", stake_command),
            CommandHandler("mystakes", mystakes_command),
            CallbackQueryHandler(callback_query_handler),
            MessageHandler(filters.TEXT & ~filters.COMMAND, echo_message),
            MessageHandler(filters.COMMAND, unknown_command),
        ]
        
        for handler in handlers:
            app_instance.add_handler(handler)
            
        cls._initialized = True
        logger.info("Telegram handlers initialized")
    @classmethod
    async def start(cls) -> None:
        """אתחול מלא של אפליקציית הטלגרם + Webhook"""
        # רישום handlers פעם אחת
        cls.initialize_handlers()
        app_instance = cls.get_app()
        if not getattr(cls, "_started", False):
            await app_instance.initialize()
            await app_instance.start()
            try:
                if Config.WEBHOOK_URL:
                    await app_instance.bot.set_webhook(Config.WEBHOOK_URL)
                    logger.info(f"Webhook set to {Config.WEBHOOK_URL}")
            except Exception as e:
                logger.error(f"Failed to set webhook: {e}")
            cls._started = True
            logger.info("Telegram Application started")

    @classmethod
    async def shutdown(cls) -> None:
        """עצירת האפליקציה בצורה נקייה"""
        try:
            app_instance = cls.get_app()
            await app_instance.stop()
            await app_instance.shutdown()
        except Exception as e:
            logger.error(f"Error during Telegram shutdown: {e}")


# =========================
# utilities משופרות
# =========================

def build_payment_instructions() -> str:
    """בונה טקסט מסודר לכל אפשרויות התשלום והוראות שליחת האישור"""
    bank_details = (
        "🏦 *העברה בנקאית:*\n"
        "בנק הפועלים\n"
        "סניף כפר גנים (153)\n"
        "חשבון 73462\n"
        "המוטב: קאופמן צביקה\n\n"
    )

    parts = [bank_details]

    if Config.PAYBOX_URL:
        parts.append(f"📲 *PayBox*: [לינק לתשלום]({Config.PAYBOX_URL})\n")
    if Config.BIT_URL:
        parts.append(f"📲 *Bit*: [לינק לתשלום]({Config.BIT_URL})\n")
    if Config.PAYPAL_URL:
        parts.append(f"🌍 *PayPal*: [לינק לתשלום]({Config.PAYPAL_URL})\n")
    if getattr(Config, "TON_WALLET_ADDRESS", ""):
        parts.append(f"🔐 *ארנק TON*: `{Config.TON_WALLET_ADDRESS}`\n")

    footer = (
        "\nלאחר התשלום, שלח צילום מסך של האישור כאן בבוט, "
        "והמערכת תעביר אותו אוטומטית לאישור אצלנו.\n"
        "אחרי האישור תקבל קישור לקבוצת העסקים + גישה לכל הכלים הדיגיטליים."
    )

    parts.append(footer)
    return "".join(parts)


def build_payment_instructions() -> str:
    """בונה טקסט מסודר לכל אפשרויות התשלום והוראות שליחת האישור"""
    bank_details = (
        "🏦 *העברה בנקאית:*\n"
        "בנק הפועלים\\n"
        "סניף כפר גנים (153)\\n"
        "חשבון 73462\\n"
        "המוטב: קאופמן צביקה\n\n"
    )

    parts = [bank_details]

    if Config.PAYBOX_URL:
        parts.append(f"📲 *PayBox*: [לינק לתשלום]({Config.PAYBOX_URL})\n")
    if Config.BIT_URL:
        parts.append(f"📲 *Bit*: [לינק לתשלום]({Config.BIT_URL})\n")
    if Config.PAYPAL_URL:
        parts.append(f"🌍 *PayPal*: [לינק לתשלום]({Config.PAYPAL_URL})\n")
    if getattr(Config, "TON_WALLET_ADDRESS", ""):
        parts.append(f"🔐 *ארנק TON*: `{Config.TON_WALLET_ADDRESS}`\n")

    footer = (
        "\nלאחר התשלום, שלח צילום מסך של האישור כאן בבוט, "
        "והמערכת תעביר אותו אוטומטית לאישור אצלנו.\n"
        "אחרי האישור תקבל קישור לקבוצת העסקים + גישה לכל הכלים הדיגיטליים."
    )

    parts.append(footer)
    return "".join(parts)

async def send_log_message(text: str) -> None:
    """שולח הודעת לוג עם הגנות"""
    if not Config.LOGS_GROUP_CHAT_ID:
        logger.warning("LOGS_GROUP_CHAT_ID not set; skipping log message")
        return
        
    try:
        app_instance = TelegramAppManager.get_app()
        await app_instance.bot.send_message(
            chat_id=int(Config.LOGS_GROUP_CHAT_ID), 
            text=text
        )
    except Exception as e:
        logger.error(f"Failed to send log message: {e}")


def safe_get_url(url: str, fallback: str) -> str:
    """מחזיר URL עם הגנות"""
    return url if url and url.startswith(('http://', 'https://')) else fallback


# =========================
# handlers משופרים
# =========================


async def send_start_screen(update: Update, context: ContextTypes.DEFAULT_TYPE, referrer: Optional[int] = None) -> None:
    """מציג מסך start עם כל אפשרויות התשלום וההצטרפות"""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        logger.error("No user or chat in update")
        return

    # רישום referral
    register_referral(user.id, referrer)

    # טעינת הודעות עם ברירת מחדל
    title = load_message_block("START_TITLE", "🚀 ברוך הבא ל-SLHNET!")
    body = load_message_block(
        "START_BODY",
        (
            "ברוך הבא לשער הדיגיטלי של קהילת SLHNET.\n"
            "כאן אתה מצטרף לקהילת עסקים, מקבל גישה לארנקים, חוזים חכמים, "
            "NFT וקבלת תשלומים – הכל סביב תשלום חד־פעמי של *39 ₪*."
        ),
    )

    # שליחת תמונה עם הגנות
    image_path = BASE_DIR / Config.START_IMAGE_PATH
    try:
        if image_path.exists() and image_path.is_file():
            with image_path.open("rb") as f:
                await chat.send_photo(photo=InputFile(f), caption=title)
        else:
            logger.warning(f"Start image not found: {image_path}")
            await chat.send_message(text=title)
    except Exception as e:
        logger.error(f"Error sending start image: {e}")
        await chat.send_message(text=title)

    # כפתורי פעולה
    pay_url = safe_get_url(Config.PAYBOX_URL, Config.LANDING_URL + "#join39")

    keyboard = [
        [InlineKeyboardButton("💳 תשלום 39 ₪ – PayBox", url=pay_url)],
        [InlineKeyboardButton("📤 איך לשלם ולשלוח אישור", callback_data="send_proof")],
        [InlineKeyboardButton("ℹ️ מה אני מקבל?", callback_data="info_benefits")],
        [InlineKeyboardButton("📈 מידע למשקיעים", callback_data="open_investor")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await chat.send_message(text=body, reply_markup=reply_markup, parse_mode="Markdown")

    # לוגים
    log_text = (
        f"📥 משתמש חדש הפעיל את הבוט\n"
        f"👤 User ID: {user.id}\n"
        f"📛 Username: @{user.username or 'לא מוגדר'}\n"
        f"🔰 שם: {user.full_name}\n"
        f"🔄 Referrer: {referrer or 'לא צוין'}"
    )
    await send_log_message(log_text)
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """פקודת start עם referral"""
    referrer = None
    if context.args:
        try:
            referrer = int(context.args[0])
            logger.info(f"Start command with referrer: {referrer}")
        except (ValueError, TypeError):
            logger.warning(f"Invalid referrer ID: {context.args[0]}")

    await send_start_screen(update, context, referrer=referrer)


async def whoami_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """פקודת whoami משופרת"""
    user = update.effective_user
    chat = update.effective_chat

    if not user:
        await chat.send_message("❌ לא זיהיתי משתמש.")
        return

    # מידע נוסף מהרפר�rals
    referrals_data = load_referrals()
    user_ref_data = referrals_data["users"].get(str(user.id), {})
    
    text = (
        f"👤 **פרטי המשתמש שלך:**\n"
        f"🆔 ID: `{user.id}`\n"
        f"📛 שם משתמש: @{user.username or 'לא מוגדר'}\n"
        f"🔰 שם מלא: {user.full_name}\n"
        f"🔄 מספר הפניות: {user_ref_data.get('referral_count', 0)}\n"
        f"📅 הצטרף: {user_ref_data.get('joined_at', 'לא ידוע')}"
    )
    
    await chat.send_message(text=text, parse_mode="Markdown")


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """פקודת stats חדשה - סטטיסטיקות"""
    user = update.effective_user
    chat = update.effective_chat

    if not user:
        return

    referrals_data = load_referrals()
    stats = referrals_data.get("statistics", {})
    
    text = (
        f"📊 **סטטיסטיקות קהילה:**\n"
        f"👥 סה״כ משתמשים: {stats.get('total_users', 0)}\n"
        f"📈 משתמשים פעילים: {len(referrals_data.get('users', {}))}\n"
        f"🔄 הפניות כוללות: {sum(u.get('referral_count', 0) for u in referrals_data.get('users', {}).values())}"
    )
    
    await chat.send_message(text=text, parse_mode="Markdown")





# =========================
# ארנק פנימי וסטייקינג – פקודות טלגרם
# =========================

STAKING_DEFAULT_APY = Decimal(os.getenv("STAKING_DEFAULT_APY", "20"))
STAKING_DEFAULT_DAYS = int(os.getenv("STAKING_DEFAULT_DAYS", "90"))

async def wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """מציג את ארנק ה-SLH הפנימי ומצבי הסטייקינג של המשתמש."""
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return

    try:
        # וידוא קיום ארנק
        ensure_internal_wallet(user.id, user.username or None)
        overview = get_wallet_overview(user.id) or {}
        stakes = get_user_stakes(user.id) or []
    except Exception as e:
        logger.error(f"wallet_command error: {e}")
        await chat.send_message(
            "❌ לא ניתן לטעון את ארנק ה-SLH כרגע. נסה שוב מאוחר יותר."
        )
        return

    balance = overview.get("balance_slh", 0)
    wallet_id = overview.get("wallet_id", "?")

    stakes_lines: List[str] = []
    total_staked = Decimal("0")
    for s in stakes:
        amt = s.get("amount_slh") or Decimal("0")
        total_staked += Decimal(str(amt))
        pos_id = s.get("id", "?")
        apy = s.get("apy", "?")
        lock_days = s.get("lock_days", "?")
        stakes_lines.append(
            f"• #{pos_id}: {amt} SLH | APY {apy}% | {lock_days} ימים נעילה"
        )

    if not stakes_lines:
        stakes_text = "אין לך עדיין עמדות סטייקינג פעילות."
    else:
        stakes_text = "\n".join(stakes_lines)

    msg = (
        "💼 *ארנק SLH פנימי*\n\n"
        f"🆔 ID ארנק: `{wallet_id}`\n"
        f"💰 יתרה זמינה: *{balance}* SLH\n"
        f"🔒 סה״כ בסטייקינג: {total_staked} SLH\n\n"
        "כדי לפתוח סטייקינג חדש:\n"
        "*/stake <סכום_SLH> <ימי_נעילה>* לדוגמה:\n"
        "`/stake 100 30` – סטייקינג על 100 SLH ל-30 ימים.\n\n"
        "מצבי סטייקינג:\n"
        f"{stakes_text}"
    )

    await chat.send_message(text=msg, parse_mode="Markdown")


async def stake_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """פותח עמדת סטייקינג חדשה על בסיס ארנק פנימי."""
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return

    args = context.args or []
    if len(args) < 2:
        help_text = (
            "כדי לפתוח סטייקינג השתמש:\n"
            "*/stake <סכום_SLH> <ימי_נעילה>* לדוגמה:\n"
            "`/stake 100 30` – סטייקינג על 100 SLH ל-30 ימים.\n\n"
            "לפני כן ודא שיש לך יתרה בארנק דרך הפקודה /wallet."
        )
        await chat.send_message(help_text, parse_mode="Markdown")
        return

    try:
        amount_slh = Decimal(str(args[0]).replace(",", "."))
        lock_days = int(args[1])
    except (InvalidOperation, ValueError):
        await chat.send_message(
            "❌ פורמט לא תקין. נסה שוב: `/stake 100 30`.",
            parse_mode="Markdown",
        )
        return

    if amount_slh <= 0 or lock_days <= 0:
        await chat.send_message(
            "❌ הסכום וימי הנעילה חייבים להיות חיוביים."
        )
        return

    try:
        apy_percent = Decimal(os.getenv("INTERNAL_STAKING_APY", "15"))  # 15% ברירת מחדל
    except InvalidOperation:
        apy_percent = Decimal("15")

    ok, message = create_stake_position(
        user_id=user.id,
        amount_slh=amount_slh,
        apy=apy_percent,
        lock_days=lock_days,
    )

    await chat.send_message(message)


async def wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """מציג למשתמש את מצב הארנק הפנימי שלו."""
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return

    try:
        ensure_internal_wallet(user.id, user.username)
        wallet = get_wallet_overview(user.id)
    except Exception as e:
        logger.error(f"wallet_command error: {e}")
        await chat.send_message("❌ לא הצלחתי לטעון את הארנק שלך כרגע. נסה שוב מאוחר יותר.")
        return

    if not wallet:
        await chat.send_message("❌ לא הצלחתי לטעון את הארנק שלך כרגע.")
        return

    balance = wallet.get("balance_slh", Decimal("0"))
    balance = wallet.get("balance_slh", Decimal("0"))
    text = (
        "👛 *הארנק הדיגיטלי שלך – SLHNET*\n\n"
        f"🆔 User ID: `{user.id}`\n"
        f"📛 Username: @{user.username or 'לא מוגדר'}\n"
        f"💰 יתרה פנימית: *{balance} SLH*\n\n"
        "היתרה הפנימית משמשת כחשבון נקודות / טוקנים בתוך האקו־סיסטם שלנו.\n"
        "ניתן יהיה בעתיד לממש אותה מול החוזה החכם על רשת BSC."
    )

async def send_slh_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """מעביר SLH פנימי למשתמש אחר: /send_slh <amount> <@username|user_id>"""
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return

    if len(context.args) < 2:
        await chat.send_message("שימוש: /send_slh <amount> <@username|user_id>")
        return

    amount_str, target = context.args[0], context.args[1]
    try:
        amount = Decimal(amount_str.replace(",", "."))
    except InvalidOperation:
        await chat.send_message("סכום לא תקין. נסה שוב עם מספר תקין.")
        return

    # נסה לפענח user_id
    to_user_id = None
    if target.startswith("@"):
        # בגרסה בסיסית זו אנחנו לא ממפים username ל-ID.
        # המשתמש יכול לשלוח /chatid מהצד השני ולהעביר ID ידנית.
        await chat.send_message("בגרסה הנוכחית יש להשתמש ב-user_id מספרי, לא בשם משתמש. קבל את ה-ID מהפקודה /chatid אצל הצד השני.")
        return
    else:
        try:
            to_user_id = int(target)
        except ValueError:
            await chat.send_message("user_id חייב להיות מספרי.")
            return

    ok, msg = transfer_between_users(user.id, to_user_id, amount)
    if not ok:
        await chat.send_message(f"❌ העברה נכשלה: {msg}")
        return

    await chat.send_message(f"✅ הועברו {amount} SLH פנימיים למשתמש {to_user_id}.")

async def stake_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """פותח סטייקינג בסיסי: /stake <amount> [days]"""
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return

    if not context.args:
        await chat.send_message("שימוש: /stake <amount> [days]. ברירת מחדל ימים: "
                                f"{STAKING_DEFAULT_DAYS}, APY: {STAKING_DEFAULT_APY}%.")
        return

    amount_str = context.args[0]
    days = STAKING_DEFAULT_DAYS
    if len(context.args) >= 2:
        try:
            days = int(context.args[1])
        except ValueError:
            await chat.send_message("ערך ימים לא תקין, משתמש בברירת מחדל.")

    try:
        amount = Decimal(amount_str.replace(",", "."))
    except InvalidOperation:
        await chat.send_message("סכום לא תקין. נסה שוב עם מספר תקין.")
        return

    ok, msg = create_stake_position(user.id, amount, STAKING_DEFAULT_APY, days)
    if not ok:
        await chat.send_message(f"❌ סטייקינג נכשל: {msg}")
        return

    await chat.send_message(
        f"✅ פתחת סטייקינג על {amount} SLH ל-{days} ימים.\n"
        f"APY נוכחי: {STAKING_DEFAULT_APY}% (חישוב רווחים נעשה בעתיד לפי מנגנון מתקדם)."
    )

async def mystakes_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """מציג עמדות סטייקינג פעילות/סגורות"""
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return

    stakes = get_user_stakes(user.id)
    if not stakes:
        await chat.send_message("אין לך עדיין עמדות סטייקינג.")
        return

    lines = ["📊 *עמדות הסטייקינג שלך:*\n"]
    for st in stakes:
        status = st.get("status", "unknown")
        amount = st.get("amount_slh", Decimal("0"))
        apy = st.get("apy", Decimal("0"))
        lock_days = st.get("lock_days", 0)
        started = st.get("started_at")
        lines.append(
            f"• {amount} SLH | {apy}% | {lock_days} ימים | סטטוס: {status} | התחלה: {started}"
        )

    await chat.send_message("\n".join(lines), parse_mode="Markdown")

async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """מטפל ב-callback queries של תפריט ההתחלה"""
    query = update.callback_query
    if not query:
        return

    data = query.data or ""
    await query.answer()

    if data == "open_investor":
        await handle_investor_callback(update, context)
    elif data == "send_proof":
        await handle_send_proof_callback(update, context)
    elif data == "info_benefits":
        await handle_benefits_callback(update, context)
    elif data == "back_to_main":
        # חזרה למסך הראשי
        await send_start_screen(update, context)
    else:
        await query.edit_message_text("❌ פעולה לא מוכרת.")


async def handle_investor_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """מטפל בכפתור מידע למשקיעים"""
    query = update.callback_query
    investor_text = load_message_block(
        "INVESTOR_INFO",
        "📈 **מידע למשקיעים**\n\n"
        "מערכת SLHNET מחברת בין טלגרם, חוזים חכמים על Binance Smart Chain, "
        "קבלות דיגיטליות ו-NFT, כך שכל עסקה מתועדת וניתנת למעקב.\n\n"
        "ניתן להצטרף כשותף, להחזיק טוקן SLH ולקבל חלק מהתנועה במערכת.",
    )

    keyboard = [[InlineKeyboardButton("🔙 חזרה לתפריט הראשי", callback_data="back_to_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text=investor_text, reply_markup=reply_markup, parse_mode="Markdown")


async def handle_send_proof_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """מסביר איך לשלם ולאן לשלוח אישור"""
    query = update.callback_query
    text = build_payment_instructions()
    keyboard = [[InlineKeyboardButton("🔙 חזרה לתפריט הראשי", callback_data="back_to_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode="Markdown")


async def handle_benefits_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """מסביר ללקוח מה הוא מקבל מהמערכת"""
    query = update.callback_query
    benefits_text = load_message_block(
        "BENEFITS_INFO",
        "🎁 **מה מקבלים בתשלום 39 ₪?**\n\n"
        "• גישה לקבוצת עסקים חכמה בטלגרם עם תכנים, הדרכות וקהילה פעילה.\n"
        "• פתיחה וחיבור של ארנק SLH על רשת Binance Smart Chain (BSC).\n"
        "• אפשרות לקבל תשלומים דיגיטליים ועמלות הפנייה דרך המערכת.\n"
        "• חיבור לחוזים חכמים, קבלות דיגיטליות ו-NFT שמייצגים עסקאות ושערי כניסה.\n"
        "• בסיס לעתיד – סטייקינג, חסכונות והשקעות מתקדמות בתוך אקו־סיסטם SLHNET.\n\n"
        "אחרי התשלום ושליחת האישור – אתה מקבל קישור לקבוצה + סט כלים דיגיטליים להתחלה.",
    )

    keyboard = [[InlineKeyboardButton("🔙 חזרה לתפריט הראשי", callback_data="back_to_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text=benefits_text, reply_markup=reply_markup, parse_mode="Markdown")
async def echo_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """מטפל בהודעות טקסט רגילות"""
    user = update.effective_user
    text = update.message.text if update.message else ""
    
    logger.info(f"Message from {user.id if user else '?'}: {text}")
    
    response = load_message_block(
        "ECHO_RESPONSE",
        "✅ תודה על ההודעה! אנחנו כאן כדי לעזור.\nהשתמש ב-/start כדי לראות את התפריט הראשי."
    )
    
    await update.message.reply_text(response)


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """מטפל בפקודות לא מוכרות"""
    await update.message.reply_text(
        "❓ פקודה לא מוכרת. השתמש ב-/start כדי לראות את התפריט הזמין."
    )


# =========================
# Routes של FastAPI משופרים
# =========================

@app.get("/api/metrics/finance")
async def finance_metrics():
    """סטטוס כספי כולל – הכנסות, רזרבות, נטו ואישורים."""
    from datetime import datetime
    reserve_stats = get_reserve_stats() or {}
    approval_stats = get_approval_stats() or {}

    return {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "reserve": reserve_stats,
        "approvals": approval_stats,
    }




@app.get("/metrics")
async def metrics():
    """Prometheus scrape endpoint for SLHNET metrics."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/metrics")
async def metrics():
    """Prometheus scrape endpoint for SLHNET metrics."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Endpoint לבריאות המערכת"""
    from datetime import datetime
    return HealthResponse(
        status="ok",
        service="slhnet-telegram-gateway",
        timestamp=datetime.now().isoformat(),
        version="2.0.0"
    )


@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    """דף נחיתה"""
    if not templates:
        return HTMLResponse("<h1>SLHNET Bot - Template Engine Not Available</h1>")
    
    return templates.TemplateResponse(
        "landing.html",
        {
            "request": request,
            "landing_url": safe_get_url(Config.LANDING_URL, "https://slh-nft.com"),
            "business_group_url": safe_get_url(Config.BUSINESS_GROUP_URL, "https://slh-nft.com"),
        },
    )


@app.post("/webhook")
async def telegram_webhook(update: TelegramWebhookUpdate):
    """Webhook endpoint עם הגנות"""
    try:
        # אתחול אוטומטי אם needed
        TelegramAppManager.initialize_handlers()
        app_instance = TelegramAppManager.get_app()

        # המרה ועיבוד
        raw_update = update.dict()
        ptb_update = Update.de_json(raw_update, app_instance.bot)
        
        if ptb_update:
            await app_instance.process_update(ptb_update)
            return JSONResponse({"status": "processed"})
        else:
            return JSONResponse({"status": "no_update"}, status_code=400)
            
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=500)


@app.on_event("startup")
async def startup_event():
    """אתחול during startup"""
    # סכמת ארנקים פנימיים + סטייקינג
    try:
        init_internal_wallet_schema()
    except Exception as e:
        logger.error(f"init_internal_wallet_schema failed: {e}")
    warnings = Config.validate()
    for warning in warnings:
        logger.warning(warning)
    if warnings:
        await send_log_message("⚠️ **אזהרות אתחול:**\n" + "\n".join(warnings))
    # אתחול אפליקציית טלגרם + Webhook
    try:
        await TelegramAppManager.start()
    except Exception as e:
        logger.error(f"Failed to start Telegram Application: {e}")
        # לא מפילים את השרת HTTP, אבל שומרים לוג

# הרצה מקומית
# =========================
if __name__ == "__main__":
    import uvicorn
    from datetime import datetime

    # בדיקת קונפיגורציה
    warnings = Config.validate()
    if warnings:
        print("⚠️ אזהרות קונפיגורציה:")
        for warning in warnings:
            print(f"  {warning}")

    port = int(os.getenv("PORT", "8080"))
    print(f"🚀 Starting SLHNET Bot on port {port}")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_config=None
    )