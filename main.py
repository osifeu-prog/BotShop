# main.py
import os
import logging
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime
from http import HTTPStatus
from typing import Deque, Set, Literal, Optional, Dict, Any, List
from fastapi.responses import FileResponse, HTMLResponse
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

# =========================
# לוגינג בסיסי
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("gateway-bot")

# =========================
# DB אופציונלי (db.py)
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
        ensure_promoter,
        update_promoter_settings,
        get_promoter_summary,
        incr_metric,
        get_metric,
    )
    DB_AVAILABLE = True
    logger.info("DB module loaded successfully, DB logging enabled.")
except Exception as e:
    logger.warning("DB not available (missing db.py or error loading it): %s", e)
    DB_AVAILABLE = False

# =========================
# משתני סביבה חיוניים
# =========================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
BOT_USERNAME = os.environ.get("BOT_USERNAME")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is not set")

if not WEBHOOK_URL:
    raise RuntimeError("WEBHOOK_URL environment variable is not set")

logger.info("Starting bot with WEBHOOK_URL=%s", WEBHOOK_URL)

# =========================
# קבועים של המערכת
# =========================
COMMUNITY_GROUP_LINK = os.environ.get("COMMUNITY_GROUP_LINK", "https://t.me/+HIzvM8sEgh1kNWY0")
SUPPORT_GROUP_LINK = os.environ.get("SUPPORT_GROUP_LINK", "https://t.me/+1ANn25HeVBoxNmRk")
DEVELOPER_USER_ID = 224223270
PAYMENTS_LOG_CHAT_ID = -1001748319682

def build_personal_share_link(user_id: int) -> str:
    base_username = BOT_USERNAME or "Buy_My_Shop_bot"
    return f"https://t.me/{base_username}?start=ref_{user_id}"

# לינקי תשלום
PAYBOX_URL = os.environ.get("PAYBOX_URL", "https://links.payboxapp.com/1SNfaJ6XcYb")
BIT_URL = os.environ.get("BIT_URL", "https://www.bitpay.co.il/app/share-info?i=190693822888_19l4oyvE")
PAYPAL_URL = os.environ.get("PAYPAL_URL", "https://paypal.me/osifdu")
LANDING_URL = os.environ.get("LANDING_URL", "https://osifeu-prog.github.io/botshop/")
ADMIN_DASH_TOKEN = os.environ.get("ADMIN_DASH_TOKEN")
START_IMAGE_PATH = os.environ.get("START_IMAGE_PATH", "assets/start_banner.jpg")

# פרטי תשלום
BANK_DETAILS = (
    "🏦 *תשלום בהעברה בנקאית*\n\n"
    "בנק הפועלים\n"
    "סניף כפר גנים (153)\n"
    "חשבון 73462\n"
    "המוטב: קאופמן צביקה\n\n"
    "סכום: *39 ש\"ח*\n"
)

ADMIN_IDS = {DEVELOPER_USER_ID}
PayMethod = Literal["bank", "paybox", "ton"]

# =========================
# Dedup – מניעת כפילות
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
# זיכרון פשוט לתשלומים
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

# =========================
# אפליקציית Telegram
# =========================
ptb_app: Application = (
    Application.builder()
    .updater(None)
    .token(BOT_TOKEN)
    .build()
)

# =========================
# עזרי UI (מקשים)
# =========================

def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🚀 הצטרפות לקהילת העסקים (39 ₪)", callback_data="join"),
        ],
        [
            InlineKeyboardButton("💎 מה זה הנכס הדיגיטלי?", callback_data="digital_asset_info"),
        ],
        [
            InlineKeyboardButton("🔗 שתף את שער הקהילה", callback_data="share"),
        ],
        [
            InlineKeyboardButton("👤 האזור האישי שלי", callback_data="my_area"),
        ],
        [
            InlineKeyboardButton("🆘 תמיכה", callback_data="support"),
        ],
    ])

def payment_methods_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🏦 העברה בנקאית", callback_data="pay_bank"),
        ],
        [
            InlineKeyboardButton("📲 ביט / פייבוקס / PayPal", callback_data="pay_paybox"),
        ],
        [
            InlineKeyboardButton("💎 טלגרם (TON)", callback_data="pay_ton"),
        ],
        [
            InlineKeyboardButton("⬅ חזרה", callback_data="back_main"),
        ],
    ])

def payment_links_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("📲 תשלום בפייבוקס", url=PAYBOX_URL)],
        [InlineKeyboardButton("📲 תשלום בביט", url=BIT_URL)],
        [InlineKeyboardButton("💳 תשלום ב-PayPal", url=PAYPAL_URL)],
        [InlineKeyboardButton("⬅ חזרה", callback_data="back_main")],
    ]
    return InlineKeyboardMarkup(buttons)

def my_area_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🏦 הגדר פרטי בנק", callback_data="set_bank"),
        ],
        [
            InlineKeyboardButton("👥 הגדר קבוצות", callback_data="set_groups"),
        ],
        [
            InlineKeyboardButton("📊 הצג נכס דיגיטלי", callback_data="show_asset"),
        ],
        [
            InlineKeyboardButton("⬅ חזרה", callback_data="back_main"),
        ],
    ])

def support_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("קבוצת תמיכה", url=SUPPORT_GROUP_LINK),
        ],
        [
            InlineKeyboardButton("פניה למתכנת", url=f"tg://user?id={DEVELOPER_USER_ID}"),
        ],
        [
            InlineKeyboardButton("⬅ חזרה", callback_data="back_main"),
        ],
    ])

def admin_approval_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ אשר תשלום", callback_data=f"adm_approve:{user_id}"),
            InlineKeyboardButton("❌ דחה תשלום", callback_data=f"adm_reject:{user_id}"),
        ],
    ])

# =========================
# Handlers – לוגיקת הבוט
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message or update.effective_message
    if not message:
        return

    user = update.effective_user

    # לוג ל-DB ולקבוצת הלוגים
    if DB_AVAILABLE and user:
        try:
            store_user(user.id, user.username)
            incr_metric("total_starts")
        except Exception as e:
            logger.error("Failed to store user: %s", e)

    # טיפול ב-referral
    if message.text and message.text.startswith("/start") and user:
        parts = message.text.split()
        if len(parts) > 1 and parts[1].startswith("ref_"):
            try:
                referrer_id = int(parts[1].split("ref_")[1])
                if DB_AVAILABLE and referrer_id != user.id:
                    add_referral(referrer_id, user.id, source="bot_start")
                    logger.info("Referral added: %s -> %s", referrer_id, user.id)
            except Exception as e:
                logger.error("Failed to add referral: %s", e)

    # לוג לקבוצת התשלומים
    if PAYMENTS_LOG_CHAT_ID and update.effective_user:
        try:
            user = update.effective_user
            username_str = f"@{user.username}" if user.username else "(ללא username)"
            log_text = (
                "🚀 *הפעלת בוט חדשה - Buy_My_Shop*\n\n"
                f"👤 user_id: `{user.id}`\n"
                f"📛 username: {username_str}\n"
                f"💬 chat_id: `{update.effective_chat.id}`\n"
                f"🕐 זמן: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            )
            await context.bot.send_message(
                chat_id=PAYMENTS_LOG_CHAT_ID,
                text=log_text,
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error("Failed to send /start log to payments group: %s", e)

    # שליחת הודעת ברוכים הבאים
    text = (
        "🎉 *ברוך הבא לנכס הדיגיטלי המניב שלך!*\n\n"
        
        "💎 *מה זה הנכס הדיגיטלי?*\n"
        "זהו שער כניסה אישי לקהילת עסקים פעילה. לאחר רכישה תקבל:\n"
        "• לינק אישי להפצה\n"
        "• אפשרות למכור את הנכס הלאה\n"
        "• גישה לקבוצת משחק כללית\n"
        "• מערכת הפניות מתגמלת\n\n"
        
        "🔄 *איך זה עובד?*\n"
        "1. רוכשים נכס ב-39₪\n"
        "2. מקבלים לינק אישי\n"
        "3. מפיצים - כל רכישה דרך הלינק שלך מתועדת\n"
        "4. מרוויחים מהפצות נוספות\n\n"
        
        "🚀 *מה תקבל?*\n"
        "✅ גישה לקהילת עסקים\n"
        "✅ נכס דיגיטלי אישי\n"
        "✅ לינק הפצה ייחודי\n"
        "✅ אפשרות מכירה חוזרת\n"
        "✅ מערכת הפניות שקופה\n\n"
        
        "💼 *הנכס שלך - העסק שלך!*"
    )

    await message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )

async def digital_asset_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    text = (
        "💎 *הנכס הדיגיטלי - ההזדמנות העסקית שלך!*\n\n"
        
        "🏗 *מה זה בעצם?*\n"
        "נכס דיגיטלי הוא 'שער כניסה' אישי שאתה קונה פעם אחת ב-39₪ ומקבל:\n"
        "• לינק אישי משלך\n"
        "• זכות למכור נכסים נוספים\n"
        "• גישה למערכת שלמה\n\n"
        
        "💸 *איך מרוויחים?*\n"
        "1. אתה רוכש נכס ב-39₪\n"
        "2. מקבל לינק אישי להפצה\n"
        "3 *כל אדם* שקונה דרך הלינק שלך - הרכישה מתועדת לזכותך\n"
        "4. הנכס שלך ממשיך להניב הכנסות\n\n"
        
        "🔄 *מודל מכירה חוזרת:*\n"
        "אתה לא רק 'משתמש' - אתה 'בעל נכס'!\n"
        "יכול למכור נכסים נוספים לאחרים\n"
        "כל רכישה נוספת מתועדת בשרשרת ההפניה\n\n"
        
        "📈 *יתרונות:*\n"
        "• הכנסה פסיבית מהפצות\n"
        "• נכס ששווה יותר עם הזמן\n"
        "• קהילה תומכת\n"
        "• שקיפות מלאה\n\n"
        
        "🎯 *המטרה:* ליצור רשת עסקית where everyone wins!"
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )

async def join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    text = (
        "🔑 *רכישת הנכס הדיגיטלי - 39₪*\n\n"
        "בתמורה ל-39₪ תקבל:\n"
        "• נכס דיגיטלי אישי\n"
        "• לינק הפצה ייחודי\n"
        "• גישה לקהילת עסקים\n"
        "• אפשרות למכור נכסים נוספים\n\n"
        
        "🔄 *איך התהליך עובד?*\n"
        "1. בוחרים אמצעי תשלום\n"
        "2. משלמים 39₪\n"
        "3. שולחים אישור תשלום\n"
        "4. מקבלים אישור + לינק אישי\n"
        "5. מתחילים להפיץ!\n\n"
        
        "💼 *זכור:* אתה קונה *נכס* - לא רק 'גישה'!"
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=payment_methods_keyboard(),
    )

async def my_area_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    if not user:
        return

    if DB_AVAILABLE:
        summary = get_promoter_summary(user.id)
        if summary:
            personal_link = build_personal_share_link(user.id)
            bank = summary.get("bank_details") or "לא הוגדר"
            p_group = summary.get("personal_group_link") or "לא הוגדר"
            total_ref = summary.get("total_referrals", 0)
            
            text = (
                "👤 *האזור האישי שלך*\n\n"
                f"🔗 *לינק אישי:*\n`{personal_link}`\n\n"
                f"🏦 *פרטי בנק:*\n{bank}\n\n"
                f"👥 *קבוצה אישית:*\n{p_group}\n\n"
                f"📊 *הפניות:* {total_ref}\n\n"
                "*ניהול נכס:*"
            )
        else:
            text = (
                "👤 *האזור האישי שלך*\n\n"
                "עדיין אין לך נכס דיגיטלי.\n"
                "רכש נכס כדי לקבל:\n"
                "• לינק אישי להפצה\n"
                "• אפשרות למכור נכסים\n"
                "• גישה למערכת המלאה"
            )
    else:
        text = "מערכת הזמנית לא זמינת. נסה שוב מאוחר יותר."

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=my_area_keyboard(),
    )

async def set_bank_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    text = (
        "🏦 *הגדרת פרטי בנק*\n\n"
        "לאחר אישור התשלום, תוכל להגדיר כאן את פרטי הבנק שלך.\n"
        "פרטים אלה ישמשו לקבלת תשלומים מהפצות שלך.\n\n"
        "*פורמט מומלץ:*\n"
        "בנק XXX, סניף XXX, חשבון XXX, שם המוטב"
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=my_area_keyboard(),
    )

async def set_groups_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    text = (
        "👥 *הגדרת קבוצות*\n\n"
        "כבעל נכס דיגיטלי, תוכל להגדיר:\n"
        "• קבוצה אישית ללקוחות שלך\n"
        "• קבוצת משחק/קהילה\n\n"
        "הקבוצות יוצגו בנכס הדיגיטלי שלך."
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=my_area_keyboard(),
    )

async def payment_method_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data

    method_text = ""
    if data == "pay_bank":
        method_text = BANK_DETAILS
    elif data == "pay_paybox":
        method_text = "📲 *תשלום בביט / פייבוקס / PayPal*"
    elif data == "pay_ton":
        method_text = "💎 *תשלום ב-TON*"

    text = (
        f"{method_text}\n\n"
        "💎 *לאחר התשלום:*\n"
        "1. שלח צילום מסך של האישור\n"
        "2. נאשר בתוך זמן קצר\n"
        "3. תקבל את הנכס הדיגיטלי שלך\n"
        "4. תוכל להתחיל להפיץ ולהרוויח!\n\n"
        "*זכור:* אתה רוכש *נכס* - לא רק גישה!"
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=payment_links_keyboard(),
    )

async def handle_payment_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message or not message.photo:
        return

    user = update.effective_user
    chat_id = message.chat_id
    username = f"@{user.username}" if user and user.username else "(ללא username)"

    pay_method = context.user_data.get("last_pay_method", "unknown")
    pay_method_text = {
        "bank": "העברה בנקאית",
        "paybox": "ביט / פייבוקס / PayPal",
        "ton": "טלגרם (TON)",
        "unknown": "לא ידוע",
    }.get(pay_method, "לא ידוע")

    # לוג ל-DB
    if DB_AVAILABLE:
        try:
            log_payment(user.id, username, pay_method_text)
        except Exception as e:
            logger.error("Failed to log payment to DB: %s", e)

    # שליחת אישור לקבוצת הלוגים
    photo = message.photo[-1]
    file_id = photo.file_id

    payments = get_payments_store(context)
    payments[user.id] = {
        "file_id": file_id,
        "pay_method": pay_method_text,
        "username": username,
        "chat_id": chat_id,
    }

    caption_log = (
        "💰 *אישור תשלום חדש התקבל!*\n\n"
        f"👤 user_id: `{user.id}`\n"
        f"📛 username: {username}\n"
        f"💳 שיטת תשלום: {pay_method_text}\n"
        f"🕐 זמן: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        "*פעולות:*"
    )

    try:
        await context.bot.send_photo(
            chat_id=PAYMENTS_LOG_CHAT_ID,
            photo=file_id,
            caption=caption_log,
            parse_mode="Markdown",
            reply_markup=admin_approval_keyboard(user.id),
        )
    except Exception as e:
        logger.error("Failed to send payment to log group: %s", e)

    await message.reply_text(
        "✅ *אישור התשלום התקבל!*\n\n"
        "האישור נשלח לצוות שלנו לאימות.\n"
        "תקבל הודעה עם הנכס הדיגיטלי שלך בתוך זמן קצר.\n\n"
        "💎 *מה תקבל לאחר אישור:*\n"
        "• לינק אישי להפצה\n"
        "• גישה לקהילה\n"
        "• אפשרות למכור נכסים נוספים",
        parse_mode="Markdown",
    )

async def do_approve(target_id: int, context: ContextTypes.DEFAULT_TYPE, source_message) -> None:
    personal_link = build_personal_share_link(target_id)
    
    # הודעת אישור למשתמש
    approval_text = (
        "🎉 *התשלום אושר! ברוך הבא לבעלי הנכסים!*\n\n"
        
        "💎 *הנכס הדיגיטלי שלך מוכן:*\n"
        f"🔗 *לינק אישי:* `{personal_link}`\n\n"
        
        "🚀 *מה עכשיו?*\n"
        "1. שתף את הלינק עם אחרים\n"
        "2. כל רכישה דרך הלינק שלך מתועדת\n"
        "3. תוכל למכור נכסים נוספים\n"
        "4. צבור הכנסה מהפצות\n\n"
        
        "👥 *גישה לקהילה:*\n"
        f"{COMMUNITY_GROUP_LINK}\n\n"
        
        "💼 *ניהול הנכס:*\n"
        "השתמש בכפתור '👤 האזור האישי שלי'\n"
        "כדי להגדיר פרטי בנק וקבוצות"
    )

    try:
        await context.bot.send_message(chat_id=target_id, text=approval_text, parse_mode="Markdown")
        
        # עדכון DB
        if DB_AVAILABLE:
            try:
                update_payment_status(target_id, "approved", None)
                ensure_promoter(target_id)
                incr_metric("approved_payments")
            except Exception as e:
                logger.error("Failed to update DB: %s", e)

        if source_message:
            await source_message.reply_text(f"✅ אושר למשתמש {target_id} - נשלח נכס דיגיטלי")
            
    except Exception as e:
        logger.error("Failed to send approval: %s", e)

async def do_reject(target_id: int, reason: str, context: ContextTypes.DEFAULT_TYPE, source_message) -> None:
    rejection_text = (
        "❌ *אישור התשלום נדחה*\n\n"
        f"*סיבה:* {reason}\n\n"
        "אם לדעתך מדובר בטעות, פנה לתמיכה."
    )
    
    try:
        await context.bot.send_message(chat_id=target_id, text=rejection_text, parse_mode="Markdown")
        
        if DB_AVAILABLE:
            try:
                update_payment_status(target_id, "rejected", reason)
            except Exception as e:
                logger.error("Failed to update DB: %s", e)
                
        if source_message:
            await source_message.reply_text(f"❌ נדחה למשתמש {target_id}")
            
    except Exception as e:
        logger.error("Failed to send rejection: %s", e)

# =========================
# Admin handlers
# =========================

async def admin_approve_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    admin = query.from_user

    if admin.id not in ADMIN_IDS:
        await query.answer("אין הרשאה", show_alert=True)
        return

    data = query.data or ""
    try:
        _, user_id_str = data.split(":", 1)
        target_id = int(user_id_str)
    except Exception:
        await query.answer("שגיאה", show_alert=True)
        return

    await do_approve(target_id, context, query.message)

async def admin_reject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    admin = query.from_user

    if admin.id not in ADMIN_IDS:
        await query.answer("אין הרשאה", show_alert=True)
        return

    data = query.data or ""
    try:
        _, user_id_str = data.split(":", 1)
        target_id = int(user_id_str)
    except Exception:
        await query.answer("שגיאה", show_alert=True)
        return

    pending = get_pending_rejects(context)
    pending[admin.id] = target_id

    await query.message.reply_text(
        f"❌ דחייה למשתמש {target_id}\nשלח סיבה:"
    )

async def admin_reject_reason_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None or user.id not in ADMIN_IDS:
        return

    pending = get_pending_rejects(context)
    if user.id not in pending:
        return

    target_id = pending.pop(user.id)
    reason = update.message.text.strip()
    await do_reject(target_id, reason, context, update.effective_message)

# =========================
# Back handlers
# =========================

async def back_main_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    fake_update = Update(update_id=update.update_id, message=query.message)
    await start(fake_update, context)

async def support_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🆘 *תמיכה*
