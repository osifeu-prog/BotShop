# -*- coding: utf-8 -*-
import os
import logging
from dotenv import load_dotenv

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters,
)

# ------ ENV ------
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
PUBLIC_URL = os.getenv("PUBLIC_URL", "").strip()
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "Q3Zb7r9kT2pX1mN4F8hU6wY0aBcDeGHi").strip()

if not TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN חסר בסביבה (.env)")

# ------ LOGGING ------
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("server")

# ------ IMPORT YOUR BOT (do not change your design!) ------
# חשוב: bot.py חייב להיות ליד server.py בריפו
import bot as B
from bot import PRICE, FIRST_NAME, LAST_NAME, PHONE, PAYMENT_CONFIRMATION

# ------ FASTAPI + PTB APP ------
app = FastAPI()
telegram_app: Application | None = None

def build_application() -> Application:
    app_ = Application.builder().token(TOKEN).build()

    # Conversation with per_message=True (ה־תיקון!)
    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(B.select_card, pattern="^select_card$"),
            CallbackQueryHandler(B.upload_receipt, pattern="^upload_receipt$"),
        ],
        states={
            PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, B.receive_price)],
            FIRST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, B.receive_first_name)],
            LAST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, B.receive_last_name)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, B.receive_phone)],
            PAYMENT_CONFIRMATION: [MessageHandler(filters.PHOTO, B.receive_receipt)],
        ],
        fallbacks=[],
        per_message=True,  # ←←← התיקון שפתר את התקיעה אחרי "אנא הזינו מחיר"
    )

    # Handlers שמורים 1:1 לעיצוב שלך
    app_.add_handler(CommandHandler("start", B.start))
    app_.add_handler(conv_handler)
    app_.add_handler(CallbackQueryHandler(B.callback_router))

    app_.add_handler(MessageHandler(filters.Text("☎️ צור קשר 📞"), B.handle_contact))
    app_.add_handler(MessageHandler(filters.Text("🌐 אתר"), B.handle_website))
    app_.add_handler(MessageHandler(filters.Text("🔄 תפריט ראשי 📚"), B.handle_main_menu))
    app_.add_handler(MessageHandler(filters.Text("✍🏻 רכישת חנות 🎯"), B.handle_purchase_shop))

    return app_

@app.on_event("startup")
async def on_startup():
    global telegram_app
    telegram_app = build_application()
    await telegram_app.initialize()
    await telegram_app.start()
    log.info("Application started")

@app.on_event("shutdown")
async def on_shutdown():
    global telegram_app
    if telegram_app:
        await telegram_app.stop()
        await telegram_app.shutdown()

@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.get("/")
def root():
    return PlainTextResponse("OK")

@app.get("/set-webhook")
async def set_webhook():
    if not telegram_app:
        raise HTTPException(status_code=503, detail="Telegram app not ready")
    url_base = PUBLIC_URL or os.getenv("KOYEB_PUBLIC_URL", "")
    if not url_base:
        raise HTTPException(status_code=400, detail="PUBLIC_URL env var is missing")
    url = f"{url_base.rstrip('/')}/webhook/{WEBHOOK_SECRET}"
    ok = await telegram_app.bot.set_webhook(url=url, drop_pending_updates=True)
    return {"ok": ok, "set_to": url}

@app.get("/delete-webhook")
async def delete_webhook():
    if not telegram_app:
        raise HTTPException(status_code=503, detail="Telegram app not ready")
    ok = await telegram_app.bot.delete_webhook(drop_pending_updates=True)
    return {"ok": ok}

@app.get("/get-webhook")
async def get_webhook():
    if not telegram_app:
        raise HTTPException(status_code=503, detail="Telegram app not ready")
    w = await telegram_app.bot.get_webhook_info()
    return JSONResponse(w.to_dict())

@app.post("/webhook/{secret}")
async def webhook(secret: str, request: Request):
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    if not telegram_app:
        raise HTTPException(status_code=503, detail="Telegram app not ready")
    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return JSONResponse({"ok": True})
