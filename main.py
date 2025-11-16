from telegram.ext import MessageHandler, filters
import os
import json
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from pathlib import Path
from typing import Optional, Dict, Any

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from pydantic import BaseModel

from telegram import Update, InputFile
from slh_public_api import router as public_router
from social_api import router as social_router
from slh_core_api import router as core_router  # API ליבה לרפרלים
from slhnet_extra import router as slhnet_extra_router

from telegram.ext import CommandHandler, ContextTypes
from telegram.ext import Application, CommandHandler, ContextTypes


# =========================
# בסיס לוגינג
# =========================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("slhnet")

# =========================
# FastAPI app
# =========================
app = FastAPI(title="SLHNET Gateway Bot")

BASE_DIR = Path(__file__).resolve().parent

# סטטיק וטמפלטס
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# רואטרים של API ציבורי + פיד חברתי + ליבת רפרלים
app.include_router(public_router)
app.include_router(social_router)
app.include_router(core_router)

# =========================
# קובץ referral פשוט (אפשר להעביר ל-DB בהמשך)
# =========================
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
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
        return  # כבר רשום
    data["users"][suid] = {
        "referrer": str(referrer_id) if referrer_id else None,
    }
    save_referrals(data)


# =========================
# קריאת טקסטים של /start ו-/info מהקובץ
# =========================
MESSAGES_FILE = BASE_DIR / "bot_messages_slhnet.txt"


def load_message_block(block_name: str) -> str:
    """
    טוען בלוק טקסט מהקובץ bot_messages_slhnet.txt

    פורמט הקובץ:
    === BLOCK_NAME ===
    שורות...
    === END ===
    """
    if not MESSAGES_FILE.exists():
        return f"[שגיאה: bot_messages_slhnet.txt לא נמצא (חסר בלוק {block_name})]"

    content = MESSAGES_FILE.read_text(encoding="utf-8")
    lines = content.splitlines()

    result_lines = []
    in_block = False
    for line in lines:
        if line.strip().startswith("===") and block_name in line:
            in_block = True
            continue
        if in_block and line.strip().startswith("=== END"):
            break
        if in_block:
            result_lines.append(line)

    if not result_lines:
        return f"[שגיאה: בלוק {block_name} לא נמצא]"

    return "\n".join(result_lines)


# =========================
# מודל בסיסי ל-Webhook
# =========================
class TelegramWebhookUpdate(BaseModel):
    update_id: int
    message: Optional[Dict[str, Any]] = None
    callback_query: Optional[Dict[str, Any]] = None


# =========================
# קריאת משתני סביבה
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
ADMIN_ALERT_CHAT_ID = os.getenv("ADMIN_ALERT_CHAT_ID", "")
LANDING_URL = os.getenv("LANDING_URL", "https://slh-nft.com")
BUSINESS_GROUP_URL = os.getenv("BUSINESS_GROUP_URL", "")
GROUP_STATIC_INVITE = os.getenv("GROUP_STATIC_INVITE", BUSINESS_GROUP_URL)
PAYBOX_URL = os.getenv("PAYBOX_URL", "")
BIT_URL = os.getenv("BIT_URL", "")
PAYPAL_URL = os.getenv("PAYPAL_URL", "")
START_IMAGE_PATH = os.getenv("START_IMAGE_PATH", "assets/start_banner.jpg")

# קבוצת לוגים (שם מתקבלות הודעות כניסה / תשלום)
LOGS_GROUP_CHAT_ID = os.getenv("LOGS_GROUP_CHAT_ID", ADMIN_ALERT_CHAT_ID or "")

# =========================
# Telegram Application (lazy)
# =========================
telegram_app: Optional[Application] = None


def get_telegram_app() -> Application:
    global telegram_app
    if telegram_app is not None:
        return telegram_app

    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")

    telegram_app = Application.builder().token(BOT_TOKEN).build()
    logger.info("Telegram Application instance created")
    return telegram_app


# =========================
# עזר: שליחת הודעה ללוגים
# =========================
async def send_log_message(text: str) -> None:
    if not LOGS_GROUP_CHAT_ID:
        logger.warning("LOGS_GROUP_CHAT_ID not set; skipping log message")
        return
    try:
        app_ = get_telegram_app()
        await app_.bot.send_message(chat_id=int(LOGS_GROUP_CHAT_ID), text=text)
    except Exception as e:
        logger.exception(f"Failed to send log message: {e}")


# =========================
# עזר: הצגת מסך /start
# =========================
async def send_start_screen(update: Update, context: ContextTypes.DEFAULT_TYPE, referrer: Optional[int] = None) -> None:
    user = update.effective_user
    chat = update.effective_chat

    # רישום רפרראם יש
    if user:
        register_referral(user.id, referrer)

    title = load_message_block("START_TITLE")
    body = load_message_block("START_BODY")

    # שליחת תמונה אם קיימת
    image_path = BASE_DIR / START_IMAGE_PATH
    if image_path.exists():
        with image_path.open("rb") as f:
            await chat.send_photo(photo=InputFile(f), caption=title)
    else:
        await chat.send_message(text=title)

    pay_url = PAYBOX_URL or (LANDING_URL + "#join39")
    more_info_url = LANDING_URL
    group_url = BUSINESS_GROUP_URL or LANDING_URL

    keyboard = [
        [InlineKeyboardButton(" תשלום 39  וגישה מלאה", url=pay_url)],
        [InlineKeyboardButton("ℹ לפרטים נוספים", url=more_info_url)],
        [InlineKeyboardButton(" הצטרפות לקבוצת העסקים", url=group_url)],
        [InlineKeyboardButton(" מידע למשקיעים", callback_data="open_investor")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await chat.send_message(text=body, reply_markup=reply_markup)

    # לוגים: משתמש חדש
    if user:
        log_text = f"📥 משתמש חדש הפעיל את הבוט.\nuser_id = {user.id}\nusername = @{user.username or 'חסר'}\nשם: {user.full_name}"
        await send_log_message(log_text)


# =========================
# פקודת /start
# =========================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # בדיקת פרמטר רפרר (אם נפתח דרך t.me/BotName?start=12345)
    referrer = None
    if context.args:
        try:
            referrer = int(context.args[0])
        except Exception:
            referrer = None

    await send_start_screen(update, context, referrer=referrer)


# =========================
# כפתור "מידע למשקיעים"
# =========================
async def handle_investor_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    investor_text = load_message_block("INVESTOR_INFO")
    await query.edit_message_text(text=investor_text)


# =========================
# עיבוד callback כללי
# =========================
async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    data = query.data or ""

    if data == "open_investor":
        await handle_investor_callback(update, context)
        return

    await query.answer("הפעולה אינה מוכרת.")


# =========================
# פקודת /whoami
# =========================
async def whoami_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat

    if not user:
        await chat.send_message("לא זיהיתי משתמש.")
        return

    text = (
        f"👤 פרטי המשתמש שלך:\n"
        f"id: {user.id}\n"
        f"username: @{user.username or 'חסר'}\n"
        f"full_name: {user.full_name}\n"
    )
    await chat.send_message(text=text)


# =========================
# Handler כללי לטקסט
# =========================
async def echo_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # לעת עתה לא נעשה echo, רק לוג
    user = update.effective_user
    chat = update.effective_chat
    text = update.message.text if update.message else ""
    logger.info(f"Incoming message from {user.id if user else '?'}: {text}")
    await chat.send_message("קיבלתי את ההודעה, תודה!")


# =========================
# אתחול האפליקציה של טלגרם
# =========================
def init_telegram_handlers(app_: Application) -> None:
    app_.add_handler(CommandHandler("start", start_command))
    app_.add_handler(CommandHandler("whoami", whoami_command))
    app_.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo_message))
    app_.add_handler(MessageHandler(filters.COMMAND, echo_message))
    app_.add_handler(
        # CallbackQueryHandler
        MessageHandler(filters.ALL, lambda *_: None)
    )


# =========================
# Routes של FastAPI
# =========================
@app.get("/health")
async def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": "telegram-gateway-community-bot",
    }


@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    """
    רנדר של templates/landing.html
    """
    return templates.TemplateResponse(
        "landing.html",
        {
            "request": request,
            "landing_url": LANDING_URL,
            "business_group_url": BUSINESS_GROUP_URL,
        },
    )


@app.post("/webhook")
async def telegram_webhook(update: TelegramWebhookUpdate):
    """
    נקודת webhook לבוט טלגרם
    """
    app_ = get_telegram_app()

    # אתחול handlers אם לא אותחלו עדיין
    if not getattr(app_, "_slhnet_handlers_initialized", False):
        init_telegram_handlers(app_)
        setattr(app_, "_slhnet_handlers_initialized", True)

    # המרה ל-Update של python-telegram-bot
    raw_update = update.dict()
    ptb_update = Update.de_json(raw_update, app_.bot)
    await app_.process_update(ptb_update)

    return JSONResponse({"ok": True})


# =========================
# הרצה מקומית (לבדיקה)
# =========================
if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8080"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
