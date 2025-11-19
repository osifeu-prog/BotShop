from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Set

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, validator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from telegram import Update
from tenacity import retry, stop_after_attempt, wait_exponential

from core.logging import logger
from core.metrics import MESSAGES_RECEIVED, REQUEST_DURATION
from core.cache import MESSAGES_FILE
from core.db import get_approval_stats, DatabaseManager
from bot.config import Config, warnings as config_warnings
from bot.telegram_manager import TelegramAppManager

from prometheus_client import generate_latest


class TelegramWebhookUpdate(BaseModel):
    update_id: int
    message: Optional[Dict[str, Any]] = None
    callback_query: Optional[Dict[str, Any]] = None
    edited_message: Optional[Dict[str, Any]] = None

    @validator("update_id")
    def validate_update_id(cls, v: int) -> int:
        if v < 0:
            raise ValueError("update_id must be positive")
        return v


class SecurityManager:
    """Simple in‑memory protection against duplicate/empty updates."""

    _recent_updates: Set[int] = set()
    _last_cleanup: datetime = datetime.now()

    @classmethod
    def is_duplicate_update(cls, update_id: int) -> bool:
        now = datetime.now()
        if now - cls._last_cleanup > timedelta(minutes=10):
            cls._recent_updates.clear()
            cls._last_cleanup = now

        if update_id in cls._recent_updates:
            return True

        cls._recent_updates.add(update_id)
        return False


def validate_environment():
    required = ["BOT_TOKEN", "WEBHOOK_URL"]
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    if not MESSAGES_FILE.exists():
        logger.warning("messages/messages.md not found – using embedded fallbacks only")


# FastAPI app & rate limiter
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="SLHNET Telegram Gateway", version="2.0.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


async def send_log_message(text: str) -> None:
    """Send a log/alert message to the admin chat (best effort)."""
    try:
        app_instance = TelegramAppManager.get_app()
    except Exception as e:
        logger.warning("send_log_message: Telegram app not ready: %s", e)
        return

    admin_chat_id = Config.ADMIN_ALERT_CHAT_ID
    try:
        await app_instance.bot.send_message(chat_id=admin_chat_id, text=text, disable_notification=True)
    except Exception as e:  # pragma: no cover - best effort
        logger.warning("Failed to send admin log message: %s", e)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def send_message_with_retry(chat_id: int, text: str, **kwargs):
    app_instance = TelegramAppManager.get_app()
    return await app_instance.bot.send_message(chat_id=chat_id, text=text, **kwargs)


@app.on_event("startup")
async def startup_event():
    """Full startup with config validation, Telegram init and logging."""
    try:
        validate_environment()

        for w in config_warnings:
            logger.warning("Config warning: %s", w)

        if config_warnings:
            await send_log_message("⚠️ **אזהרות אתחול:**\n" + "\n".join(config_warnings))

        # Initialize Telegram Application
        await TelegramAppManager.start()

        app_instance = TelegramAppManager.get_app()
        bot_info = await app_instance.bot.get_me()
        logger.info("Bot started successfully", username=bot_info.username)

        await send_log_message(f"✅ SLHNET Bot started successfully as @{bot_info.username}")

    except Exception as e:
        logger.critical("CRITICAL: Failed to start application: %s", e)
        raise


@app.on_event("shutdown")
async def shutdown_event():
    try:
        await TelegramAppManager.stop()
    except Exception as e:
        logger.warning("Error while stopping Telegram app: %s", e)

    try:
        await DatabaseManager.close()
    except Exception as e:
        logger.warning("Error while closing DB pool: %s", e)


@app.get("/healthz")
async def healthz():
    return {
        "status": "ok",
        "service": "slhnet-telegram-gateway",
        "timestamp": datetime.utcnow().isoformat(),
        "version": app.version,
    }


@app.get("/health/detailed")
async def detailed_health():
    health_info: Dict[str, Any] = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {},
    }

    # Telegram bot
    try:
        app_instance = TelegramAppManager.get_app()
        bot_info = await app_instance.bot.get_me()
        health_info["services"]["telegram_bot"] = {
            "status": "healthy",
            "username": bot_info.username,
        }
    except Exception as e:
        health_info["services"]["telegram_bot"] = {"status": "unhealthy", "detail": str(e)}
        health_info["status"] = "degraded"

    # Database
    try:
        stats = await get_approval_stats()
        health_info["services"]["database"] = {"status": "healthy", "sample": stats}
    except Exception as e:
        health_info["services"]["database"] = {"status": "unhealthy", "detail": str(e)}
        health_info["status"] = "degraded"

    # Files
    health_info["services"]["files"] = {
        "messages_file": MESSAGES_FILE.exists(),
    }

    return health_info


@app.get("/api/metrics/finance")
async def finance_metrics():
    stats = await get_approval_stats()
    return {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        **stats,
    }


@app.get("/metrics")
async def metrics():
    data = generate_latest()
    return Response(data, media_type="text/plain")


@app.post("/webhook")
@limiter.limit("50/minute")
async def telegram_webhook(update: TelegramWebhookUpdate, request: Request):
    """Webhook endpoint with basic security protections."""
    MESSAGES_RECEIVED.inc()

    try:
        # Duplicate protection
        if SecurityManager.is_duplicate_update(update.update_id):
            logger.warning("Duplicate update detected", update_id=update.update_id)
            return JSONResponse({"status": "duplicate"})

        # Spam / invalid updates
        if not any([update.message, update.callback_query, update.edited_message]):
            logger.warning("Empty update received", update_id=update.update_id)
            return JSONResponse({"status": "invalid"}, status_code=400)

        # Convert to PTB Update
        app_instance = TelegramAppManager.get_app()
        raw_update = update.model_dump()
        ptb_update = Update.de_json(raw_update, app_instance.bot)

        if ptb_update:
            with REQUEST_DURATION.time():
                await app_instance.process_update(ptb_update)
            return JSONResponse({"status": "processed"})
        else:
            return JSONResponse({"status": "no_update"}, status_code=400)

    except Exception as e:
        logger.error("Webhook error: %s", e)
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=500)
