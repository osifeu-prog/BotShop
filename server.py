# -*- coding: utf-8 -*-
import os
import logging
import asyncio
from typing import Optional

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

# --- env ---
load_dotenv()
PUBLIC_URL = os.getenv("PUBLIC_URL", "").strip()
WEBHOOK_SECRET = os.getenv(
    "WEBHOOK_SECRET",
    "Q3Zb7r9kT2pX1mN4F8hU6wY0aBcDeGHi"  # ברירת מחדל תואמת למה שהשתמשת עד עכשיו
).strip()

# --- logging ---
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO
)
log = logging.getLogger("server")

# --- import your bot module ---
import niftii_bot as B  # <-- לא נוגעים בעיצוב שלך, רק משתמשים בו

# --- FastAPI app ---
app = FastAPI()
telegram_app: Optional[Application] = None

def build_application() -> Application:
    """בונה את אפליקציית ה-Telegram ומחבר את כל ההנדלרים מהבוט שלך (B)."""
    if not getattr(B, "TOKEN", ""):
        raise RuntimeError("TELEGRAM_TOKEN חסר ב-niftii_bot.py או ב-.env")

    app_ = Application.builder().token(B.TOKEN).build()

    # Conversation (עם התיקון: per_message=False)
    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(B.select_card, pattern=r"^select_card$"),
            CallbackQueryHandler(B.upload_receipt, pattern=r"^upload_receipt$"),
        ],
        states={
            B.PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, B.receive_price)],
            B.FIRST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, B.receive_first_name)],
            B.LAST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, B.receive_last_name)],
            B.PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, B.receive_phone)],
            B.PAYMENT_CONFIRMATION: [MessageHandler(filters.PHOTO, B.receive_receipt)],
        },
        fallbacks=[],
        per_chat=True,
        per_message=False,  # חשוב!
    )

    # Handlers מהבוט שלך
    app_.add_handler(CommandHandler("start", B.start))
    app_.add_handler(conv_handler)
    app_.add_handler(CallbackQueryHandler(B.callback_router))

    # Handlers לכפתורי תפריט (טקסט רגיל)
    app_.add_handler(MessageHandler(filters.Text("☎️ צור קשר 📞"), B.handle_contact))
    app_.add_handler(MessageHandler(filters.Text("🌐 אתר"), B.handle_website))
    app_.add_handler(MessageHandler(filters.Text("🔄 תפריט ראשי 📚"), B.handle_main_menu))
    app_.add_handler(MessageHandler(filters.Text("✍🏻 רכישת חנות 🎯"), B.handle_purchase_shop))

    return app_

@app.on_event("startup")
async def on_startup():
    global telegram_app

    # איטרציה נכונה ל-Windows/uvicorn אם צריך
    if os.name == "nt":
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        except Exception:
            pass

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
        log.info("Application stopped")

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
    if not PUBLIC_URL or not PUBLIC_URL.startswith("https://"):
        raise HTTPException(status_code=400, detail="PUBLIC_URL env var is missing or not https")
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
