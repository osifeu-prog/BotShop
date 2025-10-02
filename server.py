# -*- coding: utf-8 -*-
import os
import logging
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, filters
)

# נטען משתני סביבה
load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
PUBLIC_URL = os.getenv("PUBLIC_URL", "").strip()
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip()

if not TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN missing")

# ייבוא פונקציות ומצבים מה-bot.py שלך (ללא שינוי עיצוב)
from bot import (
    start, open_shop, handle_card_navigation, select_card,
    receive_price, receive_first_name, receive_last_name, receive_phone,
    handle_payment_method, start_bank_transfer, upload_receipt, receive_receipt,
    handle_contact, handle_website, handle_main_menu, handle_purchase_shop,
    callback_router, PRICE, FIRST_NAME, LAST_NAME, PHONE, PAYMENT_CONFIRMATION
)

log = logging.getLogger("server")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

app = FastAPI()
telegram_app: Application | None = None

def build_application() -> Application:
    app_ = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(select_card, pattern="^select_card$"),
            CallbackQueryHandler(upload_receipt, pattern="^upload_receipt$"),
        ],
        states={
            PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_price)],
            FIRST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_first_name)],
            LAST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_last_name)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_phone)],
            PAYMENT_CONFIRMATION: [MessageHandler(filters.PHOTO, receive_receipt)],
        },
        fallbacks=[],
    )

    app_.add_handler(CommandHandler("start", start))
    app_.add_handler(conv_handler)
    app_.add_handler(CallbackQueryHandler(callback_router))

    # כפתורים בתפריט התחתון (עברית כפי שמופיע בבוט שלך)
    app_.add_handler(MessageHandler(filters.Text("☎️ צור קשר 📞"), handle_contact))
    app_.add_handler(MessageHandler(filters.Text("🌐 אתר"), handle_website))
    app_.add_handler(MessageHandler(filters.Text("🔄 תפריט ראשי 📚"), handle_main_menu))
    app_.add_handler(MessageHandler(filters.Text("✍🏻 רכישת חנות 🎯"), handle_purchase_shop))

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
    if not PUBLIC_URL:
        raise HTTPException(status_code=400, detail="PUBLIC_URL env var is missing")
    if not WEBHOOK_SECRET:
        raise HTTPException(status_code=400, detail="WEBHOOK_SECRET env var is missing")
    url = f"{PUBLIC_URL.rstrip('/')}/webhook/{WEBHOOK_SECRET}"
    ok = await telegram_app.bot.set_webhook(url=url, drop_pending_updates=True)
    return {"ok": ok, "set_to": url}

@app.get("/delete-webhook")
async def delete_webhook():
    if not telegram_app:
        raise HTTPException(status_code=503, detail="Telegram app not ready")
    ok = await telegram_app.bot.delete_webhook(drop_pending_updates=False)
    return {"ok": ok}

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
