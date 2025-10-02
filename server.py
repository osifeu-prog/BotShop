# -*- coding: utf-8 -*-
import os
import asyncio
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

# נטען ENV
load_dotenv()

TOKEN = (os.getenv("TELEGRAM_TOKEN") or "").strip()
PUBLIC_URL = (os.getenv("PUBLIC_URL") or "").strip()
WEBHOOK_SECRET = (os.getenv("WEBHOOK_SECRET") or os.getenv("WEBHOOK_PATH") or "").strip()

if not TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN is missing")

# מייבא את קובץ הבוט שלך אחד לאחד
import niftii_bot as B  # <- חשוב: זה השם של הקובץ שהדבקת

logger = logging.getLogger("server")
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)

app = FastAPI()
telegram_app: Application | None = None


def build_application() -> Application:
    """בונה את אפליקציית ה-Telegram ו-מוסיף את כל ההנדלרים מהבוט שלך."""
    tg = Application.builder().token(TOKEN).build()

    # ConversationHandler עם ה-fix
    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(B.select_card, pattern="^select_card$"),
            CallbackQueryHandler(B.upload_receipt, pattern="^upload_receipt$"),
        ],
        states={
            B.PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, B.receive_price)],
            B.FIRST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, B.receive_first_name)],
            B.LAST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, B.receive_last_name)],
            B.PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, B.receive_phone)],
            B.PAYMENT_CONFIRMATION: [MessageHandler(filters.PHOTO, B.receive_receipt)],
        },
        fallbacks=[],
        per_message=True,  # <<< התיקון שמונע "היתקעות" אחרי הזנת מחיר
    )

    # Handlers זהים למה שיש לך ב-niftii_bot.py
    tg.add_handler(CommandHandler("start", B.start))
    tg.add_handler(conv_handler)
    tg.add_handler(CallbackQueryHandler(B.callback_router))

    tg.add_handler(MessageHandler(filters.Text("☎️ צור קשר 📞"), B.handle_contact))
    tg.add_handler(MessageHandler(filters.Text("🌐 אתר"), B.handle_website))
    tg.add_handler(MessageHandler(filters.Text("🔄 תפריט ראשי 📚"), B.handle_main_menu))
    tg.add_handler(MessageHandler(filters.Text("✍🏻 רכישת חנות 🎯"), B.handle_purchase_shop))

    return tg


@app.on_event("startup")
async def on_startup():
    """אתחול אפליקציית הטלגרם בתוך שרת FastAPI (מוד webhook)."""
    global telegram_app
    if telegram_app is None:
        telegram_app = build_application()
        await telegram_app.initialize()
        await telegram_app.start()
        logger.info("Application started")


@app.on_event("shutdown")
async def on_shutdown():
    """כיבוי נקי."""
    global telegram_app
    if telegram_app is not None:
        await telegram_app.stop()
        await telegram_app.shutdown()
        telegram_app = None
        logger.info("Application stopped")


@app.get("/healthz")
def healthz():
    return PlainTextResponse("ok")


@app.get("/")
def root():
    return PlainTextResponse("OK")


@app.get("/set-webhook")
async def set_webhook():
    """מגדיר webhook לכתובת PUBLIC_URL שלך עם ה-SECRET מה-ENV."""
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
    """נקודת הקבלה של טלגרם (POST)."""
    if not telegram_app:
        raise HTTPException(status_code=503, detail="Telegram app not ready")
    if not WEBHOOK_SECRET or secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")

    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)

    return JSONResponse({"ok": True})
