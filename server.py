# -*- coding: utf-8 -*-
import os
import logging
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

# ========= טעינת מודול הבוט שלך =========
# מומלץ מאוד שהקובץ ייקרא niftii_bot.py כדי לא להתנגש עם מודולים אחרים בשם "bot".
try:
    import niftii_bot as B  # << אם שינית את שם הקובץ ל-niftii_bot.py
except ModuleNotFoundError:
    # fallback אם עדיין לא שינית שם קובץ
    import bot as B  # ודא שזה הקובץ שלך בשורש הריפו

log = logging.getLogger("uvicorn")
logging.basicConfig(level=logging.INFO)

# ========= קונפיגורציה מה-ENV =========
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN env var is missing!")

# URL ציבורי של האפליקציה (למשל מה-Koyeb), לדוגמה:
# PUBLIC_URL=https://sweet-eugine-slh-0c878339.koyeb.app
PUBLIC_URL = os.getenv("PUBLIC_URL", "").strip()

# סוד ה-Webhook (מחרוזת שרירותית שאתה בוחר). שמור אותה ב-Koyeb כ-ENV.
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip() or "devsecret-change-me"

# מומלץ להריץ וורקר יחיד ב-uvicorn כדי למנוע כפילויות:
# Procfile: web: uvicorn server:app --host 0.0.0.0 --port $PORT --workers 1

# ========= FastAPI =========
app = FastAPI(title="Niftii Bot Server", version="1.0.0")
telegram_app: Application | None = None


def build_application() -> Application:
    """
    בונה את אובייקט ה-Application של PTB ומוסיף את כל ההנדלרים מקובץ הבוט שלך (B).
    """
    log.info("Using bot module file: %s", getattr(B, "__file__", "UNKNOWN"))

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Conversation states מגיעים מקובץ הבוט
    PRICE = B.PRICE
    FIRST_NAME = B.FIRST_NAME
    LAST_NAME = B.LAST_NAME
    PHONE = B.PHONE
    PAYMENT_CONFIRMATION = B.PAYMENT_CONFIRMATION

    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(B.select_card, pattern=r"^select_card$"),
            CallbackQueryHandler(B.upload_receipt, pattern=r"^upload_receipt$"),
        ],
        states={
            PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, B.receive_price)],
            FIRST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, B.receive_first_name)],
            LAST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, B.receive_last_name)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, B.receive_phone)],
            PAYMENT_CONFIRMATION: [MessageHandler(filters.PHOTO, B.receive_receipt)],
        },
        fallbacks=[],
        per_message=False,  # כמו אצלך, כדי לא להציף אזהרות זה בסדר
    )

    # פקודות/כפתורים
    application.add_handler(CommandHandler("start", B.start))
    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(B.callback_router))

    # כפתורי ה-ReplyKeyboard — יש התאמה מלאה לטקסטים שלך
    application.add_handler(MessageHandler(filters.Text("☎️ צור קשר 📞"), B.handle_contact))
    application.add_handler(MessageHandler(filters.Text("🌐 אתר"), B.handle_website))
    application.add_handler(MessageHandler(filters.Text("🔄 תפריט ראשי 📚"), B.handle_main_menu))
    application.add_handler(MessageHandler(filters.Text("✍🏻 רכישת חנות 🎯"), B.handle_purchase_shop))

    return application


@app.on_event("startup")
async def on_startup():
    global telegram_app
    telegram_app = build_application()

    # מפעילים את אפליקציית הטלגרם במצב webhook (ללא polling)
    await telegram_app.initialize()
    await telegram_app.start()

    me = await telegram_app.bot.get_me()
    log.info("Application started")
    log.info("Bot: @%s (%s)", me.username, me.id)
    if PUBLIC_URL:
        log.info("Public URL: %s", PUBLIC_URL)
    else:
        log.warning("PUBLIC_URL is not set. Use /set-webhook after setting it.")


@app.on_event("shutdown")
async def on_shutdown():
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
    """
    קובע webhook לכתובת: {PUBLIC_URL}/webhook/{WEBHOOK_SECRET}
    שים לב: חייב להיות SSL תקין ו-PUBLIC_URL תקין.
    """
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


@app.get("/get-webhook-info")
async def get_webhook_info():
    if not telegram_app:
        raise HTTPException(status_code=503, detail="Telegram app not ready")
    info = await telegram_app.bot.get_webhook_info()
    return JSONResponse(info.to_dict())


@app.post("/webhook/{secret}")
async def webhook(secret: str, request: Request):
    """
    נקודת הקצה ש-Telegram קוראת אליה. מאמתים את ה-secret לפני עיבוד העדכון.
    """
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")

    if not telegram_app:
        raise HTTPException(status_code=503, detail="Telegram app not ready")

    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return JSONResponse({"ok": True})
