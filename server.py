# server.py
# -*- coding: utf-8 -*-
import os
import logging
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from dotenv import load_dotenv

from telegram import Update
# 🔧 שורה מתוקנת: אין Handler!
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters,
)

import bot as B  # לא נוגעים בעיצוב/לוגיקה שלך בבוט

load_dotenv()

log = logging.getLogger("uvicorn")
logging.basicConfig(level=logging.INFO)

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "").strip()
WEBHOOK_SECRET   = os.getenv("WEBHOOK_SECRET", "").strip()
PUBLIC_URL       = os.getenv("PUBLIC_URL", "").strip()

if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN missing")
if not WEBHOOK_SECRET:
    log.warning("WEBHOOK_SECRET missing — /webhook/{secret} יכשל אם לא תגדיר.")

app = FastAPI()
telegram_app: Application | None = None

# ===== PTB application bootstrap =====
async def build_telegram_app() -> Application:
    app_ = Application.builder().token(TELEGRAM_TOKEN).build()

    # ———— רישום כל ה־handlers בדיוק כפי שהם בבוט שלך ————
    PRICE, FIRST_NAME, LAST_NAME, PHONE, PAYMENT_CONFIRMATION = range(5)

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
        },
        fallbacks=[],
    )

    app_.add_handler(CommandHandler("start", B.start))
    app_.add_handler(conv_handler)
    app_.add_handler(CallbackQueryHandler(B.callback_router))

    # כפתורי reply (בדיוק כמו בבוט)
    app_.add_handler(MessageHandler(filters.Text("☎️ צור קשר 📞"), B.handle_contact))
    app_.add_handler(MessageHandler(filters.Text("🌐 אתר"), B.handle_website))
    app_.add_handler(MessageHandler(filters.Text("🔄 תפריט ראשי 📚"), B.handle_main_menu))
    app_.add_handler(MessageHandler(filters.Text("✍🏻 רכישת חנות 🎯"), B.handle_purchase_shop))

    return app_

# ===== FastAPI lifecycle =====
@app.on_event("startup")
async def on_startup():
    global telegram_app
    telegram_app = await build_telegram_app()
    await telegram_app.initialize()
    await telegram_app.start()
    me = await telegram_app.bot.get_me()
    log.info("Application started. Bot: @%s (%s)", me.username, me.id)

@app.on_event("shutdown")
async def on_shutdown():
    if telegram_app:
        await telegram_app.stop()
        await telegram_app.shutdown()

# ===== Health =====
@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.get("/")
def root():
    return PlainTextResponse("OK")

# ===== Webhook helpers =====
@app.get("/set-webhook")
async def set_webhook():
    if not telegram_app:
        raise HTTPException(status_code=503, detail="Telegram app not ready")
    if not PUBLIC_URL:
        raise HTTPException(status_code=400, detail="PUBLIC_URL env var is missing")
    url = f"{PUBLIC_URL.rstrip('/')}/webhook/{WEBHOOK_SECRET}"
    ok = await telegram_app.bot.set_webhook(url=url, drop_pending_updates=True)
    return {"ok": ok, "set_to": url}

@app.get("/delete-webhook")
async def delete_webhook():
    if not telegram_app:
        raise HTTPException(status_code=503, detail="Telegram app not ready")
    ok = await telegram_app.bot.delete_webhook(drop_pending_updates=False)
    return {"ok": ok}

# ===== Telegram Webhook endpoint =====
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
