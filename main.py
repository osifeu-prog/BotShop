from telegram.ext import MessageHandler, filters
import os
import json
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
import psycopg2
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from slhnet_extra import (
    router as extra_router,
    get_public_meta,
    get_public_token_balance,
    get_public_token_price,
    get_public_staking_info,
)

from slh_core_api import router as core_router
from slh_social_api import router as social_router
from slh_public_api import router as public_router

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

logging.basicConfig(level=logging.INFO)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('telegram').setLevel(logging.WARNING)
logging.getLogger('telegram.ext').setLevel(logging.WARNING)

logger = logging.getLogger("slhnet")

BASE_DIR = Path(__file__).resolve().parent
DOCS_DIR = BASE_DIR / "docs"
DOCS_MSG_FILE = DOCS_DIR / "BOT_TEXTS_START_INVESTOR.txt"
ASSETS_DIR = BASE_DIR / "assets"

START_IMAGE_PATH = os.getenv("START_IMAGE_PATH", str(ASSETS_DIR / "start_banner.jpg"))

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
BOT_USERNAME = os.getenv("BOT_USERNAME", "")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")

COMMUNITY_GROUP_LINK = os.getenv("COMMUNITY_GROUP_LINK", "")
SUPPORT_GROUP_LINK = os.getenv("SUPPORT_GROUP_LINK", "")
PAYBOX_URL = os.getenv("PAYBOX_URL", "")
BIT_URL = os.getenv("BIT_URL", "")
PAYPAL_URL = os.getenv("PAYPAL_URL", "")
LANDING_URL = os.getenv("LANDING_URL", "")

TON_WALLET_ADDRESS = os.getenv("TON_WALLET_ADDRESS", "")

ADMIN_ALERT_CHAT_ID = int(os.getenv("ADMIN_ALERT_CHAT_ID", "0") or "0")


class BotTexts:
    def __init__(self, start: str, investor: str):
        self.start = start
        self.investor = investor


def load_bot_texts() -> BotTexts:
    """
    טוען טקסטים של /start ו-/investor מתוך docs/BOT_TEXTS_START_INVESTOR.txt
    בפורמט:

    [START]
    ...
    [INVESTOR]
    ...
    """
    default_start = (
        "ברוך הבא ל-SLH / Buy_My_Shop!\n"
        "כאן אתה קונה כרטיס כניסה דיגיטלי לעולם של הכנסה פסיבית, מומחים, ורשת כלכלית חדשה."
    )
    default_investor = (
        "מידע למשקיעים ב-SLH:\n"
        "הפרויקט בונה אקו-סיסטם שלם סביב טוקן SLH, אקדמיה, ורשת מומחים.\n"
        "בגרסה זו נציג סקיצה קצרה, וניתן להעמיק מול הצוות."
    )

    if not DOCS_MSG_FILE.exists():
        return BotTexts(start=default_start, investor=default_investor)

    content = DOCS_MSG_FILE.read_text(encoding="utf-8")
    start_block = []
    investor_block = []
    current = None

    for line in content.splitlines():
        stripped = line.strip()
        if stripped == "[START]":
            current = "start"
            continue
        if stripped == "[INVESTOR]":
            current = "investor"
            continue

        if current == "start":
            start_block.append(line)
        elif current == "investor":
            investor_block.append(line)

    start_text = "\n".join(start_block).strip() or default_start
    investor_text = "\n".join(investor_block).strip() or default_investor

    return BotTexts(start=start_text, investor=investor_text)


BOT_TEXTS = load_bot_texts()

# =========================
# הגדרות אדמין + DB לסטטיסטיקות /start
# =========================

ADMIN_IDS = set()
_admin_ids_raw = os.getenv("ADMIN_OWNER_IDS", "")
for _part in _admin_ids_raw.replace(" ", "").split(","):
    if _part:
        try:
            ADMIN_IDS.add(int(_part))
        except ValueError:
            pass


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


DATABASE_URL = os.getenv("DATABASE_URL", "")


def _get_db_conn():
    """
    חיבור פשוט ל-PostgreSQL עבור לוג /start  אם אין DB הפונקציות פשוט לא עושות כלום.
    """
    if not DATABASE_URL:
        return None
    try:
        return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        logger.warning("failed to connect DB for start stats: %s", e)
        return None


def log_start_db(user_id: int, username: str | None, chat_id: int | None, campaign: str | None) -> None:
    """
    שומר אירוע /start לטבלה start_events (כולל יצירת הטבלה אם צריך).
    """
    conn = _get_db_conn()
    if conn is None:
        return
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS start_events (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        username TEXT,
                        chat_id BIGINT,
                        campaign TEXT,
                        occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                    """
                )
                cur.execute(
                    "INSERT INTO start_events (user_id, username, chat_id, campaign) VALUES (%s, %s, %s, %s);",
                    (user_id, username, chat_id, campaign),
                )
    finally:
        conn.close()


def get_start_stats_by_date(days: int = 14):
    conn = _get_db_conn()
    if conn is None:
        return []
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        (occurred_at AT TIME ZONE 'Asia/Jerusalem')::date AS day,
                        COUNT(*) AS total,
                        COUNT(DISTINCT user_id) AS unique_users
                    FROM start_events
                    WHERE occurred_at >= NOW() - INTERVAL %s
                    GROUP BY day
                    ORDER BY day DESC
                    LIMIT 60;
                    """,
                    (f"{days} days",),
                )
                rows = cur.fetchall()
                return [
                    {
                        "day": str(r[0]),
                        "total": int(r[1]),
                        "unique_users": int(r[2]),
                    }
                    for r in rows
                ]
    finally:
        conn.close()


def get_start_stats_by_campaign(limit: int = 10):
    conn = _get_db_conn()
    if conn is None:
        return []
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        COALESCE(NULLIF(TRIM(campaign), ''), '(no_campaign)') AS campaign,
                        COUNT(*) AS total,
                        COUNT(DISTINCT user_id) AS unique_users
                    FROM start_events
                    GROUP BY campaign
                    ORDER BY total DESC
                    LIMIT %s;
                    """,
                    (limit,),
                )
                rows = cur.fetchall()
                return [
                    {
                        "campaign": r[0],
                        "total": int(r[1]),
                        "unique_users": int(r[2]),
                    }
                    for r in rows
                ]
    finally:
        conn.close()


# =========================
# Telegram Bot
# =========================


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """נקודת כניסה ראשית /start – כולל רפררלים והצגת תמונת כרטיס NFT."""
    chat = update.effective_chat
    user = update.effective_user
    message = update.effective_message

    if not chat or not user:
        return

    chat_id = chat.id

    # בדיקת payload של /start לצורך קמפיין / רפררל
    payload = None
    if message and message.text and message.text.startswith("/start"):
        parts = message.text.split(maxsplit=1)
        if len(parts) == 2:
            payload = parts[1].strip()

    # שליחת תמונת ה" שער הקהילה " (NFT דיגיטלי בסיסי)
    banner_path = Path(START_IMAGE_PATH)
    if banner_path.exists():
        try:
            with banner_path.open("rb") as f:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=InputFile(f, filename=banner_path.name),
                    caption="🎟 זה השער הדיגיטלי שלך – כרטיס כניסה לסלה / SLHNET.",
                )
        except Exception as e:
            logger.warning("could not send start banner image: %s", e)

    # טקסט חווייתי – בונה על מה שהיה ומחדד את מודל ה-NFT / אזור אישי
    text = (
        f"{BOT_TEXTS.start}\n\n"
        " מה אתה קונה כאן? כרטיס כניסה דיגיטלי בסגנון NFT (תמונת השער שאתה רואה עכשיו).\n"
        " אחרי הרכישה תוכל להגדיר באזור האישי שלך בבוט פרטי חשבון בנק לקבלת כספים,\n"
        " להוסיף קבוצה פרטית משלך לכל מי שרוכש ממך, ולקבל גישה לקבוצת המשחק הכללית.\n"
        " כל רכישה דרך הכרטיס שלך מקדמת אותך ברשת ה-SLHNET.\n\n"
        " תשלום 39  וגישה מלאה  דרך כפתור/קישור שתראה בדף הנחיתה\n"
        " /investor  מידע למשקיעים\n"
        " /whoami  פרטי החיבור שלך (להרחבה בהמשך)"
    )
    await context.bot.send_message(chat_id=chat_id, text=text)


async def investor_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/investor – פירוט למשקיעים (תוכן נטען מהקובץ או ברירת מחדל)."""
    await update.effective_message.reply_text(BOT_TEXTS.investor)


async def whoami_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/whoami – מידע בסיסי על המשתמש והחיבור שלו לבוט."""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    lines = [
        "ℹ️ פרטי החיבור שלך:",
        f"user_id: {user.id}",
        f"username: @{user.username}" if user.username else "username: —",
        f"name: {user.full_name}",
        f"chat_id: {chat.id}",
        f"chat_type: {chat.type}",
    ]

    if LANDING_URL:
        lines.append("")
        lines.append(f"עמוד הנחיתה של המערכת: {LANDING_URL}")

    await update.effective_message.reply_text("\n".join(lines))


async def bankinfo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /bankinfo – מציג למשתמש את פרטי התשלום הסטנדרטיים להצטרפות (PayBox / BIT / PayPal וכו').
    """
    lines = ["💳 אפשרויות תשלום להצטרפות לקהילה בתמורה ל-39 ₪:", ""]

    if PAYBOX_URL:
        lines.append(f"• PayBox: {PAYBOX_URL}")
    if BIT_URL:
        lines.append(f"• Bit: {BIT_URL}")
    if PAYPAL_URL:
        lines.append(f"• PayPal: {PAYPAL_URL}")

    if TON_WALLET_ADDRESS:
        lines.append("")
        lines.append("או תשלום בטון (TON):")
        lines.append(f"• TON wallet: `{TON_WALLET_ADDRESS}`")

    if COMMUNITY_GROUP_LINK:
        lines.append("")
        lines.append(f"לאחר התשלום, תצורף לקבוצת הקהילה: {COMMUNITY_GROUP_LINK}")

    await update.effective_message.reply_text("\n".join(lines), parse_mode="Markdown")


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """פקודת /help – סיכום הפקודות המרכזיות."""
    lines = [
        "פקודות זמינות בבוט Buy_My_Shop:",
        "",
        "/start - הסבר מלא על הכרטיס הדיגיטלי ונקודת פתיחה",
        "/investor - מידע למשקיעים",
        "/whoami - פרטי החיבור שלך",
        "/bankinfo - פרטי תשלום להצטרפות",
        "/chatinfo - מידע על הצ'אט הנוכחי (לצורך הגדרות אדמין/קבוצות)",
        "/admin_stats - סטטיסטיקות /start (לאדמינים בלבד)",
    ]
    await update.effective_message.reply_text("\n".join(lines))


async def chatinfo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/chatinfo – מאפשר לראות את ה-chat_id של הקבוצה/צ'אט."""
    chat = update.effective_chat
    if not chat:
        return

    lines = [
        "ℹ️ פרטי הצ'אט הנוכחי:",
        f"chat_id: {chat.id}",
        f"type: {chat.type}",
        f"title: {chat.title}",
    ]
    await update.effective_message.reply_text("\n".join(lines))


async def notify_admin_new_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    שליחת התראה לקבוצת אדמינים על כל /start:
    - לוג לקבוצת לוגים (ADMIN_ALERT_CHAT_ID)
    - כתיבה ל-DB (start_events) עבור סטטיסטיקות תאריכים/קמפיינים.
    """
    now_il = datetime.now(ZoneInfo("Asia/Jerusalem"))
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    # קמפיין מתוך /start payload, למשל: /start campaign_google
    raw_text = update.effective_message.text if update.effective_message else ""
    campaign = None
    if raw_text and raw_text.startswith("/start"):
        parts = raw_text.split(maxsplit=1)
        if len(parts) == 2:
            campaign = parts[1].strip() or None

    # לוג ל-DB
    try:
        log_start_db(user.id, user.username, chat.id, campaign)
    except Exception as e:
        logger.warning("failed to log start event to DB: %s", e)

    if not ADMIN_ALERT_CHAT_ID:
        return

    lines = [
        "👤 משתמש חדש נכנס לבוט Buy_My_Shop",
        "",
        f"time: {now_il.strftime('%Y-%m-%d %H:%M:%S')} (Asia/Jerusalem)",
        f"user_id: {user.id}",
        f"username: @{user.username}" if user.username else "username: —",
        f"name: {user.full_name}",
        f"from chat_id: {chat.id} ({chat.type})",
    ]

    if campaign:
        lines.append(f"campaign: {campaign}")

    text = "\n".join(lines)

    try:
        await context.bot.send_message(
            chat_id=ADMIN_ALERT_CHAT_ID,
            text=text,
        )
    except Exception:
        # לא מפילים את הבוט על שגיאה בלוג התראות
        pass


async def notify_admin_new_user_on_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    עוטף את notify_admin_new_user כך שנוכל לחבר אותו ל-MessageHandler של /start
    בלי להפריע ל-CommandHandler("start") הקיים.
    """
    await notify_admin_new_user(update, context)


async def admin_stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    סטטיסטיקות בסיסיות לאדמין:
    - מספר /start 14 ימים אחרונים לפי תאריכים
    - 10 קמפיינים מובילים (/start <campaign>)
    """
    user = update.effective_user
    if not user or not is_admin(user.id):
        return

    per_day = get_start_stats_by_date(14)
    per_campaign = get_start_stats_by_campaign(10)

    lines = ["📊 סטטיסטיקות /start אחרונות", ""]

    if per_day:
        lines.append("לפי תאריך (14 ימים אחורה):")
        for row in per_day:
            lines.append(
                f"- {row['day']}: total={row['total']}, unique_users={row['unique_users']}"
            )
        lines.append("")
    else:
        lines.append("אין עדיין נתוני /start בטבלה.")
        lines.append("")

    if per_campaign:
        lines.append("לפי קמפיין (/start <campaign>):")
        for row in per_campaign:
            lines.append(
                f"- {row['campaign']}: total={row['total']}, unique_users={row['unique_users']}"
            )
    else:
        lines.append("אין עדיין קמפיינים רשומים (/start עם payload).")

    await update.effective_message.reply_text("\n".join(lines))


# =========================
# FastAPI + Telegram Application
# =========================

app = FastAPI(title="SLHNET BotShop / Buy_My_Shop")

app.include_router(core_router, prefix="/core", tags=["core"])
app.include_router(social_router, prefix="/social", tags=["social"])
app.include_router(public_router, prefix="/public", tags=["public"])
app.include_router(extra_router, prefix="/extra", tags=["extra"])

static_dir = BASE_DIR / "web"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

templates = Jinja2Templates(directory=str(static_dir))

telegram_app: Optional[Application] = None


async def init_telegram_app() -> None:
    global telegram_app

    if telegram_app is not None:
        return

    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not provided, Telegram bot will not start.")
        return

    telegram_app = Application.builder().token(BOT_TOKEN).build()

    telegram_app.add_handler(CommandHandler("start", start_handler))
    telegram_app.add_handler(CommandHandler("investor", investor_handler))
    telegram_app.add_handler(CommandHandler("whoami", whoami_handler))
    telegram_app.add_handler(CommandHandler("bankinfo", bankinfo_handler))
    telegram_app.add_handler(CommandHandler("help", help_handler))
    telegram_app.add_handler(CommandHandler("chatinfo", chatinfo_handler))
    telegram_app.add_handler(CommandHandler("admin_stats", admin_stats_handler))

    telegram_app.add_handler(
        MessageHandler(
            filters.Regex(r"^/start(?:\s|$)") & (~filters.COMMAND),
            notify_admin_new_user_on_start,
        )
    )

    if WEBHOOK_URL:
        await telegram_app.bot.set_webhook(url=WEBHOOK_URL)
        logger.info("Webhook set to %s", WEBHOOK_URL)
    else:
        logger.warning("WEBHOOK_URL not set – Telegram bot will require polling if used locally.")


@app.on_event("startup")
async def on_startup():
    logger.info("Starting SLHNET gateway service...")
    await init_telegram_app()
    logger.info("Startup complete.")


@app.post("/webhook")
async def telegram_webhook(request: Request):
    if telegram_app is None:
        raise HTTPException(status_code=500, detail="Telegram application not initialized")

    try:
        update_data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    update = Update.de_json(update_data, telegram_app.bot)
    await telegram_app.process_update(update)

    return JSONResponse({"ok": True})


@app.get("/healthz")
async def healthz():
    return JSONResponse({"ok": True})


@app.get("/meta")
async def meta():
    return JSONResponse(get_public_meta())


@app.get("/token/balance")
async def token_balance(address: str):
    return JSONResponse(get_public_token_balance(address))


@app.get("/token/price")
async def token_price():
    return JSONResponse(get_public_token_price())


@app.get("/staking/info")
async def staking_info():
    return JSONResponse(get_public_staking_info())


@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    context = {
        "request": request,
        "community_group_link": COMMUNITY_GROUP_LINK,
        "support_group_link": SUPPORT_GROUP_LINK,
        "landing_url": LANDING_URL,
        "bot_username": BOT_USERNAME,
    }
    return templates.TemplateResponse("index.html", context)
