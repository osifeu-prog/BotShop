import os
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from pydantic import BaseModel

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import Application, CommandHandler, ContextTypes

from slh_public_api import router as public_router
from social_api import router as social_router
from slh_core_api import core_router
from slhnet_extra import router as extra_router

from db import init_schema, store_user, increment_metric

# =========================
# Logging
# =========================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gateway-bot")

# =========================
# Globals & paths
# =========================

BASE_DIR = Path(__file__).resolve().parent

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
ADMIN_ALERT_CHAT_ID = int(os.getenv("ADMIN_ALERT_CHAT_ID", "0") or "0")

DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DOCS_MSG_FILE = BASE_DIR / "docs" / "bot_messages_slhnet.txt"
ROOT_MSG_FILE = BASE_DIR / "bot_messages_slhnet.txt"

# =========================
# FastAPI app
# =========================

app = FastAPI(title="SLHNET Gateway Bot")

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# API routers
app.include_router(public_router)
app.include_router(social_router)
app.include_router(core_router)
app.include_router(extra_router)

# =========================
# Bot texts loader (/start, /investor)
# =========================


class BotTexts(BaseModel):
    start: str
    investor: str


def load_bot_texts() -> BotTexts:
    default_start = (
        "ברוך הבא לשער הכניסה ל-SLHNET \n"
        "קהילת עסקים, טוקן SLH, חנויות דיגיטליות ושיווק חכם."
    )
    default_investor = (
        "מידע למשקיעים: SLHNET בונה אקו-סיסטם חברתי-פיננסי שקוף, "
        "עם מודל הפניות מדורג וצמיחה אורגנית."
    )

    path = ROOT_MSG_FILE if ROOT_MSG_FILE.exists() else DOCS_MSG_FILE
    if not path.exists():
        return BotTexts(start=default_start, investor=default_investor)

    text = path.read_text(encoding="utf-8")
    start_block: list[str] = []
    investor_block: list[str] = []
    current: Optional[str] = None

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("=== /start"):
            current = "start"
            continue
        if stripped.startswith("=== /investor"):
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
# Simple referral storage on disk (still used by /whoami)
# =========================

REF_FILE = DATA_DIR / "referrals.json"


def load_referrals() -> Dict[str, Any]:
    if not REF_FILE.exists():
        return {"users": {}}
    try:
        return json.loads(REF_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"users": {}}


def save_referrals(data: Dict[str, Any]) -> None:
    REF_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def register_referral(user_id: int, referrer_id: Optional[int]) -> None:
    data = load_referrals()
    suid = str(user_id)
    if suid in data["users"]:
        return
    data["users"][suid] = {
        "referrer": str(referrer_id) if referrer_id else None,
    }
    save_referrals(data)


# =========================
# Telegram Application (webhook mode)
# =========================

telegram_app: Optional[Application] = None


async def start_slhnet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Rich /start entry point for SLHNET.
    Also logs to DB + notifies admin group (if configured).
    """
    chat = update.effective_chat
    user = update.effective_user

    if chat is None or user is None:
        return

    # DB logging
    total_views = 0
    try:
        store_user(user.id, user.username)
    except Exception as e:
        logger.warning("store_user failed: %s", e)

    try:
        total_views = increment_metric("start_views", 1)
    except Exception as e:
        logger.warning("increment_metric(start_views) failed: %s", e)

    # Referral deep-link: /start ref_<user_id>
    referrer_id: Optional[int] = None
    if context.args:
        arg = context.args[0]
        if arg.startswith("ref_"):
            try:
                referrer_id = int(arg.replace("ref_", "").strip())
            except ValueError:
                referrer_id = None

    if referrer_id:
        register_referral(user.id, referrer_id)

    landing_url = os.getenv("LANDING_URL", "https://slh-nft.com/")
    paybox_url = os.getenv("PAYBOX_URL", "https://links.payboxapp.com/1SNfaJ6XcYb")
    business_group_url = os.getenv("BUSINESS_GROUP_URL", "https://t.me/+HIzvM8sEgh1kNWY0")
    bot_url = "https://t.me/Buy_My_Shop_bot"

    header = "🌐 שער הכניסה לקהילת העסקים\n"
    if total_views:
        header += f"מספר הצגה כולל: {total_views}\n\n"

    text = header + (
        "ברוך הבא לשער הכניסה לקהילת העסקים שלנו 🌐\n\n"
        "כאן אתה מצטרף למערכת של עסקים, שותפים וקהל יוצר ערך סביב:\n"
        "• שיווק רשתי חכם\n"
        "• נכסים דיגיטליים (NFT, טוקני SLH)\n"
        "• מתנות, הפתעות ופרסים על פעילות ושיתופים\n\n"
        "מה תקבל בהצטרפות?\n"
        "✅ גישה לקבוצת עסקים פרטית\n"
        "✅ למידה משותפת איך לייצר הכנסות משיווק האקו-סיסטם שלנו\n"
        "✅ גישה למבצעים שיחולקו רק בקהילה\n"
        "✅ השתתפות עתידית בחלוקת טוקני SLH ו-NFT ייחודיים למשתתפים פעילים\n"
        "✅ מנגנון ניקוד למי שמביא חברים – שיוצג בקהילה\n\n"
        "דמי הצטרפות חד־פעמיים: 39 ש\"ח.\n\n"
        "לאחר אישור התשלום תקבל קישור לקהילת העסקים.\n\n"
        "כדי להתחיל – בחר באפשרות הרצויה:\n\n"
        "פקודות חשובות:\n"
        "/investor  מידע למשקיעים\n"
        "/whoami   פרטי החיבור שלך\n"
    )

    keyboard = [
        [InlineKeyboardButton("תשלום 39 ₪ וגישה מלאה", url=paybox_url)],
        [InlineKeyboardButton("דף נחיתה / פרטים נוספים", url=landing_url)],
        [InlineKeyboardButton("הצטרפות לקבוצת העסקים", url=business_group_url)],
        [InlineKeyboardButton("פתיחת הבוט מחדש", url=bot_url)],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Try to send banner image if exists
    banner_path = BASE_DIR / "assets" / "start_banner.jpg"
    if banner_path.exists():
        try:
            with banner_path.open("rb") as f:
                await context.bot.send_photo(
                    chat_id=chat.id,
                    photo=InputFile(f),
                    caption="שער הכניסה ל-SLHNET",
                )
        except Exception as e:
            logger.warning("Failed to send start banner: %s", e)

    await context.bot.send_message(chat_id=chat.id, text=text, reply_markup=reply_markup)

    # Admin notification about new user
    if ADMIN_ALERT_CHAT_ID:
        try:
            lines = [
                "👤 משתמש חדש נכנס לבוט Buy_My_Shop",
                "",
                f"user_id: {user.id}",
                f"username: @{user.username}" if user.username else "username: —",
                f"name: {user.full_name}",
                f"from chat_id: {chat.id} ({chat.type})",
            ]
            await context.bot.send_message(
                chat_id=ADMIN_ALERT_CHAT_ID,
                text="\n".join(lines),
            )
        except Exception as e:
            logger.warning("Failed to notify admin group: %s", e)


async def investor_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat is None:
        return

    phone = "058-420-3384"
    tg_link = "https://t.me/Osif83"
    text = (
        f"{BOT_TEXTS.investor}\n\n"
        "יצירת קשר ישירה עם המייסד:\n"
        f"טלפון: {phone}\n"
        f"טלגרם: {tg_link}\n\n"
        "כאן בונים יחד מודל ריפרל שקוף, סטייקינג ופתרונות תשואה על בסיס "
        "אקו-סיסטם אמיתי של עסקים, לא על אוויר."
    )
    await context.bot.send_message(chat_id=chat.id, text=text)


async def whoami_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat
    if chat is None or user is None:
        return

    data = load_referrals()
    u = data["users"].get(str(user.id))
    ref = u["referrer"] if u else None

    msg = [
        "פרטי המשתמש שלך:",
        f"user_id: {user.id}",
        f"username: @{user.username}" if user.username else "username: (ללא)",
    ]
    if ref:
        msg.append(f"הופנית ע\"י משתמש: {ref}")
    else:
        msg.append("לא רשום מפנה – ייתכן שאתה השורש או שנכנסת ישירות.")

    await context.bot.send_message(chat_id=chat.id, text="\n".join(msg))


async def chatid_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    user = update.effective_user
    if chat is None or user is None:
        return

    text = (
        "📡 פרטי הצ'אט הזה:\n"
        f"chat_id: {chat.id}\n"
        f"type: {chat.type}\n"
        f"title: {chat.title or '-'}\n"
        f"username: @{chat.username or '-'}\n\n"
        f"👤 user_id שלך: {user.id}\n"
        f"username שלך: @{user.username or '-'}"
    )
    await context.bot.send_message(chat_id=chat.id, text=text)


async def init_telegram_app() -> None:
    global telegram_app

    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set – bot will not run")
        return

    telegram_app = Application.builder().token(BOT_TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", start_slhnet))
    telegram_app.add_handler(CommandHandler("investor", investor_handler))
    telegram_app.add_handler(CommandHandler("whoami", whoami_handler))
    telegram_app.add_handler(CommandHandler("chatid", chatid_handler))
    telegram_app.add_handler(CommandHandler("chatinfo", chatid_handler))

    await telegram_app.initialize()

    if WEBHOOK_URL:
        try:
            await telegram_app.bot.set_webhook(WEBHOOK_URL)
            logger.info("Webhook set to %s", WEBHOOK_URL)
        except Exception as e:
            logger.error("Failed to set webhook: %s", e)
    else:
        logger.warning("WEBHOOK_URL not set – please configure it on Railway.")


@app.on_event("startup")
async def on_startup() -> None:
    logger.info("Starting SLHNET gateway service...")
    try:
        init_schema()
        logger.info("DB schema ensured (payments, users, referrals, rewards, metrics).")
    except Exception as e:
        logger.warning("init_schema failed: %s", e)

    await init_telegram_app()
    logger.info("Startup complete.")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    global telegram_app
    if telegram_app is not None:
        await telegram_app.stop()
        await telegram_app.shutdown()
        logger.info("Telegram application stopped.")


@app.get("/health")
async def health() -> Dict[str, Any]:
    db_status = "enabled" if os.getenv("DATABASE_URL") else "disabled"
    return {
        "status": "ok",
        "service": "telegram-gateway-community-bot",
        "db": db_status,
    }


@app.post("/webhook")
async def telegram_webhook(request: Request):
    global telegram_app
    if telegram_app is None:
        raise HTTPException(status_code=503, detail="Telegram app not initialized")

    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return JSONResponse({"ok": True})


@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    slh_price = float(os.getenv("SLH_NIS", "444"))
    return templates.TemplateResponse(
        "landing.html",
        {
            "request": request,
            "slh_price": slh_price,
        },
    )
