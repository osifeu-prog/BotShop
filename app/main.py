import logging
import json

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

from telegram import Update

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.session import init_db
from app.bot.application import build_application

logger = logging.getLogger(__name__)

settings = get_settings()
setup_logging(settings.LOG_LEVEL)

app = FastAPI(title=f"{settings.SERVICE_NAME} BotShop")

telegram_app = build_application()


@app.on_event("startup")
async def on_startup() -> None:
    logger.info("Starting up FastAPI + Telegram Application")
    await init_db()

    # Initialize & start PTB application
    await telegram_app.initialize()
    await telegram_app.start()

    # Set webhook if base URL provided
    if settings.WEBHOOK_BASE_URL:
        url = settings.WEBHOOK_BASE_URL.rstrip("/") + "/" + settings.WEBHOOK_PATH.lstrip("/")
        logger.info("Setting Telegram webhook to %s", url)
        await telegram_app.bot.set_webhook(url=url)
    else:
        logger.warning("WEBHOOK_BASE_URL not set – webhook will NOT be configured automatically")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    logger.info("Shutting down Telegram Application")
    await telegram_app.stop()
    await telegram_app.shutdown()


@app.post("/{path:path}")
async def telegram_webhook_any(path: str, request: Request):
    # Only accept the configured webhook path; everything else 404
    if path != settings.WEBHOOK_PATH:
        raise HTTPException(status_code=404, detail="Not Found")

    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return JSONResponse({"ok": True})


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/meta")
async def meta():
    return {
        "service": settings.SERVICE_NAME,
        "webhook_path": settings.WEBHOOK_PATH,
        "has_webhook_base_url": bool(settings.WEBHOOK_BASE_URL),
        "admins": settings.TELEGRAM_ADMIN_IDS,
    }
