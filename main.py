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
from slh_public_api import router as public_router
from social_api import router as social_router
from slh_core_api import router as core_router
from slhnet_extra import router as slhnet_extra_router

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
    app.include_router(public_router, prefix="/api/public", tags=["public"])
    app.include_router(social_router, prefix="/api/social", tags=["social"])
    app.include_router(core_router, prefix="/api/core", tags=["core"])
    if slhnet_extra_router:
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
    base: Dict[str, Any] = {
        "users": {},
        "statistics": {
            "total_users": 0,
            "start_events_total": 0,
            "last_start_at": None,
            "starts_by_user": {},
        },
    }

    if not REF_FILE.exists():
        return base

    try:
        with open(REF_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # ודא שמפתחות הסטטיסטיקה קיימים גם בקובץ ישן
        stats = data.setdefault("statistics", {})
        stats.setdefault("total_users", 0)
        stats.setdefault("start_events_total", 0)
        stats.setdefault("last_start_at", None)
        stats.setdefault("starts_by_user", {})

        data.setdefault("users", {})
        return data
    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"Error loading referrals: {e}")
        return base

    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"Error loading referrals: {e}")
        return {"users": {}, "statistics": {"total_users": 0}}



def save_referrals(data: Dict[str, Any]) -> None:
    """שומר נתוני referrals עם הגנת שגיאות"""
    try:
        stats = data.setdefault("statistics", {})
        stats["total_users"] = len(data.get("users", {}))

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
            # כבר רשום – לא נחשב כמשתמש חדש, אבל נרצה עדיין לוג / סטטיסטיקה במקום אחר
            return False  # כבר רשום

        user_data = {
            "referrer": str(referrer_id) if referrer_id else None,
            "joined_at": datetime.now().isoformat(),
            "referral_count": 0,
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


def register_start_event(user_id: int) -> None:
    """רושם אירוע /start לצורכי סטטיסטיקה (גם אם המשתמש כבר קיים)."""
    try:
        data = load_referrals()
        stats = data.setdefault("statistics", {})
        total = int(stats.get("start_events_total", 0))
        stats["start_events_total"] = total + 1

        from datetime import datetime as _dt
        stats["last_start_at"] = _dt.now().isoformat()

        per_user = stats.setdefault("starts_by_user", {})
        suid = str(user_id)
        per_user[suid] = int(per_user.get(suid, 0)) + 1

        save_referrals(data)
    except Exception as e:
        logger.error(f"Error registering start event for {user_id}: {e}")
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

def _parse_chat_id(raw: str) -> int:
    """Parses a chat_id from an env string, returns 0 if invalid."""
    if not raw:
        return 0
    import re as _re
    m = _re.search(r"-?\d+", raw)
    if not m:
        return 0
    try:
        return int(m.group(0))
    except Exception:
        return 0


def _parse_admin_ids(raw: str) -> list[int]:
    """Parses a comma/space separated list of admin IDs."""
    if not raw:
        return []
    import re as _re
    ids: list[int] = []
    for part in _re.findall(r"-?\d+", raw):
        try:
            ids.append(int(part))
        except Exception:
            continue
    return ids



class Config:
    """מחלקה לניהול קונפיגורציה"""
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    WEBHOOK_URL: str = os.getenv("WEBHOOK_URL", "")

    RAW_ADMIN_ALERT_CHAT_ID: str = os.getenv("ADMIN_ALERT_CHAT_ID", "").strip()
    RAW_LOGS_GROUP_CHAT_ID: str = os.getenv("LOGS_GROUP_CHAT_ID", RAW_ADMIN_ALERT_CHAT_ID or "").strip()
    RAW_ADMIN_OWNER_IDS: str = os.getenv("ADMIN_OWNER_IDS", "").strip()

    LANDING_URL: str = os.getenv("LANDING_URL", "https://slh-nft.com")
    BUSINESS_GROUP_URL: str = os.getenv("BUSINESS_GROUP_URL", "")
    GROUP_STATIC_INVITE: str = os.getenv("GROUP_STATIC_INVITE", "")
    PAYBOX_URL: str = os.getenv("PAYBOX_URL", "")
    BIT_URL: str = os.getenv("BIT_URL", "")
    PAYPAL_URL: str = os.getenv("PAYPAL_URL", "")
    START_IMAGE_PATH: str = os.getenv("START_IMAGE_PATH", "assets/start_banner.jpg")

    ADMIN_ALERT_CHAT_ID: int = _parse_chat_id(RAW_ADMIN_ALERT_CHAT_ID)
    LOGS_GROUP_CHAT_ID: int = _parse_chat_id(RAW_LOGS_GROUP_CHAT_ID)
    ADMIN_OWNER_IDS: list[int] = _parse_admin_ids(RAW_ADMIN_OWNER_IDS)

    @classmethod
    def validate(cls) -> List[str]:
        """בודק תקינות קונפיגורציה ומחזיר רשימת אזהרות"""
        warnings: List[str] = []
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
    async def ensure_initialized(cls) -> Application:
        """מוודא שהאפליקציה מאותחלת פעם אחת בלבד"""
        app_instance = cls.get_app()
        if cls._initialized:
            return app_instance

        # רישום handlers
        handlers = [
            CommandHandler("start", start_command),
            CommandHandler("whoami", whoami_command),
            CommandHandler("stats", stats_command),
            CommandHandler("admin", admin_command),
            CallbackQueryHandler(callback_query_handler),
            MessageHandler(filters.TEXT & ~filters.COMMAND, echo_message),
            MessageHandler(filters.COMMAND, unknown_command),
        ]

        for handler in handlers:
            app_instance.add_handler(handler)

        cls._initialized = True
        logger.info("Telegram handlers initialized")
        return app_instance
# =========================
# utilities משופרות
# =========================

async def send_log_message(text: str) -> None:
    """שולח הודעת לוג עם הגנות"""
    if not Config.LOGS_GROUP_CHAT_ID and not Config.ADMIN_ALERT_CHAT_ID:
        logger.warning("LOGS_GROUP_CHAT_ID and ADMIN_ALERT_CHAT_ID not set; skipping log message")
        return

    try:
        app_instance = TelegramAppManager.get_app()
        targets: list[int] = []

        if Config.LOGS_GROUP_CHAT_ID:
            targets.append(Config.LOGS_GROUP_CHAT_ID)
        if Config.ADMIN_ALERT_CHAT_ID and Config.ADMIN_ALERT_CHAT_ID not in targets:
            targets.append(Config.ADMIN_ALERT_CHAT_ID)

        for chat_id in targets:
            try:
                await app_instance.bot.send_message(chat_id=chat_id, text=text)
                logger.info(f"Log message sent to {chat_id}")
            except Exception as inner_e:
                logger.error(f"Failed to send log message to {chat_id}: {inner_e}")
    except Exception as e:
        logger.error(f"Failed to send log message: {e}")



def safe_get_url(url: str, fallback: str) -> str:
    """מחזיר URL עם הגנות"""
    return url if url and url.startswith(('http://', 'https://')) else fallback


# =========================
# handlers משופרים
# =========================

async def send_start_screen(update: Update, context: ContextTypes.DEFAULT_TYPE, referrer: Optional[int] = None) -> None:
    """מסך פתיחה שיווקי ל-SLH עם סטטיסטיקות ולוגים"""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        logger.error("No user or chat in update")
        return

    # רישום referral (אם משתמש חדש) + סטטיסטיקת /start
    if user:
        try:
            register_referral(user.id, referrer)
        except Exception as e:
            logger.error(f"register_referral failed: {e}")
        try:
            register_start_event(user.id)
        except Exception as e:
            logger.error(f"register_start_event failed: {e}")

    # הטקסטים מותאמים לבקשה שלך
    part1 = (
        "🎯 ברוך הבא לשער הקהילה של *SLH*\n\n"
        "זהו בוט שנועד לייצר לך *מקור הכנסה אישי*.\n"
        "רוכשים חד־פעמית לינק ייחודי לשיווק רשתי ב־*39₪*,\n"
        "ומקבלים אזור אישי בבוט – כרטיס ביקור דיגיטלי וקישור ייחודי לשיתוף."
    )

    part2 = (
        "כל מי שנכנס דרך הקישור שלך נספר אוטומטית במערכת, כולל דורות קדימה של מי שהם מביאים.\n"
        "כך אתה יכול לבנות *רשת הכנסות מתגלגלת* סביב כרטיס הביקור הדיגיטלי שלך,\n"
        "לפתוח עוד שלבים ולמכור דרכו עוד מוצרים – *החנות הדיגיטלית שלך בטלגרם*."
    )

    part3 = (
        "התמונה שאתה רואה בכניסה היא *שער הקהילה* –\n"
        "אותו רעיון של כרטיס ביקור / שער מכירה שתוכל למכור בעצמך,\n"
        "רק עם הקישור האישי שלך. הבוט זוכר עבורך מי הצטרף דרכך.\n\n"
        "לאחר התשלום תוכל להגדיר בתוך המערכת את פרטי חשבון הבנק שלך,\n"
        "ולהגדיר את המחיר שתרצה לגבות על הלינק / הכרטיס שאתה מוכר דרך הבוט."
    )

    part4 = (
        "כל משתמש חדש מקבל כרטיס ביקור אישי משלו לשיתוף וכניסה למערכת ההפניות.\n\n"
        "📷 *מה עושים עכשיו?*\n"
        "1️⃣ מבצעים תשלום באחת מהאפשרויות.\n"
        "2️⃣ שולחים לכאן צילום מסך של אישור התשלום.\n"
        "3️⃣ לאחר אישור אדמין תקבל כאן *קישור הצטרפות אישי לקהילה העסקית*."
    )

    # שליחת תמונת פתיחה (אם קיימת)
    start_image_path = Config.START_IMAGE_PATH or "assets/start_banner.jpg"
    image_fs_path = (BASE_DIR / start_image_path).resolve()
    if image_fs_path.exists():
        try:
            with image_fs_path.open("rb") as f:
                await chat.send_photo(
                    photo=f,
                    caption="שער הכניסה לקהילת *SLH* – מה שאתה רואה כאן הוא מה שתוכל למכור בעצמך, עם הלינק האישי שלך.",
                    parse_mode="Markdown",
                )
        except Exception as e:
            logger.error(f"Failed to send start image from {image_fs_path}: {e}")
    else:
        logger.warning(f"Start image not found at {image_fs_path}")

    # שליחת טקסטים מפוצלים
    await chat.send_message(part1, parse_mode="Markdown")
    await chat.send_message(part2, parse_mode="Markdown")
    await chat.send_message(part3, parse_mode="Markdown")
    await chat.send_message(part4, parse_mode="Markdown")

    # מקלדת תשלום והסברים
    keyboard = [
        [
            InlineKeyboardButton("🏦 תשלום בהעברה בנקאית", callback_data="pay_bank"),
        ],
        [
            InlineKeyboardButton("💎 תשלום ב-TON", callback_data="pay_ton"),
        ],
        [
            InlineKeyboardButton("🧩 איך להגדיר ארנק TON", callback_data="ton_help"),
        ],
        [
            InlineKeyboardButton("ℹ️ מה אני מקבל בקהילה?", callback_data="community_info"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await chat.send_message(
        "בחר את אופן התשלום או קבל עוד מידע:",
        reply_markup=reply_markup,
    )

    # לוגים לכל לחיצת /start
    log_text = (
        "📥 /start הופעל בבוט Buy_My_Shop\n"
        f"👤 User ID: {user.id}\n"
        f"📛 Username: @{user.username or 'לא מוגדר'}\n"
        f"🔰 שם: {user.full_name}\n"
        f"🔗 Referrer: {referrer or 'לא צוין'}"
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



async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """מטפל ב-callback queries של הבוט"""
    query = update.callback_query
    if not query:
        return

    data = (query.data or "").strip()
    await query.answer()

    if data == "open_investor":
        await handle_investor_callback(update, context)
        return

    if data == "pay_bank":
        text = (
            "🏦 *פרטי תשלום בהעברה בנקאית*\n\n"
            "בנק הפועלים\n"
            "סניף כפר גנים (153)\n"
            "חשבון: 73462\n"
            "שם המוטב: קאופמן צביקה\n\n"
            "לאחר ההעברה: צלם/י מסך של אישור התשלום ושלח/י לכאן בבוט."
        )
        await query.message.reply_text(text, parse_mode="Markdown")
        return

    if data == "pay_ton":
        text = (
            "💎 *תשלום ב-TON (ארנק דיגיטלי)*\n\n"
            "שלח/י את הסכום לכתובת הבאה:\n"
            "`UQCr743gEr_nqV_0SBkSp3CtYS_15R3LDLBvLmKeEv7XdGvp`\n\n"
            "לאחר ההעברה: צלם/י מסך של אישור התשלום ושלח/י לכאן בבוט."
        )
        await query.message.reply_text(text, parse_mode="Markdown")
        return

    if data == "ton_help":
        text = (
            "🧩 *איך להגדיר ארנק TON?*\n\n"
            "1. הורד/י ארנק TON (למשל *Tonkeeper* או *Telegram Wallet*).\n"
            "2. טען/י את הארנק במטבע TON.\n"
            "3. בצע/י העברה לכתובת שצוינה במסך הקודם.\n"
            "4. צלם/י מסך של האישור ושלח/י לכאן בבוט.\n\n"
            "לאחר שנאשר את התשלום – תקבל/י כאן קישור הצטרפות לקהילת העסקים של SLH."
        )
        await query.message.reply_text(text, parse_mode="Markdown")
        return

    if data == "community_info":
        text = (
            "👥 *מה מחכה לך בקהילת העסקים של SLH?*\n\n"
            "• הזדמנויות עסקיות חדשות ושותפויות.\n"
            "• גישה לבוטים וכלי רווח ייחודיים.\n"
            "• מערכת הפניות שמתגמלת אותך על כל מי שמצטרף דרכך.\n"
            "• עדכונים שוטפים על הטבות, מוצרים חדשים ותוכניות רווח.\n\n"
            "מהלינק האישי שלך *אתה מרוויח – לא אנחנו*.\n"
            "המטרה שלנו היא להגדיל את הקהילה ואת האקו־סיסטם,\n"
            "ולאפשר לך לבנות כלכלה אישית סביב כרטיס הביקור הדיגיטלי שלך."
        )
        await query.message.reply_text(text, parse_mode="Markdown")
        return

    # ברירת מחדל
    await query.edit_message_text("❌ פעולה לא מוכרת.")



async def handle_investor_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """מטפל בכפתור מידע למשקיעים"""
    query = update.callback_query
    investor_text = load_message_block(
        "INVESTOR_INFO", 
        "📈 **מידע למשקיעים**\n\nלפרטים נוספים על השקעות, צור קשר עם הנהלת הפרויקט."
    )
    
    # כפתור חזרה
    keyboard = [[InlineKeyboardButton("🔙 חזרה לתפריט הראשי", callback_data="back_to_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text=investor_text, reply_markup=reply_markup)



async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """פאנל אדמין בסיסי עם סטטיסטיקות ופקודות"""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    if user.id not in Config.ADMIN_OWNER_IDS:
        await chat.send_message("❌ אין לך הרשאת אדמין לבוט הזה.")
        return

    refs = load_referrals()
    stats = refs.get("statistics", {})
    total_users = int(stats.get("total_users", 0) or 0)
    total_starts = int(stats.get("start_events_total", 0) or 0)
    last_start = stats.get("last_start_at") or "לא נרשם"

    text = (
        "🛠 *לוח ניהול – Buy_My_Shop*\n\n"
        "*סטטיסטיקות:*\n"
        f"👥 משתמשים רשומים (referrals.json): {total_users}\n"
        f"▶️ לחיצות /start מצטברות: {total_starts}\n"
        f"🕒 /start אחרון: {last_start}\n\n"
        "*פקודות זמינות:*\n"
        "/start – דף הנחיתה למשתמשים\n"
        "/whoami – פרטי המשתמש והפניות שלו\n"
        "/stats – סטטיסטיקות בסיסיות על referrals\n"
        "/admin – תפריט ניהול זה\n"
    )

    await chat.send_message(text, parse_mode="Markdown")

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
        "❤קודה לא מוכרת. השתמש ב-/start כדי לראות את התפריט הזמין."
    )


# =========================
# Routes של FastAPI משופרים
# =========================
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


@app.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    """Endpoint מורחב לדיבוג – מצב טלגרם ו-DB"""
    from datetime import datetime

    # ברירת מחדל
    telegram_ready = False
    db_connected = False
    details: Dict[str, Any] = {}

    # בדיקת טלגרם
    try:
        app_instance = await TelegramAppManager.ensure_initialized()
        me = await app_instance.bot.get_me()
        telegram_ready = True
        details["bot_username"] = me.username
        details["bot_id"] = me.id
    except Exception as e:
        details["telegram_error"] = str(e)

    # בדיקת DB בסיסית (אם קיים מודול db)
    try:
        from db import get_session  # type: ignore
        async with get_session() as session:  # pragma: no cover - runtime check
            await session.execute("SELECT 1")
        db_connected = True
    except Exception as e:
        details["db_error"] = str(e)

    details["admin_alert_chat_id"] = Config.ADMIN_ALERT_CHAT_ID
    details["logs_group_chat_id"] = Config.LOGS_GROUP_CHAT_ID
    details["admin_owner_ids"] = Config.ADMIN_OWNER_IDS

    return HealthResponse(
        status="ok",
        service="slhnet-telegram-gateway",
        timestamp=datetime.now().isoformat(),
        version="2.0.0",
        telegram_ready=telegram_ready,
        db_connected=db_connected,
        details=details,
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
    warnings = Config.validate()
    for warning in warnings:
        logger.warning(warning)
    
    if warnings:
        await send_log_message("⚠️ **אזהרות אתחול:**\n" + "\n".join(warnings))


# =========================
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