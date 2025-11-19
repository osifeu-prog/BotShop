from telegram.ext import MessageHandler, filters, CallbackQueryHandler
import os
import json
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from pathlib import Path
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from pydantic import BaseModel

from telegram import Update
from slh.slh_public_api import router as public_router
from social_api import router as social_router
from SLH.slh_core_api import router as core_router
from slh.slhnet_extra import router as slhnet_extra_router

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
    title="SLHNET BotShop / Buy_My_Shop",
    description="SLH BotShop – בוט מכירה עצמי + API לאקו-סיסטם SLH",
    version="1.0.0"
)

BASE_DIR = Path(__file__).resolve().parent

# static ו-templates
static_dir = BASE_DIR / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# =========================
# קונפיג סביבתי
# =========================
class Config:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    BOT_USERNAME: str = os.getenv("BOT_USERNAME", "")
    WEBHOOK_URL: str = os.getenv("WEBHOOK_URL", "")

    COMMUNITY_GROUP_LINK: str = os.getenv("COMMUNITY_GROUP_LINK", "")
    SUPPORT_GROUP_LINK: str = os.getenv("SUPPORT_GROUP_LINK", "")

    PAYBOX_URL: str = os.getenv("PAYBOX_URL", "")
    BIT_URL: str = os.getenv("BIT_URL", "")
    PAYPAL_URL: str = os.getenv("PAYPAL_URL", "")

    LANDING_URL: str = os.getenv("LANDING_URL", "")

    START_IMAGE_PATH: str = os.getenv("START_IMAGE_PATH", "assets/start_banner.jpg")

    DATABASE_URL: str = os.getenv("DATABASE_URL", "")

    TON_WALLET_ADDRESS: str = os.getenv("TON_WALLET_ADDRESS", "")

    ADMIN_ALERT_CHAT_ID: int = int(os.getenv("ADMIN_ALERT_CHAT_ID", "0") or "0")
    ADMIN_OWNER_IDS: List[int] = [
        int(x.strip())
        for x in os.getenv("ADMIN_OWNER_IDS", "").split(",")
        if x.strip().isdigit()
    ]


logger.info(f"Loaded Config: BOT_USERNAME={Config.BOT_USERNAME}, WEBHOOK_URL={Config.WEBHOOK_URL}")
logger.info(f"ADMIN_OWNER_IDS={Config.ADMIN_OWNER_IDS}, ADMIN_ALERT_CHAT_ID={Config.ADMIN_ALERT_CHAT_ID}")

# =========================
# BotTexts – טקסטים דינמיים מהקובץ
# =========================
class BotTexts:
    start_text: str = (
        "ברוך הבא לבוט הרשמי של קהילת SLH.\n"
        "כאן תוכל להצטרף לקהילה העסקית שלנו ב־39 ש\"ח ולקבל גישה לכל הבוטים, הכלים וההזדמנויות."
    )
    investor_text: str = (
        "ברוך הבא למסלול המשקיעים של SLH.\n"
        "כאן נרכז עדכונים והשקעות עתידיות באקו-סיסטם SLH / SELA / NIFTII."
    )

    @classmethod
    def load_from_file(cls, path: Path) -> None:
        if not path.exists():
            logger.warning(f"Bot texts file not found: {path}")
            return

        try:
            raw = path.read_text(encoding="utf-8")
            logger.info("Loading bot texts from file")
        except Exception as e:
            logger.error(f"Error reading bot texts file: {e}")
            return

        def extract_block(tag: str) -> Optional[str]:
            start_tag = f"[{tag.upper()}]"
            end_tag = f"[END_{tag.upper()}]"
            if start_tag not in raw or end_tag not in raw:
                return None
            try:
                part = raw.split(start_tag, 1)[1].split(end_tag, 1)[0]
                return part.strip()
            except Exception:
                return None

        start_block = extract_block("START")
        investor_block = extract_block("INVESTOR")

        if start_block:
            cls.start_text = start_block
        if investor_block:
            cls.investor_text = investor_block

        logger.info("Bot texts loaded successfully")


BotTexts.load_from_file(BASE_DIR / "bot_messages_slhnet.txt")

# =========================
# DB – חיבור בסיסי
# =========================
try:
    from db import (
        init_schema,
        log_payment,
        update_payment_status,
        ensure_user,
        add_referral,
        get_referrals,
        get_top_referrers,
        increment_metric,
        get_metric,
        list_sales,
    )
except ImportError:
    logger.warning("db module not found – running in NO-DB mode")

    def init_schema():
        logger.info("init_schema() skipped – NO-DB mode")

    def log_payment(*args, **kwargs):
        logger.info(f"log_payment skipped – data={args} {kwargs}")

    def update_payment_status(*args, **kwargs):
        logger.info(f"update_payment_status skipped – data={args} {kwargs}")

    def ensure_user(*args, **kwargs):
        logger.info(f"ensure_user skipped – data={args} {kwargs}")

    def add_referral(*args, **kwargs):
        logger.info(f"add_referral skipped – data={args} {kwargs}")

    def get_referrals(*args, **kwargs):
        return []

    def get_top_referrers(*args, **kwargs):
        return []

    def increment_metric(*args, **kwargs):
        logger.info(f"increment_metric skipped – data={args} {kwargs}")

    def get_metric(*args, **kwargs):
        return 0

    def list_sales(*args, **kwargs):
        return []

# =========================
# Application Singleton
# =========================
class TelegramAppHolder:
    _instance: Optional[Application] = None
    _initialized: bool = False

    @classmethod
    def get_app(cls) -> Application:
        if cls._instance is None:
            if not Config.BOT_TOKEN:
                raise RuntimeError("BOT_TOKEN is not configured")
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
            CommandHandler("chatinfo", chatinfo_command),
            CommandHandler("stats", stats_command),
            CallbackQueryHandler(callback_query_handler),
            MessageHandler(filters.TEXT & ~filters.COMMAND, echo_message),
            MessageHandler(filters.COMMAND, unknown_command),
        ]

        for handler in handlers:
            app_instance.add_handler(handler)

        cls._initialized = True
        logger.info("Telegram handlers initialized")


# =========================
# utilities משופרות
# =========================
async def send_log_message(text: str) -> None:
    """שולח הודעת לוג עם הגנות"""
    if not Config.ADMIN_ALERT_CHAT_ID:
        logger.info(f"[LOG ONLY] {text}")
        return

    try:
        app_instance = TelegramAppHolder.get_app()
        await app_instance.bot.send_message(chat_id=Config.ADMIN_ALERT_CHAT_ID, text=text)
    except Exception as e:
        logger.error(f"Failed to send log message: {e}")


# =========================
# פונקציות מסך פתיחה
# =========================
async def send_start_screen(update: Update, context: ContextTypes.DEFAULT_TYPE, referrer: Optional[int] = None):
    chat = update.effective_chat
    user = update.effective_user

    if user:
        ensure_user(user.id, user.username, user.full_name)

    if referrer and user:
        if referrer != user.id:
            add_referral(referrer_id=referrer, referred_id=user.id)

    buttons = [
        [InlineKeyboardButton("💳 תשלום 39₪ – PayBox", url=Config.PAYBOX_URL or "https://payboxapp.com")],
        [InlineKeyboardButton("💰 תשלום ב-Bit", url=Config.BIT_URL or "https://bitpay.co.il")],
    ]

    if Config.PAYPAL_URL:
        buttons.append([InlineKeyboardButton("🌍 תשלום PayPal", url=Config.PAYPAL_URL)])

    if Config.LANDING_URL:
        buttons.append([InlineKeyboardButton("🌐 דף נחיתה מפורט", url=Config.LANDING_URL)])

    keyboard = InlineKeyboardMarkup(buttons)

    text = (
        "🎯 *ברוך הבא לשער הקהילה העסקית של SLH*\n\n"
        "כרטיס כניסה: *39 ש\"ח* בלבד – חד פעמי.\n\n"
        "לאחר התשלום ואישור ידני, תקבל:\n"
        "✅ הצטרפות לקבוצת העסקים הסגורה שלנו\n"
        "✅ גישה לבוטים ולמערכת ההפניות\n"
        "✅ אפשרות להרוויח מעסקאות של חברים שתפנה\n\n"
        "📷 *שלח עכשיו צילום מסך של האישור* (PayBox / Bit / העברה בנקאית)\n"
        "והמערכת תעביר לאדמין לאישור.\n\n"
        "לקבלת עזרה: /whoami /stats"
    )

    await chat.send_message(text=text, reply_markup=keyboard, parse_mode="Markdown")


# =========================
# פקודות בוט
# =========================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """פקודת התחלה – כולל טיפול ב-referrer"""
    user = update.effective_user
    chat = update.effective_chat

    args = context.args or []
    referrer = None
    if args:
        try:
            referrer = int(args[0])
        except (ValueError, TypeError):
            logger.warning(f"Invalid referrer ID: {args[0]}")

    await send_start_screen(update, context, referrer=referrer)


async def whoami_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """פקודת whoami משופרת"""
    user = update.effective_user
    chat = update.effective_chat

    if not user:
        await chat.send_message("❌ לא זיהיתי משתמש.")
        return

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


async def chatinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """מציג מידע על הצ'אט הנוכחי – ID, סוג וכו'. שימושי כדי להגדיר קבוצות לוגים ואדמין."""
    chat = update.effective_chat
    user = update.effective_user

    if not chat:
        return

    text = (
        "💬 *פרטי הצ'אט הנוכחי:*\n"
        f"🆔 chat_id: `{chat.id}`\n"
        f"📛 סוג: `{chat.type}`\n"
        f"📣 כותרת: {chat.title or '—'}\n"
    )

    if user:
        text += (
            "\n👤 *פרטי המשתמש ששאל:*\n"
            f"🆔 user_id: `{user.id}`\n"
            f"📛 שם משתמש: @{user.username or 'לא מוגדר'}"
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
        f"🔁 סה״כ הפניות: {stats.get('total_referrals', 0)}\n"
    )

    await chat.send_message(text=text, parse_mode="Markdown")


async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return

    await query.answer()
    await query.edit_message_text("הפעולה התקבלה, תודה.")


async def echo_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """טיפול בהודעות טקסט רגילות (תמיכה/תיעוד)"""
    chat = update.effective_chat
    await chat.send_message(
        "✅ תודה על ההודעה! אנחנו כאן כדי לעזור.\n"
        "השתמש ב-/start כדי לראות את התפריט הראשי."
    )


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    await chat.send_message(
        "❓ פקודה לא מוכרת.\n"
        "השתמש ב-/start כדי לראות את התפריט הזמין."
    )

# =========================
# referral storage (קובץ JSON פשוט)
# =========================
REFERRAL_FILE = BASE_DIR / "data" / "referrals.json"
REFERRAL_FILE.parent.mkdir(exist_ok=True)


def load_referrals() -> Dict[str, Any]:
    if not REFERRAL_FILE.exists():
        return {"users": {}, "statistics": {"total_users": 0, "total_referrals": 0}}

    try:
        with REFERRAL_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error reading referrals file: {e}")
        return {"users": {}, "statistics": {"total_users": 0, "total_referrals": 0}}


def save_referrals(data: Dict[str, Any]) -> None:
    try:
        with REFERRAL_FILE.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error writing referrals file: {e}")


def register_user_referral(user_id: int, referrer_id: Optional[int]) -> bool:
    """רושם משתמש חדש עם referral"""
    try:
        data = load_referrals()
        suid = str(user_id)

        if suid in data["users"]:
            return False

        user_data = {
            "referrer": str(referrer_id) if referrer_id else None,
            "joined_at": None,
            "referral_count": 0,
        }

        data["users"][suid] = user_data
        stats = data.setdefault("statistics", {"total_users": 0, "total_referrals": 0})
        stats["total_users"] = stats.get("total_users", 0) + 1

        if referrer_id:
            ref_s = str(referrer_id)
            ref_data = data["users"].setdefault(
                ref_s,
                {"referrer": None, "joined_at": None, "referral_count": 0},
            )
            ref_data["referral_count"] = ref_data.get("referral_count", 0) + 1
            stats["total_referrals"] = stats.get("total_referrals", 0) + 1

        save_referrals(data)
        return True
    except Exception as e:
        logger.error(f"Error registering referral: {e}")
        return False


# =========================
# FastAPI – health/meta + דפי נחיתה
# =========================
class HealthResponse(BaseModel):
    status: str
    telegram_ready: bool
    db_connected: bool


@app.on_event("startup")
async def on_startup():
    logger.info("Starting SLHNET gateway + Telegram bot...")
    try:
        init_schema()
    except Exception as e:
        logger.error(f"DB init_schema error: {e}")

    TelegramAppHolder.get_app()
    TelegramAppHolder.initialize_handlers()
    logger.info("Startup complete.")


@app.get("/healthz", response_model=HealthResponse)
async def healthz():
    db_ok = bool(Config.DATABASE_URL)
    try:
        app_instance = TelegramAppHolder.get_app()
        telegram_ok = app_instance is not None
    except Exception:
        telegram_ok = False

    return HealthResponse(status="ok", telegram_ready=telegram_ok, db_connected=db_ok)


@app.get("/meta", response_class=JSONResponse)
async def meta():
    return {
        "bot_username": Config.BOT_USERNAME,
        "webhook_url": Config.WEBHOOK_URL,
        "community_group_link": Config.COMMUNITY_GROUP_LINK,
        "support_group_link": Config.SUPPORT_GROUP_LINK,
    }


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse(
        "landing.html",
        {
            "request": request,
            "bot_username": Config.BOT_USERNAME,
            "community_link": Config.COMMUNITY_GROUP_LINK,
            "price": 39,
        },
    )


@app.post("/webhook")
async def telegram_webhook(request: Request):
    """נקודת webhook לטלגרם"""
    from telegram import Update as TgUpdate

    data = await request.json()
    app_instance = TelegramAppHolder.get_app()
    update = TgUpdate.de_json(data, app_instance.bot)
    await app_instance.process_update(update)
    return JSONResponse({"ok": True})


# רואטרים של API עם הגנות
try:
    app.include_router(public_router, prefix="/api/public", tags=["public"])
    app.include_router(social_router, prefix="/api/social", tags=["social"])
    app.include_router(core_router, prefix="/api/core", tags=["core"])
    if slhnet_extra_router:
        app.include_router(slhnet_extra_router, prefix="/api/extra", tags=["extra"])
except Exception as e:
    logger.error(f"Error including routers: {e}")
