# server.py
# -*- coding: utf-8 -*-
import os
import logging
import secrets

from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters,
)

# המודול של הבוט שלך כפי שהוא בריפו
import niftii_bot as B

# ===== לוגים + ENV =====
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("server")

load_dotenv(override=True)

TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
PUBLIC_URL = os.getenv("PUBLIC_URL", "").strip()  # למשל: https://sweet-xxxxx.koyeb.app
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip() or secrets.token_urlsafe(24)

if not TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN is missing")

# ===== בניית אפליקציית PTB =====
def build_application() -> Application:
    app = Application.builder().token(TOKEN).build()

    # חשוב: להשתמש בקבועים של B (ולא range(5) מקומי)
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
        per_message=True,  # קריטי כדי ש-CallbackQuery יעקבו אחרי כל הודעה
    )

    app.add_handler(CommandHandler("start", B.start))
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(B.callback_router))

    # הודעות טקסט (כפתורי ה-ReplyKeyboard)
    app.add_handler(MessageHandler(filters.Text(B.MENU_TXT_CONTACT), B.handle_contact))
    app.add_handler(MessageHandler(filters.Text(B.MENU_TXT_SITE), B.handle_website))
    app.add_handler(MessageHandler(filters.Text(B.MENU_TXT_MAIN), B.handle_main_menu))
    app.add_handler(MessageHandler(filters.Text(B.MENU_TXT_SHOP), B.handle_purchase_shop))

    return app

# ===== FastAPI =====
app = FastAPI()
telegram_app: Application | None = None

@app.on_event("startup")
async def on_startup():
    global telegram_app
    telegram_app = build_application()
    await telegram_app.initialize()
    await telegram_app.start()
    log.info("Application started")
    if PUBLIC_URL:
        log.info(f"Public URL: {PUBLIC_URL}")
    else:
        log.warning("PUBLIC_URL is empty; set-webhook endpoint will fail until you set it.")

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
