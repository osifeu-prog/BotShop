# main.py
import os
import logging
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime
from http import HTTPStatus
from typing import Deque, Set, Literal, Optional, Dict, Any

from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware

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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("gateway-bot")

# =========================
# DB
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
        set_promoter_bank,
        get_promoter_bank,
        increment_metric,
        get_metric,
        get_share_points,
        get_top_sharers,
    )
    DB_AVAILABLE = True
    logger.info("DB module loaded successfully, DB logging enabled.")
except Exception as e:
    logger.warning("DB not available (missing db.py or error loading it): %s", e)
    DB_AVAILABLE = False

# =========================
# ENV
# =========================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is not set")

if not WEBHOOK_URL:
    raise RuntimeError("WEBHOOK_URL environment variable is not set")

logger.info("Starting bot with WEBHOOK_URL=%s", WEBHOOK_URL)

COMMUNITY_GROUP_LINK = "https://t.me/+HIzvM8sEgh1kNWY0"
COMMUNITY_GROUP_ID = -1002981609404

SUPPORT_GROUP_LINK = "https://t.me/+1ANn25HeVBoxNmRk"
SUPPORT_GROUP_ID = -1001651506661

DEVELOPER_USER_ID = 224223270
PAYMENTS_LOG_CHAT_ID = -1001748319682

PAYBOX_URL = os.environ.get("PAYBOX_URL", "https://links.payboxapp.com/1SNfaJ6XcYb")
BIT_URL = os.environ.get(
    "BIT_URL",
    "https://www.bitpay.co.il/app/share-info?i=190693822888_19l4oyvE",
)
PAYPAL_URL = os.environ.get("PAYPAL_URL", "https://paypal.me/osifdu")

LANDING_URL = os.environ.get(
    "LANDING_URL",
    "https://slh-nft.com/",
)

# שם משתמש של הבוט בטלגרם – חשוב מאוד להפניות נכונות
# לדוגמה: Buy_My_Shop_bot
BOT_USERNAME = os.environ.get("BOT_USERNAME", "Buy_My_Shop_bot")

ADMIN_DASH_TOKEN = os.environ.get("ADMIN_DASH_TOKEN")

START_IMAGE_PATH = os.environ.get("START_IMAGE_PATH", "assets/start_banner.jpg")

BANK_DETAILS_BASE = (
    "בנק הפועלים\n"
    "סניף כפר גנים (153)\n"
    "חשבון 73462\n"
    "המוטב: קאופמן צביקה\n"
)

BANK_DETAILS = (
    "🏦 *תשלום בהעברה בנקאית*\n\n"
    f"{BANK_DETAILS_BASE}\n\n"
    "סכום: *39 ש\"ח*\n"
)

TON_DETAILS = (
    "💎 *תשלום ב-TON (טלגרם קריפטו)*\n\n"
    "אם יש לך כבר ארנק טלגרם (TON Wallet), אפשר לשלם גם ישירות בקריפטו.\n\n"
    "ארנק לקבלת התשלום:\n"
    "`UQCr743gEr_nqV_0SBkSp3CtYS_15R3LDLBvLmKeEv7XdGvp`\n\n"
    "סכום: *39 ש\"ח* (שווה ערך ב-TON)\n\n"
    "👀 בקרוב נחלק גם טוקני *SLH* ייחודיים על רשת TON וחלק מהמשתתפים יקבלו NFT\n"
    "על פעילות, שיתופים והשתתפות בקהילה.\n"
)

PAYBOX_DETAILS = (
    "📲 *תשלום בביט / פייבוקס / PayPal*\n\n"
    "אפשר לשלם דרך האפליקציות שלך בביט או פייבוקס.\n"
    "קישורי התשלום המעודכנים מופיעים בכפתורים למטה.\n\n"
    "סכום: *39 ש\"ח*\n"
)

ADMIN_IDS = {DEVELOPER_USER_ID}
PayMethod = Literal["bank", "paybox", "ton"]

# =========================
# Dedup
# =========================
_processed_ids: Deque[int] = deque(maxlen=1000)
_processed_set: Set[int] = set()


def is_duplicate_update(update: Update) -> bool:
    if update is None:
        return False
    uid = update.update_id
    if uid in _processed_set:
        return True
    _processed_set.add(uid)
    _processed_ids.append(uid)
    if len(_processed_set) > len(_processed_ids) + 10:
        valid = set(_processed_ids)
        _processed_set.intersection_update(valid)
    return False


# =========================
# bot_data stores + paid flags
# =========================
def get_payments_store(context: ContextTypes.DEFAULT_TYPE) -> Dict[int, Dict[str, Any]]:
    store = context.application.bot_data.get("payments")
    if store is None:
        store = {}
        context.application.bot_data["payments"] = store
    return store


def get_pending_rejects(context: ContextTypes.DEFAULT_TYPE) -> Dict[int, int]:
    store = context.application.bot_data.get("pending_rejects")
    if store is None:
        store = {}
        context.application.bot_data["pending_rejects"] = store
    return store


def mark_user_paid(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    """
    שומר בזיכרון (in-memory) שמזהה המשתמש הזה כבר עבר אישור תשלום.
    אם הבוט מופעל מחדש – המידע הזה מתאפס, אבל כל פעם שתאשר תשלום מחדש,
    המשתמש יחזור לרשימה.
    """
    app_data = context.application.bot_data
    paid = app_data.get("paid_users")
    if paid is None:
        paid = set()
        app_data["paid_users"] = paid
    paid.add(user_id)


def is_user_paid(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    """
    בודק (in-memory) אם המשתמש כבר סומן כמשתמש ששילם ואושר.
    """
    paid = context.application.bot_data.get("paid_users")
    if not paid:
        return False
    return user_id in paid


# =========================
# Telegram Application
# =========================
ptb_app: Application = (
    Application.builder()
    .updater(None)
    .token(BOT_TOKEN)
    .build()
)

# =========================
# Keyboards
# =========================
def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🚀 הצטרפות לקהילת העסקים (39 ₪)", callback_data="join")],
            [InlineKeyboardButton("ℹ מה אני מקבל?", callback_data="info")],
            [InlineKeyboardButton("🔗 שתף את שער הקהילה", callback_data="share")],
            [InlineKeyboardButton("🆘 תמיכה", callback_data="support")],
        ]
    )


def payment_methods_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🏦 העברה בנקאית", callback_data="pay_bank")],
            [InlineKeyboardButton("📲 ביט / פייבוקס / PayPal", callback_data="pay_paybox")],
            [InlineKeyboardButton("💎 טלגרם (TON)", callback_data="pay_ton")],
            [InlineKeyboardButton("⬅ חזרה לתפריט ראשי", callback_data="back_main")],
        ]
    )


def payment_links_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📲 תשלום בפייבוקס", url=PAYBOX_URL)],
            [InlineKeyboardButton("📲 תשלום בביט", url=BIT_URL)],
            [InlineKeyboardButton("💳 תשלום ב-PayPal", url=PAYPAL_URL)],
            [InlineKeyboardButton("⬅ חזרה לתפריט ראשי", callback_data="back_main")],
        ]
    )


def support_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("קבוצת תמיכה", url=SUPPORT_GROUP_LINK)],
            [InlineKeyboardButton("פניה למתכנת המערכת", url=f"tg://user?id={DEVELOPER_USER_ID}")],
            [InlineKeyboardButton("⬅ חזרה לתפריט ראשי", callback_data="back_main")],
        ]
    )


def admin_approval_keyboard(user_id: int, owner_id: Optional[int] = None) -> InlineKeyboardMarkup:
    """
    אם owner_id קיים – הכפתורים יכילו גם אותו, כדי שנדע מי המנהל האישי של העסקה.
    פורמט callback:
      adm_approve:<user_id>[:<owner_id>]
    """
    if owner_id is not None:
        suffix = f"{user_id}:{owner_id}"
    else:
        suffix = f"{user_id}"

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ אשר תשלום", callback_data=f"adm_approve:{suffix}"),
                InlineKeyboardButton("❌ דחה תשלום", callback_data=f"adm_reject:{suffix}"),
            ],
        ]
    )


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📊 סטטוס מערכת", callback_data="adm_status")],
            [InlineKeyboardButton("📈 מוני תמונה", callback_data="adm_counters")],
            [InlineKeyboardButton("💡 רעיונות לפיצ'רים", callback_data="adm_ideas")],
        ]
    )


# =========================
# Start image + metrics
# =========================
async def send_start_image(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, mode: str = "view"
) -> None:
    views = 0
    downloads = 0

    if DB_AVAILABLE:
        try:
            if mode == "view":
                views = increment_metric("start_image_views", 1)
                downloads = get_metric("start_image_downloads")
            elif mode == "download":
                downloads = increment_metric("start_image_downloads", 1)
                views = get_metric("start_image_views")
            else:  # reminder
                views = get_metric("start_image_views")
                downloads = get_metric("start_image_downloads")
        except Exception as e:
            logger.error("Failed to update metrics: %s", e)
    else:
        app_data = context.application.bot_data
        views = app_data.get("start_image_views", 0)
        downloads = app_data.get("start_image_downloads", 0)
        if mode == "view":
            views += 1
            app_data["start_image_views"] = views
        elif mode == "download":
            downloads += 1
            app_data["start_image_downloads"] = downloads

    if mode == "view":
        caption = (
            "🌐 שער הכניסה לקהילת העסקים\n"
            f"מספר הצגה כולל: *{views}*\n"
        )
    elif mode == "download":
        caption = (
            "🎁 זה העותק הממוספר שלך של שער הקהילה.\n"
            f"מספר סידורי לעותק: *#{downloads}*\n"
        )
    else:
        caption = (
            "⏰ תזכורת: בדוק שהלינקים של PayBox / Bit / PayPal עדיין תקפים.\n\n"
            f"מצב מונים כרגע:\n"
            f"• הצגות תמונה: {views}\n"
            f"• עותקים ממוספרים שנשלחו: {downloads}\n"
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
# Handlers
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message or update.effective_message
    if not message:
        return

    user = update.effective_user

    if DB_AVAILABLE and user:
        try:
            store_user(user.id, user.username)
        except Exception as e:
            logger.error("Failed to store user: %s", e)

    # /start ref<id> (מפיץ) – בלי ה-underscore
    if message.text and message.text.startswith("/start") and user:
        parts = message.text.split()
        if len(parts) > 1 and parts[1].startswith("ref"):
            try:
                referrer_id = int(parts[1].split("ref", 1)[1])
                if DB_AVAILABLE and referrer_id != user.id:
                    add_referral(referrer_id, user.id, source="bot_start")
                context.user_data["referrer_id"] = referrer_id
            except Exception as e:
                logger.error("Failed to add referral: %s", e)

    await send_start_image(context, message.chat_id, mode="view")

    text = (
        "ברוך הבא לשער הכניסה לקהילת העסקים שלנו 🌐\n\n"
        "כאן אתה מצטרף למערכת של *עסקים, שותפים וקהל יוצר ערך* סביב:\n"
        "• שיווק רשתי חכם\n"
        "• נכסים דיגיטליים (NFT, טוקני SLH)\n"
        "• מתנות, הפתעות ופרסים על פעילות ושיתופים\n\n"
        "מה תקבל בהצטרפות?\n"
        "✅ גישה לקבוצת עסקים פרטית\n"
        "✅ למידה משותפת איך לייצר הכנסות משיווק האקו-סיסטם שלנו\n"
        "✅ גישה למבצעים שיחולקו רק בקהילה\n"
        "✅ השתתפות עתידית בחלוקת טוקני *SLH* ו-NFT ייחודיים למשתתפים פעילים\n"
        "✅ נקודות על שיתופים – כל לחיצה על כפתור השיתוף מזכה ב-*5 נקודות*.\n\n"
        "הנקודות יוכלו בעתיד להיפדות למטבע קריפטו ייחודי לקהילה.\n\n"
        "דמי הצטרפות חד־פעמיים: *39 ש\"ח*.\n\n"
        "לאחר אישור התשלום *תקבל קישור לקהילת העסקים*.\n\n"
        "כדי להתחיל – בחר באפשרות הרצויה:"
    )

    await message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )


async def info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    text = (
        "ℹ *מה מקבלים בקהילה?*\n\n"
        "🚀 גישה לקבוצת עסקים סגורה.\n"
        "📚 תכנים על שיווק, מכירות ונכסים דיגיטליים.\n"
        "🎁 מתנות דיגיטליות, NFT והטבות ייחודיות.\n"
        "💎 טוקני *SLH* עתידיים על פעילות ושיתופים.\n"
        "🏆 משחק נקודות: כל שיתוף דרך הבוט מזכה ב-5 נקודות, "
        "והמצטיינים יזכו בפרסים.\n\n"
        "דמי הצטרפות חד־פעמיים: *39 ש\"ח*.\n\n"
        "כדי להצטרף – בחר אמצעי תשלום:"
    )

    await query.edit_message_text(
        text, parse_mode="Markdown", reply_markup=payment_methods_keyboard()
    )


async def join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    text = (
        "🔑 *הצטרפות לקהילת העסקים – 39 ש\"ח*\n\n"
        "בחר את אמצעי התשלום המתאים לך:\n"
        "• העברה בנקאית (יתכן לחשבון של המפיץ שהביא אותך)\n"
        "• ביט / פייבוקס / PayPal\n"
        "• טלגרם (TON)\n\n"
        "לאחר ביצוע התשלום:\n"
        "1. שלח כאן *צילום מסך או תמונה* של אישור התשלום.\n"
        "2. הבוט יעביר את האישור למארגנים לבדיקה.\n"
        "3. לאחר אישור ידני תקבל קישור לקהילת העסקים.\n\n"
        "אין קישור לקהילה לפני אישור תשלום."
    )

    await query.edit_message_text(
        text, parse_mode="Markdown", reply_markup=payment_methods_keyboard()
    )


async def support_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    text = (
        "🆘 *תמיכה ועזרה*\n\n"
        f"• קבוצת תמיכה: {SUPPORT_GROUP_LINK}\n"
        f"• פניה ישירה למתכנת המערכת: `tg://user?id={DEVELOPER_USER_ID}`\n\n"
        "או חזור לתפריט הראשי:"
    )

    await query.edit_message_text(
        text, parse_mode="Markdown", reply_markup=support_keyboard()
    )


async def share_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    שתף את שער הקהילה:
    - לפני תשלום מאושר: מציג הודעה שהאופציה נפתחת רק לאחר תשלום.
    - אחרי תשלום מאושר: נותן טקסט שיתוף + לינק אישי לאתר + לבוט.
    """
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    if not user:
        return
    user_id = user.id

    # אם המשתמש עדיין לא אושר כתשלום – נחסום את השיתוף
    if not is_user_paid(context, user_id):
        text = (
            "🔐 *פיצ׳ר השיתוף נפתח רק לאחר תשלום מאושר*\n\n"
            "כדי לקבל בוט שיתופים אישי ונקודות על כל שיתוף, "
            "צריך קודם להשלים תשלום חד־פעמי של 39 ש\"ח ולאשר אותו.\n\n"
            "1️⃣ בחר בתפריט: \"🚀 הצטרפות לקהילת העסקים (39 ₪)\"\n"
            "2️⃣ בחר אמצעי תשלום\n"
            "3️⃣ שלח צילום מסך של האישור לבוט\n"
            "4️⃣ אחרי אישור ידני תקבל ממני:\n"
            "   • קישור לקהילת העסקים\n"
            "   • קלף ממוספר אישי\n"
            "   • הסבר ולינק שיתוף אישי שדרכו תצבור נקודות.\n"
        )
        await query.message.reply_text(text, parse_mode="Markdown")
        return

    # מפה – משתמש ששילם ואושר (סומן בזיכרון)
    base_bot_url = f"https://t.me/{BOT_USERNAME}"

    # קישור אישי לבוט עם פרמטר ref<user_id> (ללא underscore כדי לא לשבור Markdown)
    share_link = f"{base_bot_url}?start=ref{user_id}"

    # קישור לשער האתר עם ref=<user_id> כדי לדעת מי הביא מי
    sep = "&" if "?" in LANDING_URL else "?"
    landing_with_ref = f"{LANDING_URL}{sep}ref={user_id}"

    text = (
        "🔗 *שתף את שער הקהילה*\n\n"
        "מהבוט הזה אתה משתף את *שער האתר הרשמי* של המשחק, עם קרדיט הפניה אישי שלך.\n\n"
        "העתק ושלח את הטקסט הבא לחברים / סטורי / סטטוס:\n\n"
        f"\"אני משחק במשחק קהילת העסקים שלנו – כניסה דרך השער: {landing_with_ref}\"\n\n"
        "קישור ישיר לבוט שלך (עם קרדיט הפניה בתחתית המסך):\n"
        f"{share_link}\n\n"
        "כל שימוש בכפתור השיתוף בבוט מזכה אותך ב-*5 נקודות*.\n"
        "בהמשך הנקודות ייפדו למטבע קריפטו יחודי לקהילה ופרסים נוספים.\n"
    )

    await query.message.reply_text(text, parse_mode="Markdown")

    if DB_AVAILABLE and user_id:
        try:
            create_reward(
                user_id,
                "SHARE_POINTS",
                "נקודות על שימוש בכפתור שיתוף",
                points=5,
            )
        except Exception as e:
            logger.error("Failed to credit share points: %s", e)


async def back_main_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    fake_update = Update(update_id=update.update_id, message=query.message)
    await start(fake_update, context)


def build_bank_details_for_user(context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    מחזיר טקסט בנק למשתמש – אם הגיע דרך referrer שהוא מפיץ עם בנק משלו, נשתמש בו.
    אחרת – הבנק הבסיסי.
    """
    referrer_id = context.user_data.get("referrer_id")
    if not DB_AVAILABLE or not referrer_id:
        return BANK_DETAILS

    try:
        custom = get_promoter_bank(referrer_id)
    except Exception as e:
        logger.error("Failed to get promoter bank: %s", e)
        custom = None

    if not custom:
        return BANK_DETAILS

    return (
        "🏦 *תשלום בהעברה בנקאית למפיץ שהביא אותך*\n\n"
        f"{custom}\n\n"
        "סכום: *39 ש\"ח*\n"
    )


async def payment_method_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data

    method: Optional[PayMethod] = None
    details_text = ""

    if data == "pay_bank":
        method = "bank"
        details_text = build_bank_details_for_user(context)
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
        "לאחר ביצוע התשלום:\n"
        "1. שלח כאן *צילום מסך או תמונה* של אישור התשלום.\n"
        "2. הבוט יעביר את האישור למארגנים לבדיקה.\n"
        "3. לאחר אישור ידני תקבל קישור לקהילת העסקים.\n"
    )

    await query.edit_message_text(
        text, parse_mode="Markdown", reply_markup=payment_links_keyboard()
    )


# =========================
# תשלומים
# =========================

async def handle_payment_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message or not message.photo:
        return

    user = update.effective_user
    chat_id = message.chat_id
    username = f"@{user.username}" if user and user.username else "(ללא שם משתמש)"

    pay_method = context.user_data.get("last_pay_method", "unknown")
    pay_method_text = {
        "bank": "העברה בנקאית",
        "paybox": "ביט / פייבוקס / PayPal",
        "ton": "טלגרם (TON)",
        "unknown": "לא ידוע",
    }.get(pay_method, "לא ידוע")

    # מי המפיץ שהביא את המשתמש הזה (אם יש)?
    referrer_id = context.user_data.get("referrer_id")
    owner_id = referrer_id or DEVELOPER_USER_ID  # מנהל העסקאות עבור המשתמש הזה

    caption_log = (
        "📥 התקבל אישור תשלום חדש.\n\n"
        f"user_id = {user.id}\n"
        f"username = {username}\n"
        f"from chat_id = {chat_id}\n"
        f"שיטת תשלום: {pay_method_text}\n"
        f"מנהל העסקה (owner_id): {owner_id}\n\n"
        "לאישור (עבור אדמין ראשי):\n"
        f"/approve {user.id}\n"
        f"/reject {user.id} <סיבה>\n"
        "(או להשתמש בכפתורי האישור/דחייה מתחת להודעה זו)\n"
    )

    photo = message.photo[-1]
    file_id = photo.file_id

    payments = get_payments_store(context)
    payments[user.id] = {
        "file_id": file_id,
        "pay_method": pay_method_text,
        "username": username,
        "chat_id": chat_id,
        "owner_id": owner_id,
    }

    if DB_AVAILABLE:
        try:
            log_payment(user.id, username, pay_method_text)
        except Exception as e:
            logger.error("Failed to log payment to DB: %s", e)

    # שליחה לקבוצת לוגים מרכזית (בשבילך)
    try:
        await context.bot.send_photo(
            chat_id=PAYMENTS_LOG_CHAT_ID,
            photo=file_id,
            caption=caption_log,
            reply_markup=admin_approval_keyboard(user.id),
        )
    except Exception as e:
        logger.error("Failed to forward payment photo to log group: %s", e)
        try:
            await context.bot.send_photo(
                chat_id=DEVELOPER_USER_ID,
                photo=file_id,
                caption="(Fallback – לא הצלחתי לשלוח לקבוצת לוגים)\n\n"
                + caption_log,
                reply_markup=admin_approval_keyboard(user.id),
            )
        except Exception as e2:
            logger.error("Failed to send fallback payment: %s", e2)

    # בנוסף – שליחה למנהל האישי (המפיץ שהביא אותו), אם זה לא אתה
    if owner_id != DEVELOPER_USER_ID:
        try:
            personal_caption = (
                "📥 התקבל אישור תשלום חדש של משתמש שהגיע דרך הלינק שלך.\n\n"
                f"user_id = {user.id}\n"
                f"username = {username}\n"
                f"שיטת תשלום: {pay_method_text}\n\n"
                "אתה יכול לאשר או לדחות את התשלום בכפתורים מטה.\n"
            )
            await context.bot.send_photo(
                chat_id=owner_id,
                photo=file_id,
                caption=personal_caption,
                reply_markup=admin_approval_keyboard(user.id, owner_id=owner_id),
            )
        except Exception as e:
            logger.error("Failed to send payment to personal owner %s: %s", owner_id, e)

    await message.reply_text(
        "תודה! אישור התשלום התקבל ונשלח לבדיקה ✅\n"
        "לאחר אישור ידני תקבל ממני קישור להצטרפות לקהילת העסקים.\n\n"
        "אם יש שאלה דחופה – אפשר לפנות גם לקבוצת התמיכה.",
        reply_markup=support_keyboard(),
    )


# =========================
# אישור / דחייה
# =========================

async def do_approve(
    target_id: int, context: ContextTypes.DEFAULT_TYPE, source_message
) -> None:
    # נסמן בזיכרון שהמשתמש הזה אושר כתשלום – פותח לו את השיתוף
    mark_user_paid(context, target_id)

    text = (
        "✅ התשלום שלך אושר!\n\n"
        "ברוך הבא לקהילת העסקים שלנו 🎉\n"
        "הנה הקישור להצטרפות לקהילה:\n"
        f"{COMMUNITY_GROUP_LINK}\n\n"
        "בהודעה הבאה אשלח לך את הקלף הממוספר שלך, "
        "וגם הסבר איך להפוך למפיץ ולקבל נקודות על שיתופים.\n"
    )

    try:
        await context.bot.send_message(chat_id=target_id, text=text)

        # עותק ממוספר של התמונה
        await send_start_image(context, target_id, mode="download")

        # מסר נוסף – פאנל מפיץ זוטר
        base_bot_url = f"https://t.me/{BOT_USERNAME}"
        share_link = f"{base_bot_url}?start=ref{target_id}"
        points = get_share_points(target_id) if DB_AVAILABLE else 0

        promo_text = (
            "📣 עכשיו אתה חלק מהמשחק של המפיצים בקהילה!\n\n"
            "1️⃣ כל שיתוף של שער הקהילה דרך כפתור השיתוף בבוט מזכה אותך ב-*5 נקודות*.\n"
            "2️⃣ בהמשך הנקודות ייפדו למטבע קריפטו ייחודי (SLH) ופרסים נוספים.\n"
            "3️⃣ אתה יכול להגדיר חשבון בנק אישי לקבלת תשלומים מההפניות שלך:\n"
            "   כתוב: /set_bank ואז פרטי הבנק שלך (שורה אחת).\n\n"
            "לינק הפניה האישי שלך לבוט:\n"
            f"{share_link}\n\n"
            "לצפייה בנקודות שלך ולוח המפיצים:\n"
            "/my_panel – לוח אישי\n"
            "/share_board – לוח שיתופים ציבורי\n\n"
            f"נקודות שצברת עד עכשיו: {points}\n"
        )

        await context.bot.send_message(
            chat_id=target_id, text=promo_text, parse_mode="Markdown"
        )

        if DB_AVAILABLE:
            try:
                update_payment_status(target_id, "approved", None)
            except Exception as e:
                logger.error("Failed to update payment status in DB: %s", e)

        if source_message:
            await source_message.reply_text(
                f"אושר ונשלח קישור + קלף ממוספר + פאנל מפיץ למשתמש {target_id}."
            )
    except Exception as e:
        logger.error("Failed to send approval message: %s", e)
        if source_message:
            await source_message.reply_text(
                f"שגיאה בשליחת הודעה למשתמש {target_id}: {e}"
            )


async def do_reject(
    target_id: int, reason: str, context: ContextTypes.DEFAULT_TYPE, source_message
) -> None:
    payments = context.application.bot_data.get("payments", {})
    payment_info = payments.get(target_id)

    base_text = (
        "לצערנו לא הצלחנו לאמת את התשלום שנשלח.\n\n"
        f"סיבה: {reason}\n\n"
        "אם לדעתך מדובר בטעות – אנא פנה אלינו עם פרטי התשלום או נסה לשלוח מחדש."
    )

    try:
        if payment_info and payment_info.get("file_id"):
            await context.bot.send_photo(
                chat_id=target_id,
                photo=payment_info["file_id"],
                caption=base_text,
            )
        else:
            await context.bot.send_message(chat_id=target_id, text=base_text)

        if DB_AVAILABLE:
            try:
                update_payment_status(target_id, "rejected", reason)
            except Exception as e:
                logger.error("Failed to update payment status in DB: %s", e)

        if source_message:
            await source_message.reply_text(
                f"התשלום של המשתמש {target_id} נדחה והודעה נשלחה עם הסיבה."
            )
    except Exception as e:
        logger.error("Failed to send rejection message: %s", e)
        if source_message:
            await source_message.reply_text(
                f"שגיאה בשליחת הודעת דחייה למשתמש {target_id}: {e}"
            )


async def approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.effective_user.id not in ADMIN_IDS:
        await update.effective_message.reply_text(
            "אין לך הרשאה לבצע פעולה זו.\n"
            "אם אתה חושב שזו טעות – דבר עם המתכנת: @OsifEU"
        )
        return

    if not context.args:
        await update.effective_message.reply_text("שימוש: /approve <user_id>")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("user_id חייב להיות מספרי.")
        return

    await do_approve(target_id, context, update.effective_message)


async def reject_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.effective_user.id not in ADMIN_IDS:
        await update.effective_message.reply_text(
            "אין לך הרשאה לבצע פעולה זו.\n"
            "אם אתה חושב שזו טעות – דבר עם המתכנת: @OsifEU"
        )
        return

    if len(context.args) < 2:
        await update.effective_message.reply_text("שימוש: /reject <user_id> <סיבה>")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("user_id חייב להיות מספרי.")
        return

    reason = " ".join(context.args[1:])
    await do_reject(target_id, reason, context, update.effective_message)


# =========================
# כפתורי אדמין (כולל בעלי בוט אישי)
# =========================

async def admin_approve_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    admin = query.from_user

    data = query.data or ""
    try:
        _, rest = data.split(":", 1)
        parts = rest.split(":")
        user_id_str = parts[0]
        target_id = int(user_id_str)
        owner_id = int(parts[1]) if len(parts) > 1 else None
    except Exception:
        await query.answer("שגיאה בנתוני המשתמש.", show_alert=True)
        return

    # רק אדמין ראשי או בעל הבוט האישי (owner_id) יכול לאשר
    if admin.id not in ADMIN_IDS and (owner_id is None or admin.id != owner_id):
        await query.answer(
            "אין לך הרשאה לאשר תשלום זה.\nאם אתה חושב שזו טעות – דבר עם @OsifEU",
            show_alert=True,
        )
        return

    await do_approve(target_id, context, query.message)


async def admin_reject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    admin = query.from_user

    data = query.data or ""
    try:
        _, rest = data.split(":", 1)
        parts = rest.split(":")
        user_id_str = parts[0]
        target_id = int(user_id_str)
        owner_id = int(parts[1]) if len(parts) > 1 else None
    except Exception:
        await query.answer("שגיאה בנתוני המשתמש.", show_alert=True)
        return

    # רק אדמין ראשי או בעל הבוט האישי (owner_id) יכול לדחות
    if admin.id not in ADMIN_IDS and (owner_id is None or admin.id != owner_id):
        await query.answer(
            "אין לך הרשאה לדחות תשלום זה.\nאם אתה חושב שזו טעות – דבר עם @OsifEU",
            show_alert=True,
        )
        return

    pending = get_pending_rejects(context)
    pending[admin.id] = target_id

    await query.message.reply_text(
        f"❌ בחרת לדחות את התשלום של המשתמש {target_id}.\n"
        "שלח עכשיו את סיבת הדחייה בהודעה אחת (טקסט), והיא תישלח אליו יחד עם צילום התשלום."
    )


async def admin_reject_reason_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    user = update.effective_user
    if user is None:
        return

    pending = get_pending_rejects(context)
    if user.id not in pending:
        # לא באמצע תהליך דחייה
        return

    target_id = pending.pop(user.id)
    reason = update.message.text.strip()
    await do_reject(target_id, reason, context, update.effective_message)


# =========================
# לוח מפנים / שיתופים / Rewards
# =========================

async def admin_leaderboard_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if update.effective_user is None or update.effective_user.id not in ADMIN_IDS:
        await update.effective_message.reply_text(
            "אין לך הרשאה לצפות בלוח המפנים.\n"
            "אם אתה חושב שזו טעות – דבר עם המתכנת: @OsifEU"
        )
        return

    if not DB_AVAILABLE:
        await update.effective_message.reply_text("DB לא פעיל כרגע.")
        return

    try:
        rows = get_top_referrers(10)
    except Exception as e:
        logger.error("Failed to get top referrers: %s", e)
        await update.effective_message.reply_text("שגיאה בקריאת נתוני הפניות.")
        return

    if not rows:
        await update.effective_message.reply_text("אין עדיין נתוני הפניות.")
        return

    lines = ["🏆 *לוח מפנים – Top 10* \n"]
    rank = 1
    for row in rows:
        rid = row["referrer_id"]
        uname = row["username"] or f"ID {rid}"
        total = row["total_referrals"]
        points = row["total_points"]
        lines.append(f"{rank}. {uname} – {total} הפניות ({points} נק׳)")
        rank += 1

    await update.effective_message.reply_text(
        "\n".join(lines), parse_mode="Markdown"
    )


async def admin_payments_stats_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if update.effective_user is None or update.effective_user.id not in ADMIN_IDS:
        await update.effective_message.reply_text(
            "אין לך הרשאה לצפות בסטטיסטיקות.\n"
            "אם אתה צריך גישה – דבר עם המתכנת: @OsifEU"
        )
        return

    if not DB_AVAILABLE:
        await update.effective_message.reply_text("DB לא פעיל כרגע.")
        return

    now = datetime.utcnow()
    year, month = now.year, now.month

    try:
        rows = get_monthly_payments(year, month)
        stats = get_approval_stats()
    except Exception as e:
        logger.error("Failed to get payment stats: %s", e)
        await update.effective_message.reply_text("שגיאה בקריאת נתוני תשלום.")
        return

    lines = [f"📊 *דוח תשלומים – {month:02d}/{year}* \n"]

    if rows:
        lines.append("*לפי אמצעי תשלום וסטטוס:*")
        for row in rows:
            lines.append(f"- {row['pay_method']} / {row['status']}: {row['count']}")
    else:
        lines.append("אין תשלומים בחודש זה.")

    if stats and stats.get("total", 0) > 0:
        total = stats["total"]
        approved = stats["approved"]
        rejected = stats["rejected"]
        pending = stats["pending"]
        approval_rate = round(approved * 100 / total, 1) if total else 0.0
        lines.append("\n*סטטוס כללי:*")
        lines.append(f"- אושרו: {approved}")
        lines.append(f"- נדחו: {rejected}")
        lines.append(f"- ממתינים: {pending}")
        lines.append(f"- אחוז אישור: {approval_rate}%")
    else:
        lines.append("\nאין עדיין נתונים כלליים.")

    await update.effective_message.reply_text(
        "\n".join(lines), parse_mode="Markdown"
    )


async def admin_reward_slh_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if update.effective_user is None or update.effective_user.id not in ADMIN_IDS:
        await update.effective_message.reply_text(
            "אין לך הרשאה ליצור Rewards.\n"
            "אם אתה צריך גישה – דבר עם המתכנת: @OsifEU"
        )
        return

    if not DB_AVAILABLE:
        await update.effective_message.reply_text("DB לא פעיל כרגע.")
        return

    if len(context.args) < 3:
        await update.effective_message.reply_text(
            "שימוש: /reward_slh <user_id> <points> <reason...>"
        )
        return

    try:
        target_id = int(context.args[0])
        points = int(context.args[1])
    except ValueError:
        await update.effective_message.reply_text(
            "user_id ו-points חייבים להיות מספריים."
        )
        return

    reason = " ".join(context.args[2:])

    try:
        create_reward(target_id, "SLH", reason, points)
    except Exception as e:
        logger.error("Failed to create reward: %s", e)
        await update.effective_message.reply_text("שגיאה ביצירת Reward.")
        return

    try:
        await update.effective_message.reply_text(
            f"נוצר Reward SLH למשתמש {target_id} ({points} נק׳): {reason}"
        )

        await ptb_app.bot.send_message(
            chat_id=target_id,
            text=(
                "🎁 קיבלת Reward על הפעילות שלך בקהילה!\n\n"
                f"סוג: *SLH* ({points} נק׳)\n"
                f"סיבה: {reason}\n\n"
                "Reward זה יצטרף למאזן שלך ויהווה בסיס להנפקת מטבעות/נכסים "
                "דיגיטליים בעתיד."
            ),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error("Failed to notify user about reward: %s", e)


async def share_board_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """לוח שיתופים ציבורי – /share_board (לא רק אדמין)"""
    if not DB_AVAILABLE:
        await update.effective_message.reply_text(
            "לוח השיתופים לא פעיל כרגע (DB כבוי)."
        )
        return

    try:
        rows = get_top_sharers(20)
    except Exception as e:
        logger.error("Failed to get top sharers: %s", e)
        await update.effective_message.reply_text("שגיאה בקריאת נתוני שיתופים.")
        return

    if not rows:
        await update.effective_message.reply_text("אין עדיין נקודות על שיתופים.")
        return

    lines = ["📣 *לוח שיתופים – Top 20* \n"]
    rank = 1
    for row in rows:
        uid = row["user_id"]
        uname = row["username"] or f"ID {uid}"
        pts = row["total_points"]
        lines.append(f"{rank}. {uname} – {pts} נק׳ שיתוף")
        rank += 1

    await update.effective_message.reply_text(
        "\n".join(lines), parse_mode="Markdown"
    )


# =========================
# פאנל מפיץ זוטר – /set_bank /my_panel
# =========================

async def set_bank_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        return

    if not DB_AVAILABLE:
        await update.effective_message.reply_text(
            "שמירת פרטי הבנק זמינה רק כשה-DB פעיל."
        )
        return

    if not context.args:
        await update.effective_message.reply_text(
            "שימוש: /set_bank <פרטי הבנק בשורה אחת>\n"
            "לדוגמה:\n"
            "/set_bank בנק הפועלים, סניף 153, חשבון 123456, המוטב: ישראל ישראלי"
        )
        return

    bank_details = " ".join(context.args)

    try:
        set_promoter_bank(user.id, bank_details)
    except Exception as e:
        logger.error("Failed to set promoter bank: %s", e)
        await update.effective_message.reply_text("שגיאה בשמירת פרטי הבנק.")
        return

    await update.effective_message.reply_text(
        "פרטי הבנק שלך נשמרו כמפיץ ✅\n"
        "משתמשים שיגיעו דרך הלינק האישי שלך ויבחרו תשלום בהעברה בנקאית "
        "יקבלו את פרטי הבנק האלה לתשלום."
    )


async def my_panel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        return

    user_id = user.id

    base_bot_url = f"https://t.me/{BOT_USERNAME}"
    share_link = f"{base_bot_url}?start=ref{user_id}"
    points = get_share_points(user_id) if DB_AVAILABLE else 0
    bank_details = None

    if DB_AVAILABLE:
        try:
            bank_details = get_promoter_bank(user_id)
        except Exception as e:
            logger.error("Failed to get promoter bank in my_panel: %s", e)

    bank_text = (
        bank_details
        if bank_details
        else "לא הוגדרו עדיין פרטי בנק אישיים. השתמש ב-/set_bank כדי להגדיר."
    )

    text = (
        "📊 *פאנל מפיץ אישי*\n\n"
        f"user_id: `{user_id}`\n\n"
        f"*נקודות שיתוף שצברת:* {points}\n\n"
        "*פרטי בנק למקבלי תשלום מההפניות שלך:*\n"
        f"{bank_text}\n\n"
        "*לינק הפניה אישי לבוט:*\n"
        f"{share_link}\n\n"
        "פקודות זמינות:\n"
        "/set_bank – הגדרת/עדכון פרטי בנק\n"
        "/share_board – צפייה בלוח השיתופים הכללי\n"
    )

    await update.effective_message.reply_text(text, parse_mode="Markdown")


# =========================
# help / admin menu
# =========================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message or update.effective_message
    if not message:
        return

    text = (
        "/start – פתיחת שער הקהילה\n"
        "/help – עזרה\n"
        "/my_panel – פאנל מפיץ אישי (למי שהצטרף)\n"
        "/share_board – לוח שיתופים ציבורי\n\n"
        "לאחר תשלום – שלח צילום מסך של האישור לבוט.\n\n"
        "למארגנים / אדמינים:\n"
        "/admin – תפריט אדמין\n"
        "/leaderboard – לוח מפנים\n"
        "/payments_stats – דוח תשלומים\n"
        "/reward_slh – יצירת Reward SLH\n"
        "/approve / /reject – ניהול תשלומים\n"
    )

    await message.reply_text(text)


async def admin_menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.effective_user.id not in ADMIN_IDS:
        await update.effective_message.reply_text(
            "אין לך הרשאה לתפריט אדמין.\n"
            "אם אתה צריך גישה – דבר עם המתכנת: @OsifEU"
        )
        return

    text = (
        "🛠 *תפריט אדמין – Buy My Shop*\n\n"
        "בחר אחת מהאפשרויות:\n"
        "• סטטוס מערכת (DB, Webhook, לינקים)\n"
        "• מוני תמונת שער\n"
        "• רעיונות לפיצ'רים עתידיים\n\n"
        "פקודות נוספות:\n"
        "/leaderboard – לוח מפנים\n"
        "/payments_stats – דוח תשלומים\n"
        "/reward_slh – יצירת Reward SLH\n"
    )

    await update.effective_message.reply_text(
        text, parse_mode="Markdown", reply_markup=admin_menu_keyboard()
    )


async def admin_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    admin = query.from_user

    if admin.id not in ADMIN_IDS:
        await query.answer(
            "אין לך הרשאה.\nאם אתה חושב שזו טעות – דבר עם @OsifEU",
            show_alert=True,
        )
        return

    data = query.data

    if data == "adm_status":
        views = get_metric("start_image_views") if DB_AVAILABLE else 0
        downloads = get_metric("start_image_downloads") if DB_AVAILABLE else 0
        text = (
            "📊 *סטטוס מערכת*\n\n"
            f"• DB: {'פעיל' if DB_AVAILABLE else 'כבוי'}\n"
            f"• Webhook URL: `{WEBHOOK_URL}`\n"
            f"• LANDING_URL: `{LANDING_URL}`\n"
            f"• PAYBOX_URL: `{PAYBOX_URL}`\n"
            f"• BIT_URL: `{BIT_URL}`\n"
            f"• PAYPAL_URL: `{PAYPAL_URL}`\n\n"
            "מוני תמונה (מה-DB):\n"
            f"• הצגות: {views}\n"
            f"• עותקים ממוספרים: {downloads}\n"
        )
        await query.message.edit_text(
            text, parse_mode="Markdown", reply_markup=admin_menu_keyboard()
        )

    elif data == "adm_counters":
        views = get_metric("start_image_views") if DB_AVAILABLE else 0
        downloads = get_metric("start_image_downloads") if DB_AVAILABLE else 0
        text = (
            "📈 *מוני תמונת שער*\n\n"
            f"• מספר הצגות (start): {views}\n"
            f"• עותקים ממוספרים שנשלחו אחרי אישור: {downloads}\n"
            "הנתונים נשמרים ב-DB ולא מתאפסים בהפעלה מחדש."
        )
        await query.message.edit_text(
            text, parse_mode="Markdown", reply_markup=admin_menu_keyboard()
        )

    elif data == "adm_ideas":
        text = (
            "💡 *רעיונות לפיצ'רים עתידיים לבוט*\n\n"
            "1. טבלת ניקוד דינמית באתר על בסיס API ציבורי.\n"
            "2. אינטגרציה מלאה ל-NFT/SLH.\n"
            "3. משימות יומיות עם נקודות ותוכן אוטומטי מבוט נוסף.\n"
            "4. Dashboard וובי מפורט לניתוח פעילות.\n"
        )
        await query.message.edit_text(
            text, parse_mode="Markdown", reply_markup=admin_menu_keyboard()
        )


# =========================
# register handlers
# =========================

ptb_app.add_handler(CommandHandler("start", start))
ptb_app.add_handler(CommandHandler("help", help_command))
ptb_app.add_handler(CommandHandler("admin", admin_menu_command))
ptb_app.add_handler(CommandHandler("approve", approve_command))
ptb_app.add_handler(CommandHandler("reject", reject_command))
ptb_app.add_handler(CommandHandler("leaderboard", admin_leaderboard_command))
ptb_app.add_handler(CommandHandler("payments_stats", admin_payments_stats_command))
ptb_app.add_handler(CommandHandler("reward_slh", admin_reward_slh_command))
ptb_app.add_handler(CommandHandler("set_bank", set_bank_command))
ptb_app.add_handler(CommandHandler("my_panel", my_panel_command))
ptb_app.add_handler(CommandHandler("share_board", share_board_command))

ptb_app.add_handler(CallbackQueryHandler(info_callback, pattern="^info$"))
ptb_app.add_handler(CallbackQueryHandler(join_callback, pattern="^join$"))
ptb_app.add_handler(CallbackQueryHandler(support_callback, pattern="^support$"))
ptb_app.add_handler(CallbackQueryHandler(share_callback, pattern="^share$"))
ptb_app.add_handler(CallbackQueryHandler(back_main_callback, pattern="^back_main$"))
ptb_app.add_handler(CallbackQueryHandler(payment_method_callback, pattern="^pay_"))
ptb_app.add_handler(
    CallbackQueryHandler(admin_menu_callback, pattern="^adm_(status|counters|ideas)$")
)
ptb_app.add_handler(CallbackQueryHandler(admin_approve_callback, pattern="^adm_approve:"))
ptb_app.add_handler(CallbackQueryHandler(admin_reject_callback, pattern="^adm_reject:"))

ptb_app.add_handler(
    MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, handle_payment_photo)
)
ptb_app.add_handler(
    MessageHandler(filters.TEXT & filters.ALL, admin_reject_reason_handler)
)


# =========================
# JobQueue – reminder
# =========================

async def remind_update_links(context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_start_image(context, PAYMENTS_LOG_CHAT_ID, mode="reminder")


# =========================
# FastAPI + webhook
# =========================

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Setting Telegram webhook to %s", WEBHOOK_URL)
    await ptb_app.bot.setWebhook(url=WEBHOOK_URL, allowed_updates=Update.ALL_TYPES)

    if DB_AVAILABLE:
        try:
            init_schema()
            logger.info("DB schema initialized.")
        except Exception as e:
            logger.error("Failed to init DB schema: %s", e)

    async with ptb_app:
        logger.info("Starting Telegram Application")
        await ptb_app.start()

        if ptb_app.job_queue:
            ptb_app.job_queue.run_repeating(
                remind_update_links,
                interval=6 * 24 * 60 * 60,
                first=6 * 24 * 60 * 60,
            )

        yield

        logger.info("Stopping Telegram Application")
        await ptb_app.stop()


app = FastAPI(lifespan=lifespan)

# לאפשר ל-GitHub Pages / דף המשחק למשוך את ה-API הציבורי
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/webhook")
async def telegram_webhook(request: Request) -> Response:
    data = await request.json()
    update = Update.de_json(data, ptb_app.bot)

    if is_duplicate_update(update):
        logger.warning("Duplicate update_id=%s – ignoring", update.update_id)
        return Response(status_code=HTTPStatus.OK.value)

    await ptb_app.process_update(update)
    return Response(status_code=HTTPStatus.OK.value)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "telegram-gateway-community-bot",
        "db": "enabled" if DB_AVAILABLE else "disabled",
    }


@app.get("/admin/stats")
async def admin_stats(token: str = ""):
    if not ADMIN_DASH_TOKEN or token != ADMIN_DASH_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if not DB_AVAILABLE:
        return {"db": "disabled"}

    try:
        stats = get_approval_stats()
        monthly = get_monthly_payments(datetime.utcnow().year, datetime.utcnow().month)
        top_ref = get_top_referrers(5)
        top_share = get_top_sharers(5)
    except Exception as e:
        logger.error("Failed to get admin stats: %s", e)
        raise HTTPException(status_code=500, detail="DB error")

    return {
        "db": "enabled",
        "payments_stats": stats,
        "monthly_breakdown": monthly,
        "top_referrers": top_ref,
        "top_sharers": top_share,
    }


@app.get("/public/share_board")
async def public_share_board():
    """
    API ציבורי לטבלת השיתופים.
    מחזיר JSON: { items: [ {user_id, username, points}, ... ] }
    """
    if not DB_AVAILABLE:
        return {"items": []}

    try:
        rows = get_top_sharers(50)
    except Exception as e:
        logger.error("Failed to get public share board: %s", e)
        raise HTTPException(status_code=500, detail="DB error")

    items = []
    for row in rows:
        items.append(
            {
                "user_id": row["user_id"],
                "username": row["username"],
                "points": row["total_points"],
            }
        )

    return {"items": items}
