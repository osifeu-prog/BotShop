from telegram.ext import MessageHandler, filters, CallbackQueryHandler
import os
import json
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from pathlib import Path
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, Request
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
# Logging
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("slhnet")

# =========================
# FastAPI app
# =========================
app = FastAPI(
    title="SLHNET BotShop / Buy_My_Shop",
    description="SLH BotShop – Telegram bot + API",
    version="1.0.0",
)

BASE_DIR = Path(__file__).resolve().parent

static_dir = BASE_DIR / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# =========================
# Config
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


logger.info("Loaded Config: BOT_USERNAME=%s, WEBHOOK_URL=%s", Config.BOT_USERNAME, Config.WEBHOOK_URL)
logger.info("ADMIN_OWNER_IDS=%s, ADMIN_ALERT_CHAT_ID=%s", Config.ADMIN_OWNER_IDS, Config.ADMIN_ALERT_CHAT_ID)

# =========================
# Bot texts
# =========================
class BotTexts:
    start_text: str = (
        "ברוך הבא לשער הקהילה העסקית של SLH.\n"
        "כרטיס כניסה חד-פעמי: 39₪ כולל גישה לבוטים, לקהילה ולאקדמיה."
    )
    investor_text: str = (
        "ברוך הבא למסלול המשקיעים של SLH.\n"
        "כאן מרוכזים עדכונים ותוכניות השקעה."
    )

    @classmethod
    def load_from_file(cls, path: Path) -> None:
        if not path.exists():
            logger.warning("bot messages file not found: %s", path)
            return
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error("failed reading bot messages file: %s", e)
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

        logger.info("bot messages loaded from file")


BotTexts.load_from_file(BASE_DIR / "bot_messages_slhnet.txt")

# =========================
# DB layer
# =========================
DB_AVAILABLE = False
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
    DB_AVAILABLE = True
except ImportError:
    logger.warning("db module not found – running without DB")

    def init_schema():
        logger.info("init_schema skipped (no db)")

    def log_payment(*args, **kwargs):
        logger.info("log_payment skipped: %s %s", args, kwargs)

    def update_payment_status(*args, **kwargs):
        logger.info("update_payment_status skipped: %s %s", args, kwargs)

    def ensure_user(*args, **kwargs):
        logger.info("ensure_user skipped: %s %s", args, kwargs)

    def add_referral(*args, **kwargs):
        logger.info("add_referral skipped: %s %s", args, kwargs)

    def get_referrals(*args, **kwargs):
        return []

    def get_top_referrers(*args, **kwargs):
        return []

    def increment_metric(*args, **kwargs):
        logger.info("increment_metric skipped: %s %s", args, kwargs)

    def get_metric(*args, **kwargs):
        return 0

    def list_sales(*args, **kwargs):
        return []

# =========================
# Telegram Application holder
# =========================
class TelegramAppHolder:
    _instance: Optional[Application] = None
    _initialized: bool = False
    _started: bool = False

    @classmethod
    def get_app(cls) -> Application:
        if cls._instance is None:
            if not Config.BOT_TOKEN:
                raise RuntimeError("BOT_TOKEN is not configured")
            cls._instance = Application.builder().token(Config.BOT_TOKEN).build()
            logger.info("Telegram Application instance created")
        return cls._instance

    @classmethod
    def init_handlers(cls) -> None:
        if cls._initialized:
            return
        app_instance = cls.get_app()
        app_instance.add_handler(CommandHandler("start", start_command))
        app_instance.add_handler(CommandHandler("whoami", whoami_command))
        app_instance.add_handler(CommandHandler("chatinfo", chatinfo_command))
        app_instance.add_handler(CommandHandler("stats", stats_command))
        app_instance.add_handler(CallbackQueryHandler(callback_query_handler))
        app_instance.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))
        app_instance.add_handler(MessageHandler(filters.COMMAND, unknown_command))
        cls._initialized = True
        logger.info("Telegram handlers initialized")

    @classmethod
    async def async_start(cls) -> None:
        app_instance = cls.get_app()
        cls.init_handlers()
        if not cls._started:
            await app_instance.initialize()
            if Config.WEBHOOK_URL:
                try:
                    await app_instance.bot.set_webhook(Config.WEBHOOK_URL)
                    logger.info("Webhook set to %s", Config.WEBHOOK_URL)
                except Exception as e:
                    logger.error("Failed to set webhook: %s", e)
            await app_instance.start()
            cls._started = True
            logger.info("Telegram Application started")

    @classmethod
    async def async_stop(cls) -> None:
        if cls._instance and cls._started:
            await cls._instance.stop()
            await cls._instance.shutdown()
            cls._started = False
            logger.info("Telegram Application stopped")

# =========================
# Logging helper
# =========================
async def send_log_message(text: str) -> None:
    if not Config.ADMIN_ALERT_CHAT_ID:
        logger.warning("ADMIN_ALERT_CHAT_ID not set; log only: %s", text)
        return
    try:
        app_instance = TelegramAppHolder.get_app()
        await app_instance.bot.send_message(chat_id=Config.ADMIN_ALERT_CHAT_ID, text=text)
    except Exception as e:
        logger.error("failed to send log message: %s", e)

# =========================
# Helpers
# =========================
def get_start_image_path() -> Optional[Path]:
    """
    מחפש קודם כל את הנתיב שהוגדר ב-START_IMAGE_PATH (יחסי ל-BASE_DIR אם צריך),
    ואם לא קיים – ינסה להשתמש ב-assets/start_banner.jpg.
    """
    if Config.START_IMAGE_PATH:
        p = Path(Config.START_IMAGE_PATH)
        if not p.is_absolute():
            p = BASE_DIR / p
        if p.exists():
            return p

    p2 = BASE_DIR / "assets" / "start_banner.jpg"
    if p2.exists():
        return p2

    return None


def get_ton_address() -> str:
    if Config.TON_WALLET_ADDRESS:
        return Config.TON_WALLET_ADDRESS
    return "UQCr743gEr_nqV_0SBkSp3CtYS_15R3LDLBvLmKeEv7XdGvp"

# =========================
# Bot commands
# =========================
async def send_start_screen(update: Update, context: ContextTypes.DEFAULT_TYPE, referrer: Optional[int] = None):
    chat = update.effective_chat
    user = update.effective_user

    if user:
        ensure_user(user.id, user.username, user.full_name)

    # כפתורים – רק תשלום/מידע, לא קישור לקהילה לפני אישור
    buttons = []

    if Config.PAYBOX_URL:
        buttons.append([InlineKeyboardButton("💳 תשלום 39₪ – PayBox", url=Config.PAYBOX_URL)])
    if Config.BIT_URL:
        buttons.append([InlineKeyboardButton("💰 תשלום ב-Bit", url=Config.BIT_URL)])
    if Config.PAYPAL_URL:
        buttons.append([InlineKeyboardButton("🌍 תשלום PayPal", url=Config.PAYPAL_URL)])
    if Config.LANDING_URL:
        buttons.append([InlineKeyboardButton("🌐 דף נחיתה מלא באתר", url=Config.LANDING_URL)])

    keyboard = InlineKeyboardMarkup(buttons) if buttons else None

    ton_address = get_ton_address()

    text = (
        "🎯 *ברוך הבא לשער הקהילה של SLH*\n\n"
        "זהו בוט שנועד לייצר לך *מקור הכנסה אישי*.\n"
        "אתה רוכש פעם אחת כניסה ב־*39₪*, ומקבל אזור אישי בבוט, "
        "עם כרטיס ביקור דיגיטלי וקישור ייחודי לשיתוף.\n\n"
        "כל מי שנכנס דרך הקישור שלך נספר אוטומטית במערכת, "
        "כולל כמה דורות קדימה של מי שהם הביאו. כך אתה יכול לבנות\n"
        "*רשת הכנסות מתגלגלת* סביב כרטיס הביקור הדיגיטלי שלך.\n\n"
        "התמונה שאתה רואה בכניסה היא *שער הקהילה* –\n"
        "אותו רעיון של כרטיס ביקור / שער מכירה שתוכל למכור בעצמך,\n"
        "רק עם הקישור האישי שלך. הבוט זוכר עבורך מי הצטרף דרכך.\n\n"
        "בהמשך תוכל להגדיר בתוך המערכת את פרטי חשבון הבנק שלך "
        "(לפי מדיניות הבנק במדינה שלך),\n"
        "ולהגדיר את המחיר שתרצה לגבות על הלינק / הכרטיס שאתה מוכר דרך הבוט.\n"
        "כל משתמש חדש מקבל *כרטיס ביקור אישי לשיתוף* ונכנס למערכת ההפניות.\n\n"
        "📷 *מה עושים עכשיו?*\n"
        "1️⃣ מבצעים תשלום באחת מהאפשרויות הבאות.\n"
        "2️⃣ שולחים לכאן צילום מסך של אישור התשלום.\n"
        "3️⃣ לאחר אישור אדמין תקבל כאן קישור הצטרפות אישי לקהילה העסקית.\n\n"
        "🏦 *תשלום בהעברה בנקאית:*\n"
        "בנק הפועלים\n"
        "סניף כפר גנים (153)\n"
        "חשבון: 73462\n"
        "שם המוטב: קאופמן צביקה\n\n"
        "💎 *תשלום ב-TON (ארנק דיגיטלי):*\n"
        f"שלח לכתובת:\n`{ton_address}`\n"
        "איך זה עובד?\n"
        "1. הורד ארנק TON (למשל *Tonkeeper* או *Telegram Wallet*).\n"
        "2. טען את הארנק במטבע TON.\n"
        "3. בצע העברה לכתובת למעלה.\n"
        "4. צלם מסך של האישור ושלח לכאן.\n\n"
        "לאחר שנאשר את התשלום – תקבל כאן את\n"
        "*קישור ההצטרפות לקהילת העסקים של SLH*,\n"
        "ומשם תתחיל לבנות את הכלכלה האישית שלך דרך המערכת.\n"
    )

    img_path = get_start_image_path()
    if img_path is not None:
        try:
            with img_path.open("rb") as f:
                await chat.send_photo(
                    photo=InputFile(f),
                    caption=text,
                    reply_markup=keyboard,
                    parse_mode="Markdown",
                )
            return
        except Exception as e:
            logger.error("failed to send start image: %s", e)

    await chat.send_message(text=text, reply_markup=keyboard, parse_mode="Markdown")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args or []
    referrer = None
    if args:
        try:
            referrer = int(args[0])
        except ValueError:
            logger.warning("invalid referrer passed to /start: %s", args[0])
    await send_start_screen(update, context, referrer)


async def whoami_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat
    if not user:
        await chat.send_message("לא זיהיתי משתמש.")
        return
    text = (
        "👤 *פרטי המשתמש שלך:*\n"
        f"🆔 ID: `{user.id}`\n"
        f"📛 שם משתמש: @{user.username or 'לא מוגדר'}\n"
        f"🔰 שם מלא: {user.full_name}\n"
    )
    await chat.send_message(text=text, parse_mode="Markdown")


async def chatinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
            "\n👤 *המשתמש ששלח:*\n"
            f"🆔 user_id: `{user.id}`\n"
            f"📛 שם משתמש: @{user.username or 'לא מוגדר'}"
        )
    await chat.send_message(text=text, parse_mode="Markdown")


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    text = (
        "📊 סטטיסטיקות בסיסיות יגיעו לכאן בהמשך.\n"
        "כרגע הפוקוס: לוודא שכל ליד מהקמפיין מגיע לבוט, "
        "מבצע תשלום ושולח אישור."
    )
    await chat.send_message(text=text)


async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()
    await query.edit_message_text("הפעולה נקלטה, תודה.")


async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    await chat.send_message(
        "תודה על ההודעה 🙏\n"
        "להצטרפות – בצע תשלום 39₪ (בנק / Bit / PayBox / TON), "
        "צלם מסך של האישור ושלח לכאן, או כתוב /start לקבלת ההנחיות שוב.",
    )


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    await chat.send_message("פקודה לא מוכרת. השתמש ב-/start כדי לראות את האפשרויות.")

# =========================
# Referrals JSON (דמו)
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
        logger.error("error reading referrals: %s", e)
        return {"users": {}, "statistics": {"total_users": 0, "total_referrals": 0}}


def save_referrals(data: Dict[str, Any]) -> None:
    try:
        with REFERRAL_FILE.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("error writing referrals: %s", e)

# =========================
# Health & lifecycle
# =========================
class HealthResponse(BaseModel):
    status: str
    telegram_ready: bool
    db_connected: bool
    bot_username: Optional[str] = None
    webhook_url: Optional[str] = None
    has_bot_token: bool
    has_database_url: bool
    db_available: bool
    admin_owner_ids: List[int]
    admin_alert_chat_id: int


@app.on_event("startup")
async def on_startup():
    logger.info("Starting SLHNET service...")
    try:
        init_schema()
    except Exception as e:
        logger.error("DB init_schema error: %s", e)
    await TelegramAppHolder.async_start()
    logger.info("Startup complete.")


@app.on_event("shutdown")
async def on_shutdown():
    logger.info("Shutting down SLHNET service...")
    await TelegramAppHolder.async_stop()


@app.get("/healthz", response_model=HealthResponse)
async def healthz():
    has_bot_token = bool(Config.BOT_TOKEN)
    has_database_url = bool(Config.DATABASE_URL)
    db_connected = has_database_url and DB_AVAILABLE
    try:
        app_instance = TelegramAppHolder.get_app()
        telegram_ok = app_instance is not None and TelegramAppHolder._started
    except Exception:
        telegram_ok = False

    return HealthResponse(
        status="ok",
        telegram_ready=telegram_ok,
        db_connected=db_connected,
        bot_username=Config.BOT_USERNAME or None,
        webhook_url=Config.WEBHOOK_URL or None,
        has_bot_token=has_bot_token,
        has_database_url=has_database_url,
        db_available=DB_AVAILABLE,
        admin_owner_ids=Config.ADMIN_OWNER_IDS,
        admin_alert_chat_id=Config.ADMIN_ALERT_CHAT_ID,
    )


@app.get("/meta", response_class=JSONResponse)
async def meta():
    return {
        "bot_username": Config.BOT_USERNAME,
        "webhook_url": Config.WEBHOOK_URL,
        "community_group_link": Config.COMMUNITY_GROUP_LINK,
        "support_group_link": Config.SUPPORT_GROUP_LINK,
        "has_bot_token": bool(Config.BOT_TOKEN),
        "has_database_url": bool(Config.DATABASE_URL),
        "db_available": DB_AVAILABLE,
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
    data = await request.json()
    app_instance = TelegramAppHolder.get_app()
    update = Update.de_json(data, app_instance.bot)
    await app_instance.process_update(update)
    return JSONResponse({"ok": True})

# =========================
# Routers (SLH APIs)
# =========================
try:
    app.include_router(public_router, prefix="/api/public", tags=["public"])
    app.include_router(social_router, prefix="/api/social", tags=["social"])
    app.include_router(core_router, prefix="/api/core", tags=["core"])
    if slhnet_extra_router:
        app.include_router(slhnet_extra_router, prefix="/api/extra", tags=["extra"])
except Exception as e:
    logger.error("Error including routers: %s", e)
