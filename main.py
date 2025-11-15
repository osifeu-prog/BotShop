# main.py
import os
import logging
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime
from http import HTTPStatus
from typing import Deque, Set, Literal, Optional, Dict, Any, List

from fastapi import FastAPI, Request, Response, HTTPException
from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from telegram.error import RetryAfter


# =========================
# ×œ×•×’×™× ×’ ×‘×،×™×،×™
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("gateway-bot")

# =========================
# DB ×گ×•×¤×¦×™×•× ×œ×™ (db.py)
# =========================
try:
    from db import (
        init_schema,
        log_payment,
        update_payment_status,
        store_user,
        add_referral,
        get_top_referrers,
        get_monthly_payments,
        get_approval_stats,
        create_reward,
    )
    DB_AVAILABLE = True
    logger.info("DB module loaded successfully, DB logging enabled.")
except Exception as e:
    logger.warning("DB not available (missing db.py or error loading it): %s", e)
    DB_AVAILABLE = False

# =========================
# ×‍×©×ھ× ×™ ×،×‘×™×‘×” ×—×™×•× ×™×™×‌
# =========================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")  # ×—×™×™×‘ ×œ×›×œ×•×œ /webhook ×‘×،×•×£

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is not set")

if not WEBHOOK_URL:
    raise RuntimeError("WEBHOOK_URL environment variable is not set")

logger.info("Starting bot with WEBHOOK_URL=%s", WEBHOOK_URL)

# =========================
# ×§×‘×•×¢×™×‌ ×©×œ ×”×‍×¢×¨×›×ھ ×©×œ×ڑ
# =========================

# ×§×‘×•×¦×ھ ×”×§×”×™×œ×” (×گ×—×¨×™ ×گ×™×©×•×¨ ×ھ×©×œ×•×‌)
COMMUNITY_GROUP_LINK = "https://t.me/+HIzvM8sEgh1kNWY0"
COMMUNITY_GROUP_ID = -1002981609404  # ×œ×گ ×—×•×‘×” ×œ×©×™×‍×•×© ×›×¨×’×¢

# ×§×‘×•×¦×ھ ×ھ×‍×™×›×”
SUPPORT_GROUP_LINK = "https://t.me/+1ANn25HeVBoxNmRk"
SUPPORT_GROUP_ID = -1001651506661  # ×›×¨×’×¢ ×¨×§ ×œ×™× ×§

# ×‍×ھ×›× ×ھ ×”×‍×¢×¨×›×ھ (×گ×ھ×”)
DEVELOPER_USER_ID = 224223270

# ×§×‘×•×¦×ھ ×œ×•×’×™×‌ ×•×ھ×©×œ×•×‍×™×‌ (×¨×§ ×œ×‍×گ×¨×’× ×™×‌, ×œ×گ ×™×•×¦×’ ×œ×‍×©×ھ×‍×©)
PAYMENTS_LOG_CHAT_ID = -1001748319682

# ×œ×™× ×§×™ ×ھ×©×œ×•×‌ (×‍×”-ENV ×¢×‌ ×‘×¨×™×¨×ھ ×‍×—×“×œ)
PAYBOX_URL = os.environ.get(
    "PAYBOX_URL",
    "https://links.payboxapp.com/1SNfaJ6XcYb",
)
BIT_URL = os.environ.get(
    "BIT_URL",
    "https://www.bitpay.co.il/app/share-info?i=190693822888_19l4oyvE",
)
PAYPAL_URL = os.environ.get(
    "PAYPAL_URL",
    "https://paypal.me/osifdu",
)

# ×œ×™× ×§ ×œ×“×£ ×”× ×—×™×ھ×” (GitHub Pages) â€“ ×‘×©×‘×™×œ ×›×¤×ھ×•×¨ ×”×©×™×ھ×•×£
LANDING_URL = os.environ.get(
    "LANDING_URL",
    "https://osifeu-prog.github.io/botshop/",
)

# Token ×§×ک×ں ×œ×“×©×‘×•×¨×“ API (/admin/stats)
ADMIN_DASH_TOKEN = os.environ.get("ADMIN_DASH_TOKEN")

# × ×ھ×™×‘ ×”×ھ×‍×•× ×” ×”×¨×گ×©×™×ھ ×©×œ /start
START_IMAGE_PATH = os.environ.get(
    "START_IMAGE_PATH",
    "assets/start_banner.jpg",  # ×ھ×•×•×“×گ ×©×”×ھ×‍×•× ×” ×”×–×• ×§×™×™×‍×ھ ×‘×¤×¨×•×™×§×ک
)

# ×¤×¨×ک×™ ×ھ×©×œ×•×‌
BANK_DETAILS = (
    "ًںڈ¦ *×ھ×©×œ×•×‌ ×‘×”×¢×‘×¨×” ×‘× ×§×گ×™×ھ*\n\n"
    "×‘× ×§ ×”×¤×•×¢×œ×™×‌\n"
    "×،× ×™×£ ×›×¤×¨ ×’× ×™×‌ (153)\n"
    "×—×©×‘×•×ں 73462\n"
    "×”×‍×•×ک×‘: ×§×گ×•×¤×‍×ں ×¦×‘×™×§×”\n\n"
    "×،×›×•×‌: *39 ×©\"×—*\n"
)

PAYBOX_DETAILS = (
    "ًں“² *×ھ×©×œ×•×‌ ×‘×‘×™×ک / ×¤×™×™×‘×•×§×، / PayPal*\n\n"
    "×گ×¤×©×¨ ×œ×©×œ×‌ ×“×¨×ڑ ×”×گ×¤×œ×™×§×¦×™×•×ھ ×©×œ×ڑ ×‘×‘×™×ک ×گ×• ×¤×™×™×‘×•×§×،.\n"
    "×§×™×©×•×¨×™ ×”×ھ×©×œ×•×‌ ×”×‍×¢×•×“×›× ×™×‌ ×‍×•×¤×™×¢×™×‌ ×‘×›×¤×ھ×•×¨×™×‌ ×œ×‍×ک×”.\n\n"
    "×،×›×•×‌: *39 ×©\"×—*\n"
)

TON_DETAILS = (
    "ًں’ژ *×ھ×©×œ×•×‌ ×‘-TON (×ک×œ×’×¨×‌ ×§×¨×™×¤×ک×•)*\n\n"
    "×گ×‌ ×™×© ×œ×ڑ ×›×‘×¨ ×گ×¨× ×§ ×ک×œ×’×¨×‌ (TON Wallet), ×گ×¤×©×¨ ×œ×©×œ×‌ ×’×‌ ×™×©×™×¨×•×ھ ×‘×§×¨×™×¤×ک×•.\n\n"
    "×گ×¨× ×§ ×œ×§×‘×œ×ھ ×”×ھ×©×œ×•×‌:\n"
    "`UQCr743gEr_nqV_0SBkSp3CtYS_15R3LDLBvLmKeEv7XdGvp`\n\n"
    "×،×›×•×‌: *39 ×©\"×—* (×©×•×•×” ×¢×¨×ڑ ×‘-TON)\n\n"
    "ًں‘€ ×‘×§×¨×•×‘ × ×—×œ×§ ×’×‌ ×ک×•×§× ×™ *SLH* ×™×™×—×•×“×™×™×‌ ×¢×œ ×¨×©×ھ TON ×•×—×œ×§ ×‍×”×‍×©×ھ×ھ×¤×™×‌ ×™×§×‘×œ×• NFT\n"
    "×¢×œ ×¤×¢×™×œ×•×ھ, ×©×™×ھ×•×¤×™×‌ ×•×”×©×ھ×ھ×¤×•×ھ ×‘×§×”×™×œ×”.\n"
)

# ×گ×“×‍×™× ×™×‌ ×©×™×›×•×œ×™×‌ ×œ×گ×©×¨ / ×œ×“×—×•×ھ ×ھ×©×œ×•×‌
ADMIN_IDS = {DEVELOPER_USER_ID}  # ×گ×¤×©×¨ ×œ×”×•×،×™×£ ×¢×•×“ IDs ×گ×‌ ×ھ×¨×¦×”

PayMethod = Literal["bank", "paybox", "ton"]

# =========================
# Dedup â€“ ×‍× ×™×¢×ھ ×›×¤×™×œ×•×ھ ×ھ×’×•×‘×•×ھ
# =========================
_processed_ids: Deque[int] = deque(maxlen=1000)
_processed_set: Set[int] = set()

def is_duplicate_update(update: Update) -> bool:
    """×‘×•×“×§ ×گ×‌ update ×›×‘×¨ ×ک×•×¤×œ (×¢×´×¤ update_id)"""
    if update is None:
        return False
    uid = update.update_id
    if uid in _processed_set:
        return True
    _processed_set.add(uid)
    _processed_ids.append(uid)
    # × ×™×§×•×™ ×،×ک ×œ×¤×™ ×”-deque
    if len(_processed_set) > len(_processed_ids) + 10:
        valid = set(_processed_ids)
        _processed_set.intersection_update(valid)
    return False

# =========================
# ×–×™×›×¨×•×ں ×¤×©×•×ک ×œ×ھ×©×œ×•×‍×™×‌ ×گ×—×¨×•× ×™×‌ + ×“×—×™×•×ھ ×‍×‍×ھ×™× ×•×ھ
# =========================
# bot_data["payments"][user_id] => dict ×¢×‌ ×¤×¨×ک×™ ×”×¢×،×§×” ×”×گ×—×¨×•× ×”
def get_payments_store(context: ContextTypes.DEFAULT_TYPE) -> Dict[int, Dict[str, Any]]:
    store = context.application.bot_data.get("payments")
    if store is None:
        store = {}
        context.application.bot_data["payments"] = store
    return store

# bot_data["pending_rejects"][admin_id] = target_user_id
def get_pending_rejects(context: ContextTypes.DEFAULT_TYPE) -> Dict[int, int]:
    store = context.application.bot_data.get("pending_rejects")
    if store is None:
        store = {}
        context.application.bot_data["pending_rejects"] = store
    return store

# =========================
# ×گ×¤×œ×™×§×¦×™×™×ھ Telegram
# =========================
ptb_app: Application = (
    Application.builder()
    .updater(None)  # ×گ×™×ں polling â€“ ×¨×§ webhook
    .token(BOT_TOKEN)
    .build()
)

# =========================
# ×¢×–×¨×™ UI (×‍×§×©×™×‌)
# =========================

def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("ًںڑ€ ×”×¦×ک×¨×¤×•×ھ ×œ×§×”×™×œ×ھ ×”×¢×،×§×™×‌ (39 â‚ھ)", callback_data="join"),
        ],
        [
            InlineKeyboardButton("â„¹ ×‍×” ×گ× ×™ ×‍×§×‘×œ?", callback_data="info"),
        ],
        [
            InlineKeyboardButton("ًں”— ×©×ھ×£ ×گ×ھ ×©×¢×¨ ×”×§×”×™×œ×”", callback_data="share"),
        ],
        [
            InlineKeyboardButton("ًں†ک ×ھ×‍×™×›×”", callback_data="support"),
        ],
    ])

def payment_methods_keyboard() -> InlineKeyboardMarkup:
    """×‘×—×™×¨×ھ ×،×•×’ ×ھ×©×œ×•×‌ (×œ×•×’×™ â€“ ×œ×گ ×œ×™× ×§×™×‌)"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("ًںڈ¦ ×”×¢×‘×¨×” ×‘× ×§×گ×™×ھ", callback_data="pay_bank"),
        ],
        [
            InlineKeyboardButton("ًں“² ×‘×™×ک / ×¤×™×™×‘×•×§×، / PayPal", callback_data="pay_paybox"),
        ],
        [
            InlineKeyboardButton("ًں’ژ ×ک×œ×’×¨×‌ (TON)", callback_data="pay_ton"),
        ],
        [
            InlineKeyboardButton("â¬… ×—×–×¨×” ×œ×ھ×¤×¨×™×ک ×¨×گ×©×™", callback_data="back_main"),
        ],
    ])

def payment_links_keyboard() -> InlineKeyboardMarkup:
    """×›×¤×ھ×•×¨×™ ×œ×™× ×§×™×‌ ×گ×‍×™×ھ×™×™×‌ ×œ×ھ×©×œ×•×‌"""
    buttons = [
        [InlineKeyboardButton("ًں“² ×ھ×©×œ×•×‌ ×‘×¤×™×™×‘×•×§×،", url=PAYBOX_URL)],
        [InlineKeyboardButton("ًں“² ×ھ×©×œ×•×‌ ×‘×‘×™×ک", url=BIT_URL)],
        [InlineKeyboardButton("ًں’³ ×ھ×©×œ×•×‌ ×‘-PayPal", url=PAYPAL_URL)],
        [InlineKeyboardButton("â¬… ×—×–×¨×” ×œ×ھ×¤×¨×™×ک ×¨×گ×©×™", callback_data="back_main")],
    ]
    return InlineKeyboardMarkup(buttons)

def support_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("×§×‘×•×¦×ھ ×ھ×‍×™×›×”", url=SUPPORT_GROUP_LINK),
        ],
        [
            InlineKeyboardButton("×¤× ×™×” ×œ×‍×ھ×›× ×ھ ×”×‍×¢×¨×›×ھ", url=f"tg://user?id={DEVELOPER_USER_ID}"),
        ],
        [
            InlineKeyboardButton("â¬… ×—×–×¨×” ×œ×ھ×¤×¨×™×ک ×¨×گ×©×™", callback_data="back_main"),
        ],
    ])

def admin_approval_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """×›×¤×ھ×•×¨×™ ×گ×™×©×•×¨/×“×—×™×™×” ×œ×œ×•×’×™×‌"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("âœ… ×گ×©×¨ ×ھ×©×œ×•×‌", callback_data=f"adm_approve:{user_id}"),
            InlineKeyboardButton("â‌Œ ×“×—×” ×ھ×©×œ×•×‌", callback_data=f"adm_reject:{user_id}"),
        ],
    ])

def admin_menu_keyboard() -> InlineKeyboardMarkup:
    """×ھ×¤×¨×™×ک ×گ×“×‍×™×ں"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("ًں“ٹ ×،×ک×ک×•×، ×‍×¢×¨×›×ھ", callback_data="adm_status"),
        ],
        [
            InlineKeyboardButton("ًں“ˆ ×‍×•× ×™ ×ھ×‍×•× ×”", callback_data="adm_counters"),
        ],
        [
            InlineKeyboardButton("ًں’، ×¨×¢×™×•× ×•×ھ ×œ×¤×™×¦'×¨×™×‌", callback_data="adm_ideas"),
        ],
    ])

# =========================
# ×¢×•×–×¨: ×©×œ×™×—×ھ ×ھ×‍×•× ×ھ ×”-START ×¢×‌ ×‍×•× ×™×‌
# =========================

async def send_start_image(context: ContextTypes.DEFAULT_TYPE, chat_id: int, mode: str = "view") -> None:
    """
    mode:
      - "view": ×”×¦×’×” ×‘-/start, ×‍×¢×œ×” ×‍×•× ×” ×¦×¤×™×•×ھ
      - "download": ×¢×•×ھ×§ ×‍×‍×•×،×¤×¨ ×œ×‍×©×ھ×‍×© ×گ×—×¨×™ ×گ×™×©×•×¨ ×ھ×©×œ×•×‌
      - "reminder": ×ھ×–×›×•×¨×ھ ×‘×§×‘×•×¦×ھ ×œ×•×’×™×‌ â€“ ×‘×œ×™ ×œ×©× ×•×ھ ×‍×•× ×™×‌
    """
    app_data = context.application.bot_data

    views = app_data.get("start_image_views", 0)
    downloads = app_data.get("start_image_downloads", 0)

    caption = ""
    if mode == "view":
        views += 1
        app_data["start_image_views"] = views
        caption = (
            f"ًںŒگ ×©×¢×¨ ×”×›× ×™×،×” ×œ×§×”×™×œ×ھ ×”×¢×،×§×™×‌\n"
            f"×‍×،×¤×¨ ×”×¦×’×” ×›×•×œ×œ: *{views}*\n"
        )
    elif mode == "download":
        downloads += 1
        app_data["start_image_downloads"] = downloads
        caption = (
            "ًںژپ ×–×” ×”×¢×•×ھ×§ ×”×‍×‍×•×،×¤×¨ ×©×œ×ڑ ×©×œ ×©×¢×¨ ×”×§×”×™×œ×”.\n"
            f"×‍×،×¤×¨ ×،×™×“×•×¨×™ ×œ×¢×•×ھ×§: *#{downloads}*\n"
        )
    elif mode == "reminder":
        caption = (
            "âڈ° ×ھ×–×›×•×¨×ھ: ×‘×“×•×§ ×©×”×œ×™× ×§×™×‌ ×©×œ PayBox / Bit / PayPal ×¢×“×™×™×ں ×ھ×§×¤×™×‌.\n\n"
            f"×‍×¦×‘ ×‍×•× ×™×‌ ×›×¨×’×¢:\n"
            f"â€¢ ×”×¦×’×•×ھ ×ھ×‍×•× ×”: {views}\n"
            f"â€¢ ×¢×•×ھ×§×™×‌ ×‍×‍×•×،×¤×¨×™×‌ ×©× ×©×œ×—×•: {downloads}\n"
        )

    try:
        with open(START_IMAGE_PATH, "rb") as f:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=f,
                caption=caption,
                parse_mode="Markdown",
            )
    except FileNotFoundError:
        logger.error("Start image not found at path: %s", START_IMAGE_PATH)
    except Exception as e:
        logger.error("Failed to send start image: %s", e)

# =========================
# Handlers â€“ ×œ×•×’×™×§×ھ ×”×‘×•×ک
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """×ھ×©×•×‘×ھ /start â€“ ×©×¢×¨ ×”×›× ×™×،×” ×œ×§×”×™×œ×” + ×”×¤× ×™×•×ھ (referrals)"""
    message = update.message or update.effective_message
    if not message:
        return

    user = update.effective_user

    # 1. ×©×•×‍×¨×™×‌ ×‍×©×ھ×‍×© ×‘-DB (×گ×‌ ×گ×¤×©×¨)
    if DB_AVAILABLE and user:
        try:
            store_user(user.id, user.username)
        except Exception as e:
            logger.error("Failed to store user: %s", e)

    # 2. ×ک×™×¤×•×œ ×‘-deep link: /start ref_<referrer_id>
    if message.text and message.text.startswith("/start") and user:
        parts = message.text.split()
        if len(parts) > 1 and parts[1].startswith("ref_"):
            try:
                referrer_id = int(parts[1].split("ref_")[1])
                if DB_AVAILABLE and referrer_id != user.id:
                    add_referral(referrer_id, user.id, source="bot_start")
            except Exception as e:
                logger.error("Failed to add referral: %s", e)

    # 3. ×ھ×‍×•× ×” ×‍×‍×•×،×¤×¨×ھ
    await send_start_image(context, message.chat_id, mode="view")

    # 4. ×ک×§×،×ک ×•×ھ×¤×¨×™×ک
    text = (
        "×‘×¨×•×ڑ ×”×‘×گ ×œ×©×¢×¨ ×”×›× ×™×،×” ×œ×§×”×™×œ×ھ ×”×¢×،×§×™×‌ ×©×œ× ×• ًںŒگ\n\n"
        "×›×گ×ں ×گ×ھ×” ×‍×¦×ک×¨×£ ×œ×‍×¢×¨×›×ھ ×©×œ *×¢×،×§×™×‌, ×©×•×ھ×¤×™×‌ ×•×§×”×œ ×™×•×¦×¨ ×¢×¨×ڑ* ×،×‘×™×‘:\n"
        "â€¢ ×©×™×•×•×§ ×¨×©×ھ×™ ×—×›×‌\n"
        "â€¢ × ×›×،×™×‌ ×“×™×’×™×ک×œ×™×™×‌ (NFT, ×ک×•×§× ×™ SLH)\n"
        "â€¢ ×‍×ھ× ×•×ھ, ×”×¤×ھ×¢×•×ھ ×•×¤×¨×،×™×‌ ×¢×œ ×¤×¢×™×œ×•×ھ ×•×©×™×ھ×•×¤×™×‌\n\n"
        "×‍×” ×ھ×§×‘×œ ×‘×”×¦×ک×¨×¤×•×ھ?\n"
        "âœ… ×’×™×©×” ×œ×§×‘×•×¦×ھ ×¢×،×§×™×‌ ×¤×¨×ک×™×ھ\n"
        "âœ… ×œ×‍×™×“×” ×‍×©×•×ھ×¤×ھ ×گ×™×ڑ ×œ×™×™×¦×¨ ×”×›× ×،×•×ھ ×‍×©×™×•×•×§ ×”×گ×§×•-×،×™×،×ک×‌ ×©×œ× ×•\n"
        "âœ… ×’×™×©×” ×œ×‍×‘×¦×¢×™×‌ ×©×™×—×•×œ×§×• ×¨×§ ×‘×§×”×™×œ×”\n"
        "âœ… ×”×©×ھ×ھ×¤×•×ھ ×¢×ھ×™×“×™×ھ ×‘×—×œ×•×§×ھ ×ک×•×§× ×™ *SLH* ×•-NFT ×™×™×—×•×“×™×™×‌ ×œ×‍×©×ھ×ھ×¤×™×‌ ×¤×¢×™×œ×™×‌\n"
        "âœ… ×‍× ×’× ×•×ں × ×™×§×•×“ ×œ×‍×™ ×©×‍×‘×™×گ ×—×‘×¨×™×‌ â€“ ×©×™×•×¦×’ ×‘×§×”×™×œ×”\n\n"
        "×“×‍×™ ×”×¦×ک×¨×¤×•×ھ ×—×“ض¾×¤×¢×‍×™×™×‌: *39 ×©\"×—*.\n\n"
        "×œ×گ×—×¨ ×گ×™×©×•×¨ ×”×ھ×©×œ×•×‌ *×ھ×§×‘×œ ×§×™×©×•×¨ ×œ×§×”×™×œ×ھ ×”×¢×،×§×™×‌*.\n\n"
        "×›×“×™ ×œ×”×ھ×—×™×œ â€“ ×‘×—×¨ ×‘×گ×¤×©×¨×•×ھ ×”×¨×¦×•×™×”:"
    )

    await message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )

async def info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """×‍×™×“×¢ ×¢×œ ×”×”×ک×‘×•×ھ"""
    query = update.callback_query
    await query.answer()

    text = (
        "â„¹ *×‍×” ×‍×§×‘×œ×™×‌ ×‘×§×”×™×œ×”?*\n\n"
        "ًںڑ€ ×’×™×©×” ×œ×§×‘×•×¦×ھ ×¢×،×§×™×‌ ×،×’×•×¨×” ×©×‘×” ×‍×©×ھ×¤×™×‌ ×¨×¢×™×•× ×•×ھ, ×©×™×ھ×•×¤×™ ×¤×¢×•×œ×” ×•×”×–×“×‍× ×•×™×•×ھ.\n"
        "ًں“ڑ ×”×“×¨×›×•×ھ ×¢×œ ×©×™×•×•×§ ×¨×©×ھ×™, ×‘× ×™×™×ھ ×§×”×™×œ×”, ×‍×›×™×¨×•×ھ ×گ×•× ×œ×™×™×ں ×•× ×›×،×™×‌ ×“×™×’×™×ک×œ×™×™×‌.\n"
        "ًںژپ ×‍×ھ× ×•×ھ ×“×™×’×™×ک×œ×™×•×ھ, NFT ×•×”×ک×‘×•×ھ ×©×™×—×•×œ×§×• ×‘×ھ×•×ڑ ×”×§×”×™×œ×”.\n"
        "ًں’ژ ×‘×¢×ھ×™×“ ×”×§×¨×•×‘ â€“ ×—×œ×•×§×ھ ×ک×•×§× ×™ *SLH* ×¢×œ ×¤×¢×™×œ×•×ھ, ×©×™×ھ×•×¤×™×‌ ×•×”×¤× ×™×•×ھ.\n"
        "ًںڈ† ×‍× ×’× ×•×ں × ×™×§×•×“ ×œ×‍×™ ×©×‍×‘×™×گ ×—×‘×¨×™×‌ â€“ ×©×™×•×¦×’ ×‘×§×‘×•×¦×” ×•×™×§×‘×œ ×¢×“×™×¤×•×ھ ×‘×‍×‘×¦×¢×™×‌.\n\n"
        "×“×‍×™ ×”×¦×ک×¨×¤×•×ھ ×—×“ض¾×¤×¢×‍×™×™×‌: *39 ×©\"×—*.\n\n"
        "×›×“×™ ×œ×”×¦×ک×¨×£ â€“ ×‘×—×¨ ×گ×‍×¦×¢×™ ×ھ×©×œ×•×‌:"
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=payment_methods_keyboard(),
    )

async def join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """×œ×—×™×¦×” ×¢×œ '×”×¦×ک×¨×¤×•×ھ ×œ×§×”×™×œ×”'"""
    query = update.callback_query
    await query.answer()

    text = (
        "ًں”‘ *×”×¦×ک×¨×¤×•×ھ ×œ×§×”×™×œ×ھ ×”×¢×،×§×™×‌ â€“ 39 ×©\"×—*\n\n"
        "×‘×—×¨ ×گ×ھ ×گ×‍×¦×¢×™ ×”×ھ×©×œ×•×‌ ×”×‍×ھ×گ×™×‌ ×œ×ڑ:\n"
        "â€¢ ×”×¢×‘×¨×” ×‘× ×§×گ×™×ھ\n"
        "â€¢ ×‘×™×ک / ×¤×™×™×‘×•×§×، / PayPal\n"
        "â€¢ ×ک×œ×’×¨×‌ (TON)\n\n"
        "×œ×گ×—×¨ ×‘×™×¦×•×¢ ×”×ھ×©×œ×•×‌:\n"
        "1. ×©×œ×— ×›×گ×ں *×¦×™×œ×•×‌ ×‍×،×ڑ ×گ×• ×ھ×‍×•× ×”* ×©×œ ×گ×™×©×•×¨ ×”×ھ×©×œ×•×‌.\n"
        "2. ×”×‘×•×ک ×™×¢×‘×™×¨ ×گ×ھ ×”×گ×™×©×•×¨ ×œ×‍×گ×¨×’× ×™×‌ ×œ×‘×“×™×§×”.\n"
        "3. ×œ×گ×—×¨ ×گ×™×©×•×¨ ×™×“× ×™ ×ھ×§×‘×œ ×§×™×©×•×¨ ×œ×§×”×™×œ×ھ ×”×¢×،×§×™×‌.\n\n"
        "×©×™×‍×• ×œ×‘: *×گ×™×ں ×§×™×©×•×¨ ×œ×§×”×™×œ×” ×œ×¤× ×™ ×گ×™×©×•×¨ ×ھ×©×œ×•×‌.*"
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=payment_methods_keyboard(),
    )

async def support_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """×‍×،×ڑ ×ھ×‍×™×›×”"""
    query = update.callback_query
    await query.answer()

    text = (
        "ًں†ک *×ھ×‍×™×›×” ×•×¢×–×¨×”*\n\n"
        "×‘×›×œ ×©×œ×‘ ×گ×¤×©×¨ ×œ×§×‘×œ ×¢×–×¨×” ×‘×گ×—×“ ×”×¢×¨×•×¦×™×‌ ×”×‘×گ×™×‌:\n\n"
        f"â€¢ ×§×‘×•×¦×ھ ×ھ×‍×™×›×”: {SUPPORT_GROUP_LINK}\n"
        f"â€¢ ×¤× ×™×” ×™×©×™×¨×” ×œ×‍×ھ×›× ×ھ ×”×‍×¢×¨×›×ھ: `tg://user?id={DEVELOPER_USER_ID}`\n\n"
        "×گ×• ×—×–×•×¨ ×œ×ھ×¤×¨×™×ک ×”×¨×گ×©×™:"
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=support_keyboard(),
    )

async def share_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """×›×¤×ھ×•×¨ '×©×ھ×£ ×گ×ھ ×©×¢×¨ ×”×§×”×™×œ×”' â€“ ×©×•×œ×— ×œ×‍×©×ھ×‍×© ×گ×ھ ×”×œ×™× ×§ ×œ×“×£ ×”× ×—×™×ھ×”"""
    query = update.callback_query
    await query.answer()

    text = (
        "ًں”— *×©×ھ×£ ×گ×ھ ×©×¢×¨ ×”×§×”×™×œ×”*\n\n"
        "×›×“×™ ×œ×”×–×‍×™×ں ×—×‘×¨×™×‌ ×œ×§×”×™×œ×”, ×گ×¤×©×¨ ×œ×©×œ×•×— ×œ×”×‌ ×گ×ھ ×”×§×™×©×•×¨ ×”×‘×گ:\n"
        f"{LANDING_URL}\n\n"
        "×‍×•×‍×œ×¥ ×œ×©×ھ×£ ×‘×،×ک×•×¨×™ / ×،×ک×ک×•×، / ×§×‘×•×¦×•×ھ, ×•×œ×”×•×،×™×£ ×›×‍×” ×‍×™×œ×™×‌ ×گ×™×©×™×•×ھ ×‍×©×œ×ڑ.\n"
        "×›×œ ×‍×™ ×©×™×™×›× ×، ×“×¨×ڑ ×”×œ×™× ×§ ×•×™×œ×—×¥ ×¢×œ Start ×‘×‘×•×ک â€“ ×™×¢×‘×•×¨ ×“×¨×ڑ ×©×¢×¨ ×”×§×”×™×œ×”."
    )

    await query.message.reply_text(
        text,
        parse_mode="Markdown",
    )

async def back_main_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """×—×–×¨×” ×œ×ھ×¤×¨×™×ک ×¨×گ×©×™"""
    query = update.callback_query
    await query.answer()
    fake_update = Update(update_id=update.update_id, message=query.message)
    await start(fake_update, context)

async def payment_method_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """×‘×—×™×¨×ھ ×گ×‍×¦×¢×™ ×ھ×©×œ×•×‌"""
    query = update.callback_query
    await query.answer()
    data = query.data

    method: Optional[PayMethod] = None
    details_text = ""

    if data == "pay_bank":
        method = "bank"
        details_text = BANK_DETAILS
    elif data == "pay_paybox":
        method = "paybox"
        details_text = PAYBOX_DETAILS
    elif data == "pay_ton":
        method = "ton"
        details_text = TON_DETAILS

    if method is None:
        return

    context.user_data["last_pay_method"] = method

    text = (
        f"{details_text}\n"
        "×œ×گ×—×¨ ×‘×™×¦×•×¢ ×”×ھ×©×œ×•×‌:\n"
        "1. ×©×œ×— ×›×گ×ں *×¦×™×œ×•×‌ ×‍×،×ڑ ×گ×• ×ھ×‍×•× ×”* ×©×œ ×گ×™×©×•×¨ ×”×ھ×©×œ×•×‌.\n"
        "2. ×”×‘×•×ک ×™×¢×‘×™×¨ ×گ×ھ ×”×گ×™×©×•×¨ ×œ×‍×گ×¨×’× ×™×‌ ×œ×‘×“×™×§×”.\n"
        "3. ×œ×گ×—×¨ ×گ×™×©×•×¨ ×™×“× ×™ ×ھ×§×‘×œ ×§×™×©×•×¨ ×œ×§×”×™×œ×ھ ×”×¢×،×§×™×‌.\n"
    )

    # ×›×گ×ں ×‍×•×¤×™×¢×™×‌ ×”×›×¤×ھ×•×¨×™×‌ ×”×گ×‍×™×ھ×™×™×‌ ×©×œ ×”×ھ×©×œ×•×‌
    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=payment_links_keyboard(),
    )

# =========================
# ×œ×•×’×™×§×ھ ×ھ×©×œ×•×‌ + DB + ×œ×•×’×™×‌
# =========================

async def handle_payment_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    ×¦×™×œ×•×‌ ×©×‍×’×™×¢ ×‍×”×‍×©×ھ×‍×© â€“ × × ×™×— ×©×–×” ×گ×™×©×•×¨ ×ھ×©×œ×•×‌:
    1. × × ×،×” ×œ×”×¢×‘×™×¨ ×œ×§×‘×•×¦×ھ ×”×œ×•×’×™×‌ PAYMENTS_LOG_CHAT_ID
    2. × ×©×‍×•×¨ ×¤×¨×ک×™ ×ھ×©×œ×•×‌ ×گ×—×¨×•×ں ×‘×‍×‘× ×” ×‘×–×™×›×¨×•×ں
    3. ×گ×‌ ×”×œ×•×’×™×‌ × ×›×©×œ×™×‌ â€“ × ×©×œ×— ×گ×œ×™×ڑ (DEVELOPER_USER_ID) ×”×•×“×¢×”
    4. ×‍×—×–×™×¨×™×‌ ×œ×‍×©×ھ×‍×© ×”×•×“×¢×ھ '×‘×‘×“×™×§×”'
    5. ×گ×‌ DB ×–×‍×™×ں â€“ ×¨×•×©×‍×™×‌ ×¨×©×•×‍×ھ 'pending' ×‘×ک×‘×œ×”
    """
    message = update.message
    if not message or not message.photo:
        return

    user = update.effective_user
    chat_id = message.chat_id
    username = f"@{user.username}" if user and user.username else "(×œ×œ×گ ×©×‌ ×‍×©×ھ×‍×©)"

    pay_method = context.user_data.get("last_pay_method", "unknown")
    pay_method_text = {
        "bank": "×”×¢×‘×¨×” ×‘× ×§×گ×™×ھ",
        "paybox": "×‘×™×ک / ×¤×™×™×‘×•×§×، / PayPal",
        "ton": "×ک×œ×’×¨×‌ (TON)",
        "unknown": "×œ×گ ×™×“×•×¢",
    }.get(pay_method, "×œ×گ ×™×“×•×¢")

    caption_log = (
        "ًں“¥ ×”×ھ×§×‘×œ ×گ×™×©×•×¨ ×ھ×©×œ×•×‌ ×—×“×©.\n\n"
        f"user_id = {user.id}\n"
        f"username = {username}\n"
        f"from chat_id = {chat_id}\n"
        f"×©×™×ک×ھ ×ھ×©×œ×•×‌: {pay_method_text}\n\n"
        "×œ×گ×™×©×•×¨:\n"
        f"/approve {user.id}\n"
        f"/reject {user.id} <×،×™×‘×”>\n"
        "(×گ×• ×œ×”×©×ھ×‍×© ×‘×›×¤×ھ×•×¨×™ ×”×گ×™×©×•×¨/×“×—×™×™×” ×‍×ھ×—×ھ ×œ×”×•×“×¢×” ×–×•)\n"
    )

    # × ×™×§×— ×گ×ھ ×”×ھ×‍×•× ×” ×”×’×“×•×œ×” ×‘×™×•×ھ×¨
    photo = message.photo[-1]
    file_id = photo.file_id

    # × ×©×‍×•×¨ ×‘×–×™×›×¨×•×ں ×گ×ھ ×¤×¨×ک×™ ×”×ھ×©×œ×•×‌ ×”×گ×—×¨×•×ں ×©×œ ×”×‍×©×ھ×‍×©
    payments = get_payments_store(context)
    payments[user.id] = {
        "file_id": file_id,
        "pay_method": pay_method_text,
        "username": username,
        "chat_id": chat_id,
    }

    # ×œ×•×’ ×œ-DB (×گ×•×¤×¦×™×•× ×œ×™)
    if DB_AVAILABLE:
        try:
            log_payment(user.id, username, pay_method_text)
        except Exception as e:
            logger.error("Failed to log payment to DB: %s", e)

    # × × ×،×” ×œ×©×œ×•×— ×œ×§×‘×•×¦×ھ ×œ×•×’×™×‌
    try:
        await context.bot.send_photo(
            chat_id=PAYMENTS_LOG_CHAT_ID,
            photo=file_id,
            caption=caption_log,
            reply_markup=admin_approval_keyboard(user.id),
        )
    except Exception as e:
        logger.error("Failed to forward payment photo to log group: %s", e)
        # ×’×™×‘×•×™: × ×©×œ×— ×گ×œ×™×ڑ ×‘×¤×¨×ک×™
        try:
            await context.bot.send_photo(
                chat_id=DEVELOPER_USER_ID,
                photo=file_id,
                caption="(Fallback â€“ ×œ×گ ×”×¦×œ×—×ھ×™ ×œ×©×œ×•×— ×œ×§×‘×•×¦×ھ ×œ×•×’×™×‌)\n\n" + caption_log,
                reply_markup=admin_approval_keyboard(user.id),
            )
        except Exception as e2:
            logger.error("Failed to send fallback payment to developer: %s", e2)

    await message.reply_text(
        "×ھ×•×“×”! ×گ×™×©×•×¨ ×”×ھ×©×œ×•×‌ ×”×ھ×§×‘×œ ×•× ×©×œ×— ×œ×‘×“×™×§×” âœ…\n"
        "×œ×گ×—×¨ ×گ×™×©×•×¨ ×™×“× ×™ ×ھ×§×‘×œ ×‍×‍× ×™ ×§×™×©×•×¨ ×œ×”×¦×ک×¨×¤×•×ھ ×œ×§×”×™×œ×ھ ×”×¢×،×§×™×‌.\n\n"
        "×گ×‌ ×™×© ×©×گ×œ×” ×“×—×•×¤×” â€“ ×گ×¤×©×¨ ×œ×¤× ×•×ھ ×’×‌ ×œ×§×‘×•×¦×ھ ×”×ھ×‍×™×›×”.",
        reply_markup=support_keyboard(),
    )

# =========================
# ×¢×•×–×¨×™×‌ ×œ×گ×™×©×•×¨/×“×—×™×™×” â€“ ×‍×©×•×ھ×£ ×œ×›×¤×ھ×•×¨×™×‌ ×•×œ×¤×§×•×“×•×ھ
# =========================

async def do_approve(target_id: int, context: ContextTypes.DEFAULT_TYPE, source_message) -> None:
    """×œ×•×’×™×§×ھ ×گ×™×©×•×¨ ×ھ×©×œ×•×‌ â€“ ×‍×©×•×ھ×¤×ھ ×œ-/approve ×•×œ×›×¤×ھ×•×¨"""
    text = (
        "âœ… ×”×ھ×©×œ×•×‌ ×©×œ×ڑ ×گ×•×©×¨!\n\n"
        "×‘×¨×•×ڑ ×”×‘×گ ×œ×§×”×™×œ×ھ ×”×¢×،×§×™×‌ ×©×œ× ×• ًںژ‰\n"
        "×”× ×” ×”×§×™×©×•×¨ ×œ×”×¦×ک×¨×¤×•×ھ ×œ×§×”×™×œ×”:\n"
        f"{COMMUNITY_GROUP_LINK}\n\n"
        "×•×›×‍×• ×©×”×‘×ک×—× ×• â€“ ×§×‘×œ ×گ×ھ ×”×¢×•×ھ×§ ×”×‍×‍×•×،×¤×¨ ×©×œ×ڑ ×©×œ ×©×¢×¨ ×”×§×”×™×œ×” ×‘×”×•×“×¢×” × ×¤×¨×“×ھ ًںژپ\n"
        "× ×™×¤×’×© ×‘×¤× ×™×‌ ًں™Œ"
    )
    try:
        await context.bot.send_message(chat_id=target_id, text=text)
        # ×©×œ×™×—×ھ ×”×¢×•×ھ×§ ×”×‍×‍×•×،×¤×¨ ×©×œ ×”×ھ×‍×•× ×”
        await send_start_image(context, target_id, mode="download")

        # ×¢×“×›×•×ں ×،×ک×ک×•×، ×‘-DB
        if DB_AVAILABLE:
            try:
                update_payment_status(target_id, "approved", None)
            except Exception as e:
                logger.error("Failed to update payment status in DB: %s", e)

        if source_message:
            await source_message.reply_text(
                f"×گ×•×©×¨ ×•× ×©×œ×— ×§×™×©×•×¨ + ×¢×•×ھ×§ ×‍×‍×•×،×¤×¨ ×œ×‍×©×ھ×‍×© {target_id}."
            )
    except Exception as e:
        logger.error("Failed to send approval message: %s", e)
        if source_message:
            await source_message.reply_text(f"×©×’×™×گ×” ×‘×©×œ×™×—×ھ ×”×•×“×¢×” ×œ×‍×©×ھ×‍×© {target_id}: {e}")

async def do_reject(target_id: int, reason: str, context: ContextTypes.DEFAULT_TYPE, source_message) -> None:
    """×œ×•×’×™×§×ھ ×“×—×™×™×ھ ×ھ×©×œ×•×‌ â€“ ×‍×©×•×ھ×¤×ھ ×œ-/reject ×•×œ×–×¨×™×‍×ھ ×›×¤×ھ×•×¨"""
    payments = context.application.bot_data.get("payments", {})
    payment_info = payments.get(target_id)

    base_text = (
        "×œ×¦×¢×¨× ×• ×œ×گ ×”×¦×œ×—× ×• ×œ×گ×‍×ھ ×گ×ھ ×”×ھ×©×œ×•×‌ ×©× ×©×œ×—.\n\n"
        f"×،×™×‘×”: {reason}\n\n"
        "×گ×‌ ×œ×“×¢×ھ×ڑ ×‍×“×•×‘×¨ ×‘×ک×¢×•×ھ â€“ ×گ× ×گ ×¤× ×” ×گ×œ×™× ×• ×¢×‌ ×¤×¨×ک×™ ×”×ھ×©×œ×•×‌ ×گ×• × ×،×” ×œ×©×œ×•×— ×‍×—×“×©."
    )

    try:
        if payment_info and payment_info.get("file_id"):
            # ×©×œ×™×—×ھ ×¦×™×œ×•×‌ + ×”×،×‘×¨
            await context.bot.send_photo(
                chat_id=target_id,
                photo=payment_info["file_id"],
                caption=base_text,
            )
        else:
            await context.bot.send_message(chat_id=target_id, text=base_text)

        # ×¢×“×›×•×ں ×،×ک×ک×•×، ×‘-DB
        if DB_AVAILABLE:
            try:
                update_payment_status(target_id, "rejected", reason)
            except Exception as e:
                logger.error("Failed to update payment status in DB: %s", e)

        if source_message:
            await source_message.reply_text(
                f"×”×ھ×©×œ×•×‌ ×©×œ ×”×‍×©×ھ×‍×© {target_id} × ×“×—×” ×•×”×•×“×¢×” × ×©×œ×—×” ×¢×‌ ×”×،×™×‘×”."
            )
    except Exception as e:
        logger.error("Failed to send rejection message: %s", e)
        if source_message:
            await source_message.reply_text(
                f"×©×’×™×گ×” ×‘×©×œ×™×—×ھ ×”×•×“×¢×ھ ×“×—×™×™×” ×œ×‍×©×ھ×‍×© {target_id}: {e}"
            )

# =========================
# ×گ×™×©×•×¨/×“×—×™×™×” â€“ ×¤×§×•×“×•×ھ ×ک×§×،×ک
# =========================

async def approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """×گ×™×©×•×¨ ×ھ×©×œ×•×‌ ×œ×‍×©×ھ×‍×©: /approve <user_id>"""
    if update.effective_user is None or update.effective_user.id not in ADMIN_IDS:
        await update.effective_message.reply_text(
            "×گ×™×ں ×œ×ڑ ×”×¨×©×گ×” ×œ×‘×¦×¢ ×¤×¢×•×œ×” ×–×•.\n"
            "×گ×‌ ×گ×ھ×” ×—×•×©×‘ ×©×–×• ×ک×¢×•×ھ â€“ ×“×‘×¨ ×¢×‌ ×”×‍×ھ×›× ×ھ: @OsifEU"
        )
        return

    if not context.args:
        await update.effective_message.reply_text("×©×™×‍×•×©: /approve <user_id>")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("user_id ×—×™×™×‘ ×œ×”×™×•×ھ ×‍×،×¤×¨×™.")
        return

    await do_approve(target_id, context, update.effective_message)

async def reject_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """×“×—×™×™×ھ ×ھ×©×œ×•×‌ ×œ×‍×©×ھ×‍×©: /reject <user_id> <×،×™×‘×”>"""
    if update.effective_user is None or update.effective_user.id not in ADMIN_IDS:
        await update.effective_message.reply_text(
            "×گ×™×ں ×œ×ڑ ×”×¨×©×گ×” ×œ×‘×¦×¢ ×¤×¢×•×œ×” ×–×•.\n"
            "×گ×‌ ×گ×ھ×” ×—×•×©×‘ ×©×–×• ×ک×¢×•×ھ â€“ ×“×‘×¨ ×¢×‌ ×”×‍×ھ×›× ×ھ: @OsifEU"
        )
        return

    if len(context.args) < 2:
        await update.effective_message.reply_text("×©×™×‍×•×©: /reject <user_id> <×،×™×‘×”>")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("user_id ×—×™×™×‘ ×œ×”×™×•×ھ ×‍×،×¤×¨×™.")
        return

    reason = " ".join(context.args[1:])
    await do_reject(target_id, reason, context, update.effective_message)

# =========================
# Leaderboard / ×،×ک×ک×™×،×ک×™×§×•×ھ / Rewards â€“ ×¤×§×•×“×•×ھ ×گ×“×‍×™×ں
# =========================

async def admin_leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """×œ×•×— ×‍×¤× ×™×‌ â€“ /leaderboard"""
    if update.effective_user is None or update.effective_user.id not in ADMIN_IDS:
        await update.effective_message.reply_text(
            "×گ×™×ں ×œ×ڑ ×”×¨×©×گ×” ×œ×¦×¤×•×ھ ×‘×œ×•×— ×”×‍×¤× ×™×‌.\n"
            "×گ×‌ ×گ×ھ×” ×—×•×©×‘ ×©×–×• ×ک×¢×•×ھ â€“ ×“×‘×¨ ×¢×‌ ×”×‍×ھ×›× ×ھ: @OsifEU"
        )
        return

    if not DB_AVAILABLE:
        await update.effective_message.reply_text("DB ×œ×گ ×¤×¢×™×œ ×›×¨×’×¢.")
        return

    try:
        rows: List[Dict[str, Any]] = get_top_referrers(10)
    except Exception as e:
        logger.error("Failed to get top referrers: %s", e)
        await update.effective_message.reply_text("×©×’×™×گ×” ×‘×§×¨×™×گ×ھ × ×ھ×•× ×™ ×”×¤× ×™×•×ھ.")
        return

    if not rows:
        await update.effective_message.reply_text("×گ×™×ں ×¢×“×™×™×ں × ×ھ×•× ×™ ×”×¤× ×™×•×ھ.")
        return

    lines = ["ًںڈ† *×œ×•×— ×‍×¤× ×™×‌ â€“ Top 10* \n"]
    rank = 1
    for row in rows:
        rid = row["referrer_id"]
        uname = row["username"] or f"ID {rid}"
        total = row["total_referrals"]
        points = row["total_points"]
        lines.append(f"{rank}. {uname} â€“ {total} ×”×¤× ×™×•×ھ ({points} × ×§×³)")
        rank += 1

    await update.effective_message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
    )

async def admin_payments_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """×“×•×— ×ھ×©×œ×•×‍×™×‌ â€“ /payments_stats"""
    if update.effective_user is None or update.effective_user.id not in ADMIN_IDS:
        await update.effective_message.reply_text(
            "×گ×™×ں ×œ×ڑ ×”×¨×©×گ×” ×œ×¦×¤×•×ھ ×‘×،×ک×ک×™×،×ک×™×§×•×ھ.\n"
            "×گ×‌ ×گ×ھ×” ×¦×¨×™×ڑ ×’×™×©×” â€“ ×“×‘×¨ ×¢×‌ ×”×‍×ھ×›× ×ھ: @OsifEU"
        )
        return

    if not DB_AVAILABLE:
        await update.effective_message.reply_text("DB ×œ×گ ×¤×¢×™×œ ×›×¨×’×¢.")
        return

    now = datetime.utcnow()
    year = now.year
    month = now.month

    try:
        rows = get_monthly_payments(year, month)
        stats = get_approval_stats()
    except Exception as e:
        logger.error("Failed to get payment stats: %s", e)
        await update.effective_message.reply_text("×©×’×™×گ×” ×‘×§×¨×™×گ×ھ × ×ھ×•× ×™ ×ھ×©×œ×•×‌.")
        return

    lines = [f"ًں“ٹ *×“×•×— ×ھ×©×œ×•×‍×™×‌ â€“ {month:02d}/{year}* \n"]

    if rows:
        lines.append("*×œ×¤×™ ×گ×‍×¦×¢×™ ×ھ×©×œ×•×‌ ×•×،×ک×ک×•×،:*")
        for row in rows:
            lines.append(f"- {row['pay_method']} / {row['status']}: {row['count']}")
    else:
        lines.append("×گ×™×ں ×ھ×©×œ×•×‍×™×‌ ×‘×—×•×“×© ×–×”.")

    if stats and stats.get("total", 0) > 0:
        total = stats["total"]
        approved = stats["approved"]
        rejected = stats["rejected"]
        pending = stats["pending"]
        approval_rate = round(approved * 100 / total, 1) if total else 0.0
        lines.append("\n*×،×ک×ک×•×، ×›×œ×œ×™:*")
        lines.append(f"- ×گ×•×©×¨×•: {approved}")
        lines.append(f"- × ×“×—×•: {rejected}")
        lines.append(f"- ×‍×‍×ھ×™× ×™×‌: {pending}")
        lines.append(f"- ×گ×—×•×– ×گ×™×©×•×¨: {approval_rate}%")
    else:
        lines.append("\n×گ×™×ں ×¢×“×™×™×ں × ×ھ×•× ×™×‌ ×›×œ×œ×™×™×‌.")

    await update.effective_message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
    )

async def admin_reward_slh_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    ×™×¦×™×¨×ھ Reward ×™×“× ×™ ×œ×‍×©×ھ×‍×© â€“ ×œ×“×•×’×‍×”:
    /reward_slh <user_id> <points> <reason...>
    """
    if update.effective_user is None or update.effective_user.id not in ADMIN_IDS:
        await update.effective_message.reply_text(
            "×گ×™×ں ×œ×ڑ ×”×¨×©×گ×” ×œ×™×¦×•×¨ Rewards.\n"
            "×گ×‌ ×گ×ھ×” ×¦×¨×™×ڑ ×’×™×©×” â€“ ×“×‘×¨ ×¢×‌ ×”×‍×ھ×›× ×ھ: @OsifEU"
        )
        return

    if not DB_AVAILABLE:
        await update.effective_message.reply_text("DB ×œ×گ ×¤×¢×™×œ ×›×¨×’×¢.")
        return

    if len(context.args) < 3:
        await update.effective_message.reply_text(
            "×©×™×‍×•×©: /reward_slh <user_id> <points> <reason...>"
        )
        return

    try:
        target_id = int(context.args[0])
        points = int(context.args[1])
    except ValueError:
        await update.effective_message.reply_text("user_id ×•-points ×—×™×™×‘×™×‌ ×œ×”×™×•×ھ ×‍×،×¤×¨×™×™×‌.")
        return

    reason = " ".join(context.args[2:])

    try:
        create_reward(target_id, "SLH", reason, points)
    except Exception as e:
        logger.error("Failed to create reward: %s", e)
        await update.effective_message.reply_text("×©×’×™×گ×” ×‘×™×¦×™×¨×ھ Reward.")
        return

    # ×”×•×“×¢×” ×œ×‍×©×ھ×‍×© (×¢×“×™×™×ں ×œ×œ×گ mint ×گ×‍×™×ھ×™ â€“ ×œ×•×’×™)
    try:
        await update.effective_message.reply_text(
            f"× ×•×¦×¨ Reward SLH ×œ×‍×©×ھ×‍×© {target_id} ({points} × ×§×³): {reason}"
        )

        await ptb_app.bot.send_message(
            chat_id=target_id,
            text=(
                "ًںژپ ×§×™×‘×œ×ھ Reward ×¢×œ ×”×¤×¢×™×œ×•×ھ ×©×œ×ڑ ×‘×§×”×™×œ×”!\n\n"
                f"×،×•×’: *SLH* ({points} × ×§×³)\n"
                f"×،×™×‘×”: {reason}\n\n"
                "Reward ×–×” ×™×گ×،×£ ×œ×‍×گ×–×ں ×©×œ×ڑ ×•×™×گ×¤×©×¨ ×”× ×¤×§×ھ ×‍×ک×‘×¢×•×ھ/× ×›×،×™×‌ "
                "×“×™×’×™×ک×œ×™×™×‌ ×œ×¤×™ ×”×‍×“×™× ×™×•×ھ ×©×ھ×¤×•×¨×،×‌ ×‘×§×”×™×œ×”."
            ),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error("Failed to notify user about reward: %s", e)

# =========================
# ×گ×™×©×•×¨/×“×—×™×™×” â€“ ×›×¤×ھ×•×¨×™ ×گ×“×‍×™×ں
# =========================

async def admin_approve_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """×›×¤×ھ×•×¨ '×گ×©×¨ ×ھ×©×œ×•×‌' ×‘×œ×•×’×™×‌"""
    query = update.callback_query
    await query.answer()
    admin = query.from_user

    if admin.id not in ADMIN_IDS:
        await query.answer(
            "×گ×™×ں ×œ×ڑ ×”×¨×©×گ×”.\n×گ×‌ ×گ×ھ×” ×—×•×©×‘ ×©×–×• ×ک×¢×•×ھ â€“ ×“×‘×¨ ×¢×‌ @OsifEU",
            show_alert=True,
        )
        return

    data = query.data or ""
    try:
        _, user_id_str = data.split(":", 1)
        target_id = int(user_id_str)
    except Exception:
        await query.answer("×©×’×™×گ×” ×‘× ×ھ×•× ×™ ×”×‍×©×ھ×‍×©.", show_alert=True)
        return

    await do_approve(target_id, context, query.message)

async def admin_reject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """×›×¤×ھ×•×¨ '×“×—×” ×ھ×©×œ×•×‌' â€“ ×‍×‘×§×© ×‍×”×گ×“×‍×™×ں ×،×™×‘×” ×‘×”×•×“×¢×” ×”×‘×گ×” ×©×œ×•"""
    query = update.callback_query
    await query.answer()
    admin = query.from_user

    if admin.id not in ADMIN_IDS:
        await query.answer(
            "×گ×™×ں ×œ×ڑ ×”×¨×©×گ×”.\n×گ×‌ ×گ×ھ×” ×—×•×©×‘ ×©×–×• ×ک×¢×•×ھ â€“ ×“×‘×¨ ×¢×‌ @OsifEU",
            show_alert=True,
        )
        return

    data = query.data or ""
    try:
        _, user_id_str = data.split(":", 1)
        target_id = int(user_id_str)
    except Exception:
        await query.answer("×©×’×™×گ×” ×‘× ×ھ×•× ×™ ×”×‍×©×ھ×‍×©.", show_alert=True)
        return

    pending = get_pending_rejects(context)
    pending[admin.id] = target_id

    await query.message.reply_text(
        f"â‌Œ ×‘×—×¨×ھ ×œ×“×—×•×ھ ×گ×ھ ×”×ھ×©×œ×•×‌ ×©×œ ×”×‍×©×ھ×‍×© {target_id}.\n"
        "×©×œ×— ×¢×›×©×™×• ×گ×ھ ×،×™×‘×ھ ×”×“×—×™×™×” ×‘×”×•×“×¢×” ×گ×—×ھ (×ک×§×،×ک), ×•×”×™×گ ×ھ×™×©×œ×— ×گ×œ×™×• ×™×—×“ ×¢×‌ ×¦×™×œ×•×‌ ×”×ھ×©×œ×•×‌."
    )

async def admin_reject_reason_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    ×”×•×“×¢×ھ ×ک×§×،×ک ×‍×گ×“×‍×™×ں ×گ×—×¨×™ ×©×œ×—×¥ '×“×—×” ×ھ×©×œ×•×‌':
    ×‍×©×ھ×‍×©×™×‌ ×‘×–×” ×›×،×™×‘×” ×œ×“×—×™×™×”.
    """
    user = update.effective_user
    if user is None or user.id not in ADMIN_IDS:
        return

    pending = get_pending_rejects(context)
    if user.id not in pending:
        return  # ×گ×™×ں ×“×—×™×™×” ×‍×‍×ھ×™× ×” ×¢×‘×•×¨ ×”×گ×“×‍×™×ں ×”×–×”

    target_id = pending.pop(user.id)
    reason = update.message.text.strip()
    await do_reject(target_id, reason, context, update.effective_message)

# =========================
# ×¢×–×¨×” + ×ھ×¤×¨×™×ک ×گ×“×‍×™×ں
# =========================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """×¢×–×¨×” ×‘×،×™×،×™×ھ"""
    message = update.message or update.effective_message
    if not message:
        return

    text = (
        "/start â€“ ×”×ھ×—×œ×” ×‍×—×“×© ×•×ھ×¤×¨×™×ک ×¨×گ×©×™\n"
        "/help â€“ ×¢×–×¨×”\n\n"
        "×گ×—×¨×™ ×‘×™×¦×•×¢ ×ھ×©×œ×•×‌ â€“ ×©×œ×— ×¦×™×œ×•×‌ ×‍×،×ڑ ×©×œ ×”×گ×™×©×•×¨ ×œ×‘×•×ک.\n\n"
        "×œ×©×™×ھ×•×£ ×©×¢×¨ ×”×§×”×™×œ×”: ×›×¤×ھ×•×¨ 'ًں”— ×©×ھ×£ ×گ×ھ ×©×¢×¨ ×”×§×”×™×œ×”' ×‘×ھ×¤×¨×™×ک ×”×¨×گ×©×™.\n\n"
        "×œ×‍×گ×¨×’× ×™×‌ / ×گ×“×‍×™× ×™×‌:\n"
        "/admin â€“ ×ھ×¤×¨×™×ک ×گ×“×‍×™×ں\n"
        "/leaderboard â€“ ×œ×•×— ×‍×¤× ×™×‌ (Top 10)\n"
        "/payments_stats â€“ ×،×ک×ک×™×،×ک×™×§×•×ھ ×ھ×©×œ×•×‍×™×‌\n"
        "/reward_slh <user_id> <points> <reason> â€“ ×™×¦×™×¨×ھ Reward ×œ-SLH\n"
        "/approve <user_id> â€“ ×گ×™×©×•×¨ ×ھ×©×œ×•×‌\n"
        "/reject <user_id> <×،×™×‘×”> â€“ ×“×—×™×™×ھ ×ھ×©×œ×•×‌\n"
        "×گ×• ×©×™×‍×•×© ×‘×›×¤×ھ×•×¨×™ ×”×گ×™×©×•×¨/×“×—×™×™×” ×œ×™×“ ×›×œ ×ھ×©×œ×•×‌ ×‘×œ×•×’×™×‌."
    )

    await message.reply_text(text)

async def admin_menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """×¤×§×•×“×ھ /admin â€“ ×ھ×¤×¨×™×ک ×گ×“×‍×™×ں"""
    if update.effective_user is None or update.effective_user.id not in ADMIN_IDS:
        await update.effective_message.reply_text(
            "×گ×™×ں ×œ×ڑ ×”×¨×©×گ×” ×œ×ھ×¤×¨×™×ک ×گ×“×‍×™×ں.\n"
            "×گ×‌ ×گ×ھ×” ×¦×¨×™×ڑ ×’×™×©×” â€“ ×“×‘×¨ ×¢×‌ ×”×‍×ھ×›× ×ھ: @OsifEU"
        )
        return

    text = (
        "ًں›  *×ھ×¤×¨×™×ک ×گ×“×‍×™×ں â€“ Buy My Shop*\n\n"
        "×‘×—×¨ ×گ×—×ھ ×‍×”×گ×¤×©×¨×•×™×•×ھ:\n"
        "â€¢ ×،×ک×ک×•×، ×‍×¢×¨×›×ھ (DB, Webhook, ×œ×™× ×§×™×‌)\n"
        "â€¢ ×‍×•× ×™ ×ھ×‍×•× ×ھ ×©×¢×¨ (×›×‍×” ×¤×¢×‍×™×‌ ×”×•×¦×’×”/× ×©×œ×—×”)\n"
        "â€¢ ×¨×¢×™×•× ×•×ھ ×œ×¤×™×¦'×¨×™×‌ ×¢×ھ×™×“×™×™×‌ ×œ×‘×•×ک\n\n"
        "×¤×§×•×“×•×ھ × ×•×،×¤×•×ھ:\n"
        "/leaderboard â€“ ×œ×•×— ×‍×¤× ×™×‌\n"
        "/payments_stats â€“ ×“×•×— ×ھ×©×œ×•×‍×™×‌\n"
        "/reward_slh â€“ ×™×¦×™×¨×ھ Reward SLH\n"
    )

    await update.effective_message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=admin_menu_keyboard(),
    )

async def admin_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """×ک×™×¤×•×œ ×‘×›×¤×ھ×•×¨×™ ×ھ×¤×¨×™×ک ×”×گ×“×‍×™×ں"""
    query = update.callback_query
    await query.answer()
    admin = query.from_user

    if admin.id not in ADMIN_IDS:
        await query.answer(
            "×گ×™×ں ×œ×ڑ ×”×¨×©×گ×”.\n×گ×‌ ×گ×ھ×” ×—×•×©×‘ ×©×–×• ×ک×¢×•×ھ â€“ ×“×‘×¨ ×¢×‌ @OsifEU",
            show_alert=True,
        )
        return

    data = query.data

    app_data = context.application.bot_data
    views = app_data.get("start_image_views", 0)
    downloads = app_data.get("start_image_downloads", 0)

    if data == "adm_status":
        text = (
            "ًں“ٹ *×،×ک×ک×•×، ×‍×¢×¨×›×ھ*\n\n"
            f"â€¢ DB: {'×¤×¢×™×œ' if DB_AVAILABLE else '×›×‘×•×™'}\n"
            f"â€¢ Webhook URL: `{WEBHOOK_URL}`\n"
            f"â€¢ LANDING_URL: `{LANDING_URL}`\n"
            f"â€¢ PAYBOX_URL: `{PAYBOX_URL}`\n"
            f"â€¢ BIT_URL: `{BIT_URL}`\n"
            f"â€¢ PAYPAL_URL: `{PAYPAL_URL}`\n"
        )
        await query.message.edit_text(
            text,
            parse_mode="Markdown",
            reply_markup=admin_menu_keyboard(),
        )

    elif data == "adm_counters":
        text = (
            "ًں“ˆ *×‍×•× ×™ ×ھ×‍×•× ×ھ ×©×¢×¨*\n\n"
            f"â€¢ ×‍×،×¤×¨ ×”×¦×’×•×ھ (start): {views}\n"
            f"â€¢ ×¢×•×ھ×§×™×‌ ×‍×‍×•×،×¤×¨×™×‌ ×©× ×©×œ×—×• ×گ×—×¨×™ ×گ×™×©×•×¨: {downloads}\n\n"
            "×”×‍×•× ×™×‌ ×‍×گ×•×¤×،×™×‌ ×‘×›×œ ×”×¤×¢×œ×” ×‍×—×“×© ×©×œ ×”×‘×•×ک (in-memory)."
        )
        await query.message.edit_text(
            text,
            parse_mode="Markdown",
            reply_markup=admin_menu_keyboard(),
        )

    elif data == "adm_ideas":
        text = (
            "ًں’، *×¨×¢×™×•× ×•×ھ ×œ×¤×™×¦'×¨×™×‌ ×¢×ھ×™×“×™×™×‌ ×œ×‘×•×ک*\n\n"
            "1. ×‍×¢×¨×›×ھ × ×™×§×•×“ ×‍×œ×گ×” ×œ×‍×¤× ×™×‌ (Leaderboard ×‘×§×‘×•×¦×”).\n"
            "2. ×“×•×—×•×ھ ×‍×ھ×§×“×‍×™×‌ ×™×•×ھ×¨ ×‘-DB:\n"
            "   â€¢ ×¤×™×œ×•×— ×œ×¤×™ ×–×‍× ×™×‌\n"
            "   â€¢ ×¤×™×œ×•×— ×œ×¤×™ ×‍×§×•×¨ ×”×¤× ×™×”.\n"
            "3. ×”× ×¤×§×ھ × ×›×،×™×‌ ×“×™×’×™×ک×œ×™×™×‌ (NFT / SLH) ×گ×•×ک×•×‍×ک×™×ھ ×œ×‍×©×ھ×ھ×¤×™×‌:\n"
            "   â€¢ ×œ×¤×™ ×‍×،×¤×¨ ×”×¤× ×™×•×ھ\n"
            "   â€¢ ×œ×¤×™ ×¨×‍×ھ ×¤×¢×™×œ×•×ھ ×‘×§×”×™×œ×”.\n"
            "4. ×“×©×‘×•×¨×“ ×•×•×‘×™ ×§×ک×ں (Read-only) ×œ×”×¦×’×ھ ×”×،×ک×ک×™×،×ک×™×§×•×ھ.\n"
            "5. ×گ×™× ×ک×’×¨×¦×™×” ×¢×‌ ×‘×•×ک×™ ×ھ×•×›×ں / ×§×•×•×،×ک×™×‌ ×©×‍×–×™× ×™×‌ ×گ×ھ ×گ×•×ھ×” ×‍×¢×¨×›×ھ × ×§×•×“×•×ھ.\n"
        )
        await query.message.edit_text(
            text,
            parse_mode="Markdown",
            reply_markup=admin_menu_keyboard(),
        )

# =========================
# ×¨×™×©×•×‌ handlers
# =========================

ptb_app.add_handler(CommandHandler("start", start))
ptb_app.add_handler(CommandHandler("help", help_command))
ptb_app.add_handler(CommandHandler("admin", admin_menu_command))
ptb_app.add_handler(CommandHandler("approve", approve_command))
ptb_app.add_handler(CommandHandler("reject", reject_command))
ptb_app.add_handler(CommandHandler("leaderboard", admin_leaderboard_command))
ptb_app.add_handler(CommandHandler("payments_stats", admin_payments_stats_command))
ptb_app.add_handler(CommandHandler("reward_slh", admin_reward_slh_command))

ptb_app.add_handler(CallbackQueryHandler(info_callback, pattern="^info$"))
ptb_app.add_handler(CallbackQueryHandler(join_callback, pattern="^join$"))
ptb_app.add_handler(CallbackQueryHandler(support_callback, pattern="^support$"))
ptb_app.add_handler(CallbackQueryHandler(share_callback, pattern="^share$"))
ptb_app.add_handler(CallbackQueryHandler(back_main_callback, pattern="^back_main$"))
ptb_app.add_handler(CallbackQueryHandler(payment_method_callback, pattern="^pay_"))
ptb_app.add_handler(CallbackQueryHandler(admin_menu_callback, pattern="^adm_(status|counters|ideas)$"))
ptb_app.add_handler(CallbackQueryHandler(admin_approve_callback, pattern="^adm_approve:"))
ptb_app.add_handler(CallbackQueryHandler(admin_reject_callback, pattern="^adm_reject:"))

# ×›×œ ×ھ×‍×•× ×” ×‘×¤×¨×ک×™ â€“ × × ×™×— ×›×گ×™×©×•×¨ ×ھ×©×œ×•×‌
ptb_app.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, handle_payment_photo))

# ×”×•×“×¢×ھ ×ک×§×،×ک ×‍×گ×“×‍×™×ں â€“ ×گ×‌ ×™×© ×“×—×™×™×” ×‍×‍×ھ×™× ×”
ptb_app.add_handler(MessageHandler(filters.TEXT & filters.User(list(ADMIN_IDS)), admin_reject_reason_handler))

# =========================
# JobQueue â€“ ×ھ×–×›×•×¨×ھ ×›×œ 6 ×™×‍×™×‌ ×œ×¢×“×›×•×ں ×œ×™× ×§×™×‌
# =========================

async def remind_update_links(context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_start_image(context, PAYMENTS_LOG_CHAT_ID, mode="reminder")

# =========================
# FastAPI + lifespan
# =========================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    ×‘×–×‍×ں ×¢×œ×™×™×ھ ×”×©×¨×ھ:
    1. ×‍×’×“×™×¨×™×‌ webhook ×‘-Telegram ×œ-WEBHOOK_URL
    2. ×‍×¤×¢×™×œ×™×‌ ×گ×ھ ×گ×¤×œ×™×§×¦×™×™×ھ ×”-Telegram
    3. ×‍×¤×¢×™×œ×™×‌ JobQueue ×œ×ھ×–×›×•×¨×ھ ×›×œ 6 ×™×‍×™×‌
    4. ×گ×‌ ×™×© DB â€“ ×‍×¨×™×‍×™×‌ schema
    """
    logger.info("Setting Telegram webhook to %s", WEBHOOK_URL)
    try:
        await ptb_app.bot.setWebhook(url=WEBHOOK_URL, allowed_updates=Update.ALL_TYPES)
    except RetryAfter as e:
        logger.warning(
            "Telegram flood control on setWebhook, retry_after=%s  continuing startup",
            getattr(e, "retry_after", None),
        )

    # init DB schema ×گ×‌ ×–×‍×™×ں
    if DB_AVAILABLE:
        try:
            init_schema()
            logger.info("DB schema initialized.")
        except Exception as e:
            logger.error("Failed to init DB schema: %s", e)

    async with ptb_app:
        logger.info("Starting Telegram Application")
        await ptb_app.start()

        # ×ھ×–×›×•×¨×ھ ×›×œ 6 ×™×‍×™×‌
        if ptb_app.job_queue:
            ptb_app.job_queue.run_repeating(
                remind_update_links,
                interval=6 * 24 * 60 * 60,  # 6 ×™×‍×™×‌ ×‘×©× ×™×•×ھ
                first=6 * 24 * 60 * 60,
            )

        yield
        logger.info("Stopping Telegram Application")
        await ptb_app.stop()

app = FastAPI(lifespan=lifespan)

# =========================
# Routes â€“ Webhook + Health + Admin Stats API
# =========================

@app.post("/webhook")
async def telegram_webhook(request: Request) -> Response:
    """× ×§×•×“×ھ ×”-webhook ×©×ک×œ×’×¨×‌ ×§×•×¨×گ ×گ×œ×™×”"""
    data = await request.json()
    update = Update.de_json(data, ptb_app.bot)

    if is_duplicate_update(update):
        logger.warning("Duplicate update_id=%s â€“ ignoring", update.update_id)
        return Response(status_code=HTTPStatus.OK.value)

    await ptb_app.process_update(update)
    return Response(status_code=HTTPStatus.OK.value)


@app.get("/health")
async def health():
    """Healthcheck ×œ-Railway / × ×™×ک×•×¨"""
    return {
        "status": "ok",
        "service": "telegram-gateway-community-bot",
        "db": "enabled" if DB_AVAILABLE else "disabled",
    }


@app.get("/admin/stats")
async def admin_stats(token: str = ""):
    """
    ×“×©×‘×•×¨×“ API ×§×ک×ں ×œ×§×¨×™×گ×” ×‘×œ×‘×“.
    ×œ×”×©×ھ×‍×© ×‘-ADMIN_DASH_TOKEN ×‘-ENV.
    """
    if not ADMIN_DASH_TOKEN or token != ADMIN_DASH_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if not DB_AVAILABLE:
        return {"db": "disabled"}

    try:
        stats = get_approval_stats()
        monthly = get_monthly_payments(datetime.utcnow().year, datetime.utcnow().month)
        top_ref = get_top_referrers(5)
    except Exception as e:
        logger.error("Failed to get admin stats: %s", e)
        raise HTTPException(status_code=500, detail="DB error")

    return {
        "db": "enabled",
        "payments_stats": stats,
        "monthly_breakdown": monthly,
        "top_referrers": top_ref,
    }

