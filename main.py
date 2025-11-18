from __future__ import annotations

import logging
import os
from datetime import datetime
from http import HTTPStatus
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    AIORateLimiter,
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# =========================
# לוגינג בסיסי
# =========================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("botshop")

# =========================
# טעינת מודול DB (db.py) עם סטאבים
# =========================

DB_AVAILABLE = False

try:
    from db import (  # type: ignore
        init_schema,
        log_payment,
        update_payment_status,
        store_user,
        add_referral,
        get_top_referrers,
        get_monthly_payments,
        get_approval_stats,
        ensure_promoter,
        incr_metric,
        get_metric,
        get_pending_payments_count,
        get_user_language,
    )

    DB_AVAILABLE = True
    logger.info("DB module loaded successfully (DB_AVAILABLE=True)")
except Exception as e:
    logger.warning("DB not available, falling back to stubs: %s", e)

    def init_schema() -> None:
        logger.info("init_schema() stub – no DB configured")

    def log_payment(user_id: int, username: str, pay_method: str) -> None:
        logger.info(
            "Payment logged (stub) – user_id=%s, username=%s, method=%s",
            user_id,
            username,
            pay_method,
        )

    def update_payment_status(
        user_id: int, status: str, reason: Optional[str] = None
    ) -> None:
        logger.info(
            "Payment status updated (stub) – user_id=%s, status=%s, reason=%s",
            user_id,
            status,
            reason,
        )

    def store_user(user_id: int, username: Optional[str]) -> None:
        logger.info("store_user(stub) – user_id=%s, username=%s", user_id, username)

    def add_referral(referrer_id: int, referred_user_id: int, source: str) -> None:
        logger.info(
            "add_referral(stub) – %s -> %s source=%s",
            referrer_id,
            referred_user_id,
            source,
        )

    def get_top_referrers(limit: int = 5) -> List[Dict[str, Any]]:
        return []

    def get_monthly_payments(year: int, month: int) -> List[Dict[str, Any]]:
        return []

    def get_approval_stats() -> Dict[str, Any]:
        return {"total": 0, "approved": 0, "pending": 0, "rejected": 0}

    def ensure_promoter(user_id: int) -> None:
        logger.info("ensure_promoter(stub) – user_id=%s", user_id)

    def incr_metric(key: str, delta: int = 1) -> None:
        logger.info("incr_metric(stub) – key=%s, delta=%s", key, delta)

    def get_metric(key: str) -> int:
        return 0

    def get_pending_payments_count(user_id: int) -> int:
        return 0

    def get_user_language(user_id: int) -> str:
        return "he"


# =========================
# ENV & קבועים
# =========================

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "").strip()
ADMIN_DASH_TOKEN = os.environ.get("ADMIN_DASH_TOKEN", "").strip()

_admin_ids_raw = os.environ.get("ADMIN_OWNER_IDS", "224223270")
try:
    ADMIN_OWNER_IDS = {
        int(x.strip())
        for x in _admin_ids_raw.split(",")
        if x.strip().isdigit()
    }
except Exception:
    ADMIN_OWNER_IDS = set()

COMMUNITY_GROUP_LINK = os.environ.get(
    "COMMUNITY_GROUP_LINK", "https://t.me/+HIzvM8sEgh1kNWY0"
)
SUPPORT_GROUP_LINK = os.environ.get(
    "SUPPORT_GROUP_LINK", "https://t.me/+1ANn25HeVBoxNmRk"
)

try:
    PAYMENTS_LOG_CHAT_ID = int(os.environ.get("PAYMENTS_LOG_CHAT_ID", "-1001748319682"))
except Exception:
    PAYMENTS_LOG_CHAT_ID = -1001748319682

TON_WALLET = os.environ.get(
    "TON_WALLET", "UQCr743gEr_nqV_0SBkSp3CtYS_15R3LDUMMYXXXX"
)
TON_DISCOUNT_PERCENT = 10

PAYBOX_URL = os.environ.get(
    "PAYBOX_URL", "https://links.payboxapp.com/1SNfaJ6XcYb"
)
BIT_URL = os.environ.get("BIT_URL", "https://paymesomething.bit/")
PAYPAL_URL = os.environ.get("PAYPAL_URL", "https://paypal.me/yourlink")

# =========================
# תרגום בסיסי
# =========================


class TranslationManager:
    def get_user_language(self, user_id: int) -> str:
        try:
            return get_user_language(user_id)
        except Exception:
            return "he"

    def get_text(self, key: str, lang: str = "he") -> str:
        he = {
            "join_community": "הצטרפות לקהילה ב-39 ₪",
            "bank_payment": "🔗 פרטי תשלום / בנק",
            "ton_payment": "תשלום ב-TON (טלגרם)",
            "back": "⬅ חזרה",
            "support": "צור קשר עם תמיכה",
            "welcome_title": "ברוך הבא לשער הקהילה של SLH",
            "new_user_start": "📥 התחלה חדשה בבוט (START) נרשמה במערכת",
        }
        en = {
            "join_community": "Join the community (39₪)",
            "bank_payment": "Payment details / bank",
            "ton_payment": "Pay with TON",
            "back": "Back",
            "support": "Contact support",
            "welcome_title": "Welcome to the SLH Community Gateway",
            "new_user_start": "New /start registered",
        }
        table = he if lang == "he" else en
        return table.get(key, he.get(key, key))


trans_manager = TranslationManager()

# =========================
# סטטיסטיקות /start
# =========================


def get_start_stats() -> Dict[str, int]:
    """
    סטטיסטיקות /start על בסיס metrics (אם יש DB).
    """
    if not DB_AVAILABLE:
        return {"total": 0, "direct": 0, "with_ref": 0}

    try:
        return {
            "total": get_metric("total_starts"),
            "direct": get_metric("starts_direct"),
            "with_ref": get_metric("starts_with_ref"),
        }
    except Exception as e:
        logger.error("Failed to read start metrics from DB: %s", e)
        return {"total": 0, "direct": 0, "with_ref": 0}


def build_personal_share_link(user_id: int, bot_username: Optional[str]) -> str:
    if not bot_username:
        bot_username = "Buy_My_Shop_bot"
    return f"https://t.me/{bot_username}?start=ref_{user_id}"


# =========================
# Telegram Bot (python-telegram-bot v20+)
# =========================

ptb_app: Optional[Application] = None


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /start – רישום משתמש, referral, סטטיסטיקות, ולוג לקבוצת תשלומים.
    """
    try:
        message = update.message or update.effective_message
        if not message:
            return

        user = update.effective_user
        chat = update.effective_chat
        if not user or not chat:
            return

        lang = trans_manager.get_user_language(user.id)
        username_str = f"@{user.username}" if user.username else "(ללא username)"

        is_new_user = False
        has_stuck_payment = False

        # רישום משתמש ומדדים
        if DB_AVAILABLE:
            try:
                store_user(user.id, user.username)
                incr_metric("total_starts")
                is_new_user = True

                pending_count = get_pending_payments_count(user.id)
                if pending_count > 0:
                    has_stuck_payment = True
            except Exception as e:
                logger.error("Failed DB operations in /start: %s", e)
        else:
            incr_metric("total_starts")

        # Referral + פילוח קמפיינים
        has_ref = False
        if message.text and message.text.startswith("/start"):
            parts = message.text.split()
            if len(parts) > 1 and parts[1].startswith("ref_"):
                has_ref = True
                try:
                    referrer_id = int(parts[1].split("ref_")[1])
                    if DB_AVAILABLE and referrer_id != user.id:
                        add_referral(referrer_id, user.id, source="bot_start")
                        logger.info("Referral added: %s -> %s", referrer_id, user.id)
                except Exception as e:
                    logger.error("Failed to add referral: %s", e)

        try:
            if has_ref:
                incr_metric("starts_with_ref")
            else:
                incr_metric("starts_direct")
        except Exception as e:
            logger.error("Failed to update start metrics: %s", e)

        # לוג לקבוצת התשלומים – כל /start
        if PAYMENTS_LOG_CHAT_ID and update.effective_user:
            try:
                status_note = (
                    "🆕 משתמש חדש"
                    if is_new_user
                    else "⚠️ תהליך תקוע"
                    if has_stuck_payment
                    else "🔁 משתמש חוזר / לחיצה נוספת"
                )
                src = "עם ref" if has_ref else "ללא ref"

                log_text = (
                    f"{trans_manager.get_text('new_user_start', 'he')}\n\n"
                    f"👤 user_id: `{user.id}`\n"
                    f"📛 username: {username_str}\n"
                    f"💬 chat_id: `{chat.id}`\n"
                    f"📊 סטטוס: {status_note}\n"
                    f"📈 מקור: {src}\n"
                    f"🕐 זמן: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                )

                await context.bot.send_message(
                    chat_id=PAYMENTS_LOG_CHAT_ID,
                    text=log_text,
                    parse_mode=ParseMode.MARKDOWN,
                )
            except Exception as e:
                logger.error("Failed to send /start log to payments group: %s", e)

        # הודעת ברוכים הבאים
        title = trans_manager.get_text("welcome_title", lang)
        text = (
            f"👋 *{title}*\n\n"
            "כאן אתה נכנס לשער הכלכלי-חברתי של SLH – קהילה, בוטים, הכנסה שיתופית ועוד.\n\n"
            "💰 עלות הצטרפות: *39 ₪* (חד-פעמי)\n"
            "לאחר התשלום תקבל:\n"
            "• כניסה לקבוצת העסקים והקהילה\n"
            "• שער דיגיטלי אישי (קובץ/תמונה ממוספרת)\n"
            "• לינק אישי לשיתוף וקבלת תגמולים\n\n"
            "להמשך – בחר פעולה מתאימה בתפריט:"
        )

        await message.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_keyboard(lang),
        )

    except Exception as e:
        logger.error("Error in /start: %s", e)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    txt = (
        "פקודות זמינות:\n"
        "/start – התחלה מחדש\n"
        "/bankinfo – פרטי תשלום והסבר\n"
        "/whoami – מידע עליך\n"
    )
    await (update.message or update.effective_message).reply_text(txt)


async def cmd_bankinfo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = trans_manager.get_user_language(update.effective_user.id)
    txt = (
        "💳 *פרטי תשלום להצטרפות ב-39 ₪*\n\n"
        "1. בצע תשלום (ביט / פייבוקס / העברה בנקאית / PayPal).\n"
        "2. שלח לבוט צילום מסך של אישור התשלום.\n"
        "3. האדמינים יאשרו את התשלום ותקבל שער דיגיטלי וקישור לקהילה.\n\n"
        f"🔗 תשלום בפייבוקס: {PAYBOX_URL}\n"
        f"🔗 תשלום בביט: {BIT_URL}\n"
        f"🔗 PayPal: {PAYPAL_URL}\n\n"
        "לאחר ששלחת אישור – תקבל עדכון כאן בבוט."
    )
    await (update.message or update.effective_message).reply_text(
        txt,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=payment_links_keyboard(lang),
    )


async def cmd_whoami(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat
    txt = (
        f"user_id: `{user.id}`\n"
        f"username: @{user.username}\n"
        f"chat_id: `{chat.id}`\n"
    )
    await (update.message or update.effective_message).reply_text(
        txt, parse_mode=ParseMode.MARKDOWN
    )


async def handle_payment_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    צילום מסך של אישור תשלום – נשלח לקבוצת לוגים ונשמר ב-DB.
    """
    try:
        message = update.message
        if not message or not message.photo:
            return

        user = update.effective_user
        chat = update.effective_chat
        if not user or not chat:
            return

        username_str = f"@{user.username}" if user.username else "(ללא username)"

        pay_method = context.user_data.get("last_pay_method", "unknown")
        pay_method_text = {
            "bank": "העברה בנקאית",
            "paybox": "ביט / פייבוקס / PayPal",
            "ton": f"טלגרם (TON) - {TON_DISCOUNT_PERCENT}% הנחה",
            "unknown": "לא ידוע",
        }.get(pay_method, "לא ידוע")

        if DB_AVAILABLE:
            try:
                log_payment(user.id, user.username or "", pay_method)
                incr_metric("payment_proofs")
            except Exception as e:
                logger.error("Failed to log payment in DB: %s", e)

        caption = (
            "📥 התקבל אישור תשלום חדש.\n\n"
            f"user_id = `{user.id}`\n"
            f"username = {username_str}\n"
            f"from chat_id = `{chat.id}`\n"
            f"💳 שיטת תשלום: {pay_method_text}\n\n"
            "לאישור (עבור אדמין ראשי):\n"
            f"/approve {user.id}\n"
            f"/reject {user.id} <סיבה>\n"
        )

        photo = message.photo[-1]

        if PAYMENTS_LOG_CHAT_ID:
            try:
                await context.bot.send_photo(
                    chat_id=PAYMENTS_LOG_CHAT_ID,
                    photo=photo.file_id,
                    caption=caption,
                    parse_mode=ParseMode.MARKDOWN,
                )
            except Exception as e:
                logger.error("Failed to forward payment proof to log group: %s", e)

        await message.reply_text(
            "✅ קיבלנו את אישור התשלום שלך.\n"
            "האדמינים יאשרו אותו ותקבל הודעה אישית + גישה לשער והקהילה.",
            parse_mode=ParseMode.MARKDOWN,
        )

    except Exception as e:
        logger.error("Error in handle_payment_photo: %s", e)


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_OWNER_IDS


async def cmd_approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /approve <user_id>
    """
    msg = update.effective_message
    from_user = update.effective_user

    if not is_admin(from_user.id):
        await msg.reply_text("אין לך הרשאה לפקודה זו.")
        return

    parts = msg.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await msg.reply_text("שימוש: /approve <user_id>")
        return

    target_id = int(parts[1])

    try:
        update_payment_status(target_id, "approved", None)
        ensure_promoter(target_id)
        incr_metric("approved_payments")
    except Exception as e:
        logger.error("Failed to update DB in /approve: %s", e)

    bot_username = context.bot.username
    personal_link = build_personal_share_link(target_id, bot_username)

    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=(
                "🎉 *התשלום שלך אושר!*\n\n"
                "קיבלת כעת גישה לשער הקהילה והמערכת.\n\n"
                f"🔗 לינק אישי לשיתוף:\n`{personal_link}`\n\n"
                "תוכל לשתף את הלינק הזה עם חברים ושותפים.\n"
            ),
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:
        logger.error("Failed to notify approved user: %s", e)

    if PAYMENTS_LOG_CHAT_ID:
        try:
            txt = (
                "✅ *אישור תשלום בוצע* ✅\n\n"
                f"target_user_id: `{target_id}`\n"
                f"by_admin: `{from_user.id}`\n"
                f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"🔗 personal link: `{personal_link}`"
            )
            await context.bot.send_message(
                chat_id=PAYMENTS_LOG_CHAT_ID,
                text=txt,
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            logger.error("Failed to send approve log: %s", e)

    await msg.reply_text(
        f"אושר. נשלחה הודעה למשתמש {target_id} עם הלינק האישי שלו."
    )


async def cmd_reject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /reject <user_id> <reason>
    """
    msg = update.effective_message
    from_user = update.effective_user

    if not is_admin(from_user.id):
        await msg.reply_text("אין לך הרשאה לפקודה זו.")
        return

    parts = msg.text.split(maxsplit=2)
    if len(parts) < 3 or not parts[1].isdigit():
        await msg.reply_text("שימוש: /reject <user_id> <סיבה>")
        return

    target_id = int(parts[1])
    reason = parts[2]

    try:
        update_payment_status(target_id, "rejected", reason)
        incr_metric("rejected_payments")
    except Exception as e:
        logger.error("Failed to update DB in /reject: %s", e)

    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=(
                "❌ *התשלום לא אושר*\n\n"
                f"סיבה: {reason}\n\n"
                "במידה ואתה סבור שמדובר בטעות – פנה לתמיכה."
            ),
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:
        logger.error("Failed to notify rejected user: %s", e)

    if PAYMENTS_LOG_CHAT_ID:
        try:
            txt = (
                "❌ *דחיית תשלום* ❌\n\n"
                f"target_user_id: `{target_id}`\n"
                f"by_admin: `{from_user.id}`\n"
                f"reason: {reason}\n"
                f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            )
            await context.bot.send_message(
                chat_id=PAYMENTS_LOG_CHAT_ID,
                text=txt,
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            logger.error("Failed to send reject log: %s", e)

    await msg.reply_text(f"דווח. התשלום של {target_id} נדחה.")


# =========================
# Keyboards
# =========================


def main_menu_keyboard(lang: str = "he") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    trans_manager.get_text("join_community", lang),
                    callback_data="join",
                )
            ],
            [
                InlineKeyboardButton(
                    trans_manager.get_text("bank_payment", lang),
                    callback_data="bankinfo",
                )
            ],
            [
                InlineKeyboardButton(
                    "📲 קישור לקהילה", url=COMMUNITY_GROUP_LINK
                )
            ],
            [
                InlineKeyboardButton(
                    trans_manager.get_text("support", lang),
                    url=SUPPORT_GROUP_LINK,
                )
            ],
        ]
    )


def payment_links_keyboard(lang: str = "he") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📲 תשלום בפייבוקס", url=PAYBOX_URL)],
            [InlineKeyboardButton("📲 תשלום בביט", url=BIT_URL)],
            [InlineKeyboardButton("💳 תשלום ב-PayPal", url=PAYPAL_URL)],
            [
                InlineKeyboardButton(
                    trans_manager.get_text("back", lang),
                    callback_data="back_main",
                )
            ],
        ]
    )


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    user = update.effective_user
    lang = trans_manager.get_user_language(user.id)

    if data == "join":
        await query.edit_message_text(
            "כדי להצטרף לקהילה – בצע תשלום 39 ₪ לפי פרטי התשלום "
            "ושלח צילום מסך של האישור לבוט.\n\n"
            "לחץ על 'פרטי תשלום' כדי לקבל את כל האפשרויות.",
            reply_markup=payment_links_keyboard(lang),
        )
        return

    if data == "bankinfo":
        await cmd_bankinfo(update, context)
        return

    if data == "back_main":
        await query.edit_message_text(
            "חזרה לתפריט הראשי:",
            reply_markup=main_menu_keyboard(lang),
        )
        return


# =========================
# FastAPI + Webhook
# =========================

app = FastAPI(title="BotShop – SLH Gateway", version="2.0.0")

ptb_app: Optional[Application] = None


@app.on_event("startup")
async def on_startup() -> None:
    global ptb_app

    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not set – bot will not run.")
        return

    if DB_AVAILABLE:
        try:
            init_schema()
        except Exception as e:
            logger.error("Failed to init DB schema: %s", e)

    ptb_app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .rate_limiter(AIORateLimiter())
        .build()
    )

    ptb_app.add_handler(CommandHandler("start", cmd_start))
    ptb_app.add_handler(CommandHandler("help", cmd_help))
    ptb_app.add_handler(CommandHandler("bankinfo", cmd_bankinfo))
    ptb_app.add_handler(CommandHandler("whoami", cmd_whoami))
    ptb_app.add_handler(CommandHandler("approve", cmd_approve))
    ptb_app.add_handler(CommandHandler("reject", cmd_reject))

    ptb_app.add_handler(
        MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_payment_photo)
    )
    ptb_app.add_handler(CallbackQueryHandler(callback_handler))

    await ptb_app.initialize()
    await ptb_app.start()

    if WEBHOOK_URL:
        webhook_full = WEBHOOK_URL.rstrip("/") + "/webhook"
        try:
            await ptb_app.bot.set_webhook(webhook_full)
            logger.info("Webhook set to %s", webhook_full)
        except Exception as e:
            logger.error("Failed to set webhook: %s", e)
    else:
        logger.warning("WEBHOOK_URL not set – webhook will not be configured.")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    global ptb_app
    if ptb_app is not None:
        await ptb_app.stop()
        await ptb_app.shutdown()


@app.get("/healthz")
async def healthz() -> JSONResponse:
    return JSONResponse({"ok": True, "service": "botshop", "db": DB_AVAILABLE})


@app.post("/webhook")
async def telegram_webhook(request: Request) -> Response:
    """
    נקודת ה-webhook שמקבלת עדכונים מטלגרם.
    """
    global ptb_app
    if ptb_app is None:
        return Response(status_code=HTTPStatus.SERVICE_UNAVAILABLE.value)

    data = await request.json()
    update = Update.de_json(data, ptb_app.bot)
    await ptb_app.process_update(update)

    return Response(status_code=HTTPStatus.OK.value)


# =========================
# Admin Stats & Dashboard
# =========================


@app.get("/admin/stats")
async def admin_stats(token: str = "") -> JSONResponse:
    """
    JSON לסטטיסטיקות – דשבורד אדמין.
    """
    if not ADMIN_DASH_TOKEN or token != ADMIN_DASH_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if not DB_AVAILABLE:
        return JSONResponse({"db": "disabled"})

    try:
        stats = get_approval_stats()
        monthly = get_monthly_payments(datetime.utcnow().year, datetime.utcnow().month)
        top_ref = get_top_referrers(5)
        start_stats = get_start_stats()
    except Exception as e:
        logger.error("Failed to get admin stats: %s", e)
        raise HTTPException(status_code=500, detail="DB error")

    return JSONResponse(
        {
            "db": "enabled",
            "payments_stats": stats,
            "monthly_breakdown": monthly,
            "top_referrers": top_ref,
            "start_stats": start_stats,
            "system": {
                "ton_discount": TON_DISCOUNT_PERCENT,
                "ton_wallet": TON_WALLET,
                "version": "2.0.0",
            },
        }
    )


@app.get("/admin/dashboard")
async def admin_dashboard(token: str = "") -> HTMLResponse:
    """
    דשבורד HTML לאדמין – מציג סטטיסטיקות תשלומים וקמפיינים.
    """
    if not ADMIN_DASH_TOKEN or token != ADMIN_DASH_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

    html_content = """
<!DOCTYPE html>
<html dir="rtl">
<head>
    <title>Admin Dashboard - Buy My Shop</title>
    <meta charset="UTF-8">
    <style>
        body { font-family: Arial; margin: 20px; }
        .card { border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 8px; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; }
    </style>
</head>
<body>
    <h1>Admin Dashboard - Buy My Shop</h1>
    <div id="stats"></div>
    <script>
        fetch('/admin/stats?token=' + new URLSearchParams(window.location.search).get('token'))
            .then(r => r.json())
            .then(data => {
                const ps = data.payments_stats || {};
                const ss = data.start_stats || {};
                const top = data.top_referrers || [];
                const topList = top.map(r => 
                    `<li>${r.username || r.referrer_id} – ${r.total_referrals} הפניות (${r.total_points || 0} נק')</li>`
                ).join('');

                document.getElementById('stats').innerHTML = `
                    <div class="stats">
                        <div class="card">משתמשים משלמים (payments): ${ps.total || 0}</div>
                        <div class="card">תשלומים שאושרו: ${ps.approved || 0}</div>
                        <div class="card">תשלומים ממתינים: ${ps.pending || 0}</div>
                        <div class="card">כל לחיצות /start: ${ss.total || 0}</div>
                        <div class="card">כניסות ישירות (/start בלי ref): ${ss.direct || 0}</div>
                        <div class="card">כניסות מקמפיינים (/start עם ref): ${ss.with_ref || 0}</div>
                        <div class="card">
                            <strong>ממליצים מובילים (Top Referrers)</strong>
                            <ul>${topList || '<li>אין עדיין נתונים</li>'}</ul>
                        </div>
                    </div>
                `;
            });
    </script>
</body>
</html>
"""
    return HTMLResponse(html_content)
