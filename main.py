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

from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, ContextTypes

from slh_public_api import router as public_router
from social_api import router as social_router
from slh_core_api import router as core_router  # API הליבה החדש

# =========================
# בסיס לוגינג
# =========================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("slhnet")

# =========================
# FastAPI app
# =========================
app = FastAPI(title="SLHNET Gateway Bot")

# סטטיק וטמפלטס
BASE_DIR = Path(__file__).resolve().parent
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
# קריאת טקסטים של /start ו-/investor מתוך docs/bot_messages_slhnet.txt
# =========================

DOCS_MSG_FILE = BASE_DIR / "docs" / "bot_messages_slhnet.txt"


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
# Telegram Application (Webhook mode)
# =========================

telegram_app: Optional[Application] = None


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat_id = update.effective_chat.id if update.effective_chat else None
    if not chat_id or not user:
        return

    # הפניה (deep-link): /start ref_<user_id>
    referrer_id: Optional[int] = None
    if context.args:
        arg = context.args[0]
        if arg.startswith("ref_"):
            try:
                referrer_id = int(arg.replace("ref_", "").strip())
            except ValueError:
                referrer_id = None

    register_referral(user.id, referrer_id)

    # שליחת תמונת שער
    banner_path = BASE_DIR / "assets" / "start_banner.jpg"
    if banner_path.exists():
        try:
            with banner_path.open("rb") as f:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=InputFile(f),
                    caption=" שער הכניסה ל-SLHNET",
                )
        except Exception as e:
            logger.warning("Failed to send start banner: %s", e)

    text = (
        f"{BOT_TEXTS.start}\n\n"
        " תשלום 39  וגישה מלאה  דרך כפתור/קישור שתראה בדף הנחיתה\n"
        " /investor  מידע למשקיעים\n"
        " /whoami  פרטי החיבור שלך (להרחבה בהמשך)"
    )
    await context.bot.send_message(chat_id=chat_id, text=text)


async def investor_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id if update.effective_chat else None
    if not chat_id:
        return

    phone = "058-420-3384"
    tg_link = "https://t.me/Osif83"
    text = (
        f"{BOT_TEXTS.investor}\n\n"
        " יצירת קשר ישירה עם המייסד:\n"
        f"טלפון: {phone}\n"
        f"טלגרם: {tg_link}\n\n"
        "כאן בונים יחד מודל ריפרל שקוף, סטייקינג ופתרונות תשואה על בסיס\n"
        "אקו-סיסטם אמיתי של עסקים, לא על אוויר."
    )
    await context.bot.send_message(chat_id=chat_id, text=text)


async def whoami_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat_id = update.effective_chat.id if update.effective_chat else None
    if not chat_id or not user:
        return

    data = load_referrals()
    u = data["users"].get(str(user.id))
    ref = u["referrer"] if u else None

    msg = [
        " פרטי המשתמש שלך:",
        f"user_id: {user.id}",
        f"username: @{user.username}" if user.username else "username: (ללא)",
    ]
    if ref:
        msg.append(f"הופנית ע\"י משתמש: {ref}")
    else:
        msg.append("לא רשום מפנה  ייתכן שאתה השורש או שנכנסת ישירות.")

    await context.bot.send_message(chat_id=chat_id, text="\n".join(msg))


async def init_telegram_app() -> None:
    global telegram_app
    bot_token = os.getenv("BOT_TOKEN")
    webhook_url = os.getenv("WEBHOOK_URL")

    if not bot_token:
        logger.error("BOT_TOKEN not set  bot will not run")
        return

    telegram_app = Application.builder().token(bot_token).build()
    telegram_app.add_handler(CommandHandler("start", start_handler))
    telegram_app.add_handler(CommandHandler("investor", investor_handler))
    telegram_app.add_handler(CommandHandler("whoami", whoami_handler))

    await telegram_app.initialize()

    if webhook_url:
        try:
            await telegram_app.bot.set_webhook(webhook_url)
            logger.info("Webhook set to %s", webhook_url)
        except Exception as e:
            logger.error("Failed to set webhook: %s", e)
    else:
        logger.warning("WEBHOOK_URL not set  please configure it on Railway.")


@app.on_event("startup")
async def on_startup() -> None:
    logger.info("Starting SLHNET gateway service...")
    await init_telegram_app()
    logger.info("Startup complete.")


@app.get("/health")
async def health() -> Dict[str, Any]:
    db_status = os.getenv("DATABASE_URL")
    return {
        "status": "ok",
        "service": "telegram-gateway-community-bot",
        "db": "enabled" if db_status else "disabled",
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
