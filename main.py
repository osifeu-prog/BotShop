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
        increment_metric,
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
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")  # חייב לכלול /webhook בסוף

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is not set")

if not WEBHOOK_URL:
    raise RuntimeError("WEBHOOK_URL environment variable is not set")

logger.info("Starting bot with WEBHOOK_URL=%s", WEBHOOK_URL)

# =========================
# קבועים של המערכת שלך
# =========================

# קבוצת הקהילה (אחרי אישור תשלום)
COMMUNITY_GROUP_LINK = "https://t.me/+HIzvM8sEgh1kNWY0"
COMMUNITY_GROUP_ID = -1002981609404  # לא חובה לשימוש כרגע

# קבוצת תמיכה
SUPPORT_GROUP_LINK = "https://t.me/+1ANn25HeVBoxNmRk"
SUPPORT_GROUP_ID = -1001651506661  # כרגע רק לינק

# מתכנת המערכת (אתה)
DEVELOPER_USER_ID = 224223270

# קבוצת לוגים ותשלומים (רק למארגנים, לא יוצג למשתמש)
PAYMENTS_LOG_CHAT_ID = -1001748319682

# לינקי תשלום (מה-ENV עם ברירת מחדל)
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

# לינק לדף הנחיתה (GitHub Pages) – בשביל כפתור השיתוף
LANDING_URL = os.environ.get(
    "LANDING_URL",
    "https://osifeu-prog.github.io/botshop/",
)

# Token קטן לדשבורד API (/admin/stats)
ADMIN_DASH_TOKEN = os.environ.get("ADMIN_DASH_TOKEN")

# נתיב התמונה הראשית של /start
START_IMAGE_PATH = os.environ.get(
    "START_IMAGE_PATH",
    "assets/start_banner.jpg",  # תוודא שהתמונה הזו קיימת בפרויקט
)

# פרטי תשלום
BANK_DETAILS = (
    "🏦 *תשלום בהעברה בנקאית*\n\n"
    "בנק הפועלים\n"
    "סניף כפר גנים (153)\n"
    "חשבון 73462\n"
    "המוטב: קאופמן צביקה\n\n"
    "סכום: *39 ש\"ח*\n"
)

PAYBOX_DETAILS = (
    "📲 *תשלום בביט / פייבוקס / PayPal*\n\n"
    "אפשר לשלם דרך האפליקציות שלך בביט או פייבוקס.\n"
    "קישורי התשלום המעודכנים מופיעים בכפתורים למטה.\n\n"
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

# אדמינים שיכולים לאשר / לדחות תשלום
ADMIN_IDS = {DEVELOPER_USER_ID}  # אפשר להוסיף עוד IDs אם תרצה

PayMethod = Literal["bank", "paybox", "ton"]

# =========================
# Dedup – מניעת כפילות תגובות
# =========================
_processed_ids: Deque[int] = deque(maxlen=1000)
_processed_set: Set[int] = set()

def is_duplicate_update(update: Update) -> bool:
    """בודק אם update כבר טופל (ע״פ update_id)"""
    if update is None:
        return False
    uid = update.update_id
    if uid in _processed_set:
        return True
    _processed_set.add(uid)
    _processed_ids.append(uid)
    # ניקוי סט לפי ה-deque
    if len(_processed_set) > len(_processed_ids) + 10:
        valid = set(_processed_ids)
        _processed_set.intersection_update(valid)
    return False

# =========================
# זיכרון פשוט לתשלומים אחרונים + דחיות ממתינות
# =========================
# bot_data["payments"][user_id] => dict עם פרטי העסקה האחרונה
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
# אפליקציית Telegram
# =========================
ptb_app: Application = (
    Application.builder()
    .updater(None)  # אין polling – רק webhook
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
            InlineKeyboardButton("ℹ מה אני מקבל?", callback_data="info"),
        ],
        [
            InlineKeyboardButton("🔗 שתף את שער הקהילה", callback_data="share"),
        ],
        [
            InlineKeyboardButton("🆘 תמיכה", callback_data="support"),
        ],
    ])

def payment_methods_keyboard() -> InlineKeyboardMarkup:
    """בחירת סוג תשלום (לוגי – לא לינקים)"""
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
            InlineKeyboardButton("⬅ חזרה לתפריט ראשי", callback_data="back_main"),
        ],
    ])

def payment_links_keyboard() -> InlineKeyboardMarkup:
    """כפתורי לינקים אמיתיים לתשלום"""
    buttons = [
        [InlineKeyboardButton("📲 תשלום בפייבוקס", url=PAYBOX_URL)],
        [InlineKeyboardButton("📲 תשלום בביט", url=BIT_URL)],
        [InlineKeyboardButton("💳 תשלום ב-PayPal", url=PAYPAL_URL)],
        [InlineKeyboardButton("⬅ חזרה לתפריט ראשי", callback_data="back_main")],
    ]
    return InlineKeyboardMarkup(buttons)

def support_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("קבוצת תמיכה", url=SUPPORT_GROUP_LINK),
        ],
        [
            InlineKeyboardButton("פניה למתכנת המערכת", url=f"tg://user?id={DEVELOPER_USER_ID}"),
        ],
        [
            InlineKeyboardButton("⬅ חזרה לתפריט ראשי", callback_data="back_main"),
        ],
    ])

def admin_approval_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """כפתורי אישור/דחייה ללוגים"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ אשר תשלום", callback_data=f"adm_approve:{user_id}"),
            InlineKeyboardButton("❌ דחה תשלום", callback_data=f"adm_reject:{user_id}"),
        ],
    ])

def admin_menu_keyboard() -> InlineKeyboardMarkup:
    """תפריט אדמין"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 סטטוס מערכת", callback_data="adm_status"),
        ],
        [
            InlineKeyboardButton("📈 מוני תמונה", callback_data="adm_counters"),
        ],
        [
            InlineKeyboardButton("💡 רעיונות לפיצ'רים", callback_data="adm_ideas"),
        ],
    ])

# =========================
# עוזר: שליחת תמונת ה-START עם מונים
# =========================

async def send_start_image(context: ContextTypes.DEFAULT_TYPE, chat_id: int, mode: str = "view") -> None:
    """
    mode:
      - "view": הצגה ב-/start, מעלה מונה צפיות
      - "download": עותק ממוספר למשתמש אחרי אישור תשלום
      - "reminder": תזכורת בקבוצת לוגים – בלי לשנות מונים
    """
    app_data = context.application.bot_data

    views = app_data.get("start_image_views", 0)
    downloads = app_data.get("start_image_downloads", 0)

    caption = ""
    if mode == "view":
        views += 1
        app_data["start_image_views"] = views
        caption = (
            f"🌐 שער הכניסה לקהילת העסקים\n"
            f"מספר הצגה כולל: *{views}*\n"
        )
    elif mode == "download":
        downloads += 1
        app_data["start_image_downloads"] = downloads
        caption = (
            "🎁 זה העותק הממוספר שלך של שער הקהילה.\n"
            f"מספר סידורי לעותק: *#{downloads}*\n"
        )
    elif mode == "reminder":
        caption = (
            "⏰ תזכורת: בדוק שהלינקים של PayBox / Bit / PayPal עדיין תקפים.\n\n"
            f"מצב מונים כרגע:\n"
            f"• הצגות תמונה: {views}\n"
            f"• עותקים ממוספרים שנשלחו: {downloads}\n"
        )

    try:
        with open(START_IMAGE_PATH, "rb") as f:
            if DB_AVAILABLE:
        try:
            if mode == "view":
                increment_metric("start_image_views", 1)
            elif mode == "download":
                increment_metric("start_image_downloads", 1)
        except Exception as e:
            logger.error("Failed to increment metrics: %s", e)
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
# Handlers – לוגיקת הבוט
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """תשובת /start – שער הכניסה לקהילה + הפניות (referrals)"""
    message = update.message or update.effective_message
    if not message:
        return

    user = update.effective_user

    # 1. שומרים משתמש ב-DB (אם אפשר)
    if DB_AVAILABLE and user:
        try:
            store_user(user.id, user.username)
        except Exception as e:
            logger.error("Failed to store user: %s", e)

    # 2. טיפול ב-deep link: /start ref_<referrer_id>
    if message.text and message.text.startswith("/start") and user:
        parts = message.text.split()
        if len(parts) > 1 and parts[1].startswith("ref_"):
            try:
                referrer_id = int(parts[1].split("ref_")[1])
                if DB_AVAILABLE and referrer_id != user.id:
                    add_referral(referrer_id, user.id, source="bot_start")
            except Exception as e:
                logger.error("Failed to add referral: %s", e)

    # 3. תמונה ממוספרת
    await send_start_image(context, message.chat_id, mode="view")

    # 4. טקסט ותפריט
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
        "✅ מנגנון ניקוד למי שמביא חברים – שיוצג בקהילה\n\n"
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
    """מידע על ההטבות"""
    query = update.callback_query
    await query.answer()

    text = (
        "ℹ *מה מקבלים בקהילה?*\n\n"
        "🚀 גישה לקבוצת עסקים סגורה שבה משתפים רעיונות, שיתופי פעולה והזדמנויות.\n"
        "📚 הדרכות על שיווק רשתי, בניית קהילה, מכירות אונליין ונכסים דיגיטליים.\n"
        "🎁 מתנות דיגיטליות, NFT והטבות שיחולקו בתוך הקהילה.\n"
        "💎 בעתיד הקרוב – חלוקת טוקני *SLH* על פעילות, שיתופים והפניות.\n"
        "🏆 מנגנון ניקוד למי שמביא חברים – שיוצג בקבוצה ויקבל עדיפות במבצעים.\n\n"
        "דמי הצטרפות חד־פעמיים: *39 ש\"ח*.\n\n"
        "כדי להצטרף – בחר אמצעי תשלום:"
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=payment_methods_keyboard(),
    )

async def join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """לחיצה על 'הצטרפות לקהילה'"""
    query = update.callback_query
    await query.answer()

    text = (
        "🔑 *הצטרפות לקהילת העסקים – 39 ש\"ח*\n\n"
        "בחר את אמצעי התשלום המתאים לך:\n"
        "• העברה בנקאית\n"
        "• ביט / פייבוקס / PayPal\n"
        "• טלגרם (TON)\n\n"
        "לאחר ביצוע התשלום:\n"
        "1. שלח כאן *צילום מסך או תמונה* של אישור התשלום.\n"
        "2. הבוט יעביר את האישור למארגנים לבדיקה.\n"
        "3. לאחר אישור ידני תקבל קישור לקהילת העסקים.\n\n"
        "שימו לב: *אין קישור לקהילה לפני אישור תשלום.*"
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=payment_methods_keyboard(),
    )

async def support_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """מסך תמיכה"""
    query = update.callback_query
    await query.answer()

    text = (
        "🆘 *תמיכה ועזרה*\n\n"
        "בכל שלב אפשר לקבל עזרה באחד הערוצים הבאים:\n\n"
        f"• קבוצת תמיכה: {SUPPORT_GROUP_LINK}\n"
        f"• פניה ישירה למתכנת המערכת: `tg://user?id={DEVELOPER_USER_ID}`\n\n"
        "או חזור לתפריט הראשי:"
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=support_keyboard(),
    )

async def share_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """כפתור 'שתף את שער הקהילה' – שולח למשתמש את הלינק לדף הנחיתה"""
    query = update.callback_query
    await query.answer()

    text = (
        "🔗 *שתף את שער הקהילה*\n\n"
        "כדי להזמין חברים לקהילה, אפשר לשלוח להם את הקישור הבא:\n"
        f"{LANDING_URL}\n\n"
        "מומלץ לשתף בסטורי / סטטוס / קבוצות, ולהוסיף כמה מילים אישיות משלך.\n"
        "כל מי שייכנס דרך הלינק וילחץ על Start בבוט – יעבור דרך שער הקהילה."
    )

    await query.message.reply_text(
        text,
        parse_mode="Markdown",
    )

async def back_main_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """חזרה לתפריט ראשי"""
    query = update.callback_query
    await query.answer()
    fake_update = Update(update_id=update.update_id, message=query.message)
    await start(fake_update, context)

async def payment_method_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """בחירת אמצעי תשלום"""
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
        "לאחר ביצוע התשלום:\n"
        "1. שלח כאן *צילום מסך או תמונה* של אישור התשלום.\n"
        "2. הבוט יעביר את האישור למארגנים לבדיקה.\n"
        "3. לאחר אישור ידני תקבל קישור לקהילת העסקים.\n"
    )

    # כאן מופיעים הכפתורים האמיתיים של התשלום
    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=payment_links_keyboard(),
    )

# =========================
# לוגיקת תשלום + DB + לוגים
# =========================

async def handle_payment_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    צילום שמגיע מהמשתמש – נניח שזה אישור תשלום:
    1. ננסה להעביר לקבוצת הלוגים PAYMENTS_LOG_CHAT_ID
    2. נשמור פרטי תשלום אחרון במבנה בזיכרון
    3. אם הלוגים נכשלים – נשלח אליך (DEVELOPER_USER_ID) הודעה
    4. מחזירים למשתמש הודעת 'בבדיקה'
    5. אם DB זמין – רושמים רשומת 'pending' בטבלה
    """
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

    caption_log = (
        "📥 התקבל אישור תשלום חדש.\n\n"
        f"user_id = {user.id}\n"
        f"username = {username}\n"
        f"from chat_id = {chat_id}\n"
        f"שיטת תשלום: {pay_method_text}\n\n"
        "לאישור:\n"
        f"/approve {user.id}\n"
        f"/reject {user.id} <סיבה>\n"
        "(או להשתמש בכפתורי האישור/דחייה מתחת להודעה זו)\n"
    )

    # ניקח את התמונה הגדולה ביותר
    photo = message.photo[-1]
    file_id = photo.file_id

    # נשמור בזיכרון את פרטי התשלום האחרון של המשתמש
    payments = get_payments_store(context)
    payments[user.id] = {
        "file_id": file_id,
        "pay_method": pay_method_text,
        "username": username,
        "chat_id": chat_id,
    }

    # לוג ל-DB (אופציונלי)
    if DB_AVAILABLE:
        try:
            log_payment(user.id, username, pay_method_text)
        except Exception as e:
            logger.error("Failed to log payment to DB: %s", e)

    # ננסה לשלוח לקבוצת לוגים
    try:
        if DB_AVAILABLE:
        try:
            if mode == "view":
                increment_metric("start_image_views", 1)
            elif mode == "download":
                increment_metric("start_image_downloads", 1)
        except Exception as e:
            logger.error("Failed to increment metrics: %s", e)
    await context.bot.send_photo(
            chat_id=PAYMENTS_LOG_CHAT_ID,
            photo=file_id,
            caption=caption_log,
            reply_markup=admin_approval_keyboard(user.id),
        )
    except Exception as e:
        logger.error("Failed to forward payment photo to log group: %s", e)
        # גיבוי: נשלח אליך בפרטי
        try:
            if DB_AVAILABLE:
        try:
            if mode == "view":
                increment_metric("start_image_views", 1)
            elif mode == "download":
                increment_metric("start_image_downloads", 1)
        except Exception as e:
            logger.error("Failed to increment metrics: %s", e)
    await context.bot.send_photo(
                chat_id=DEVELOPER_USER_ID,
                photo=file_id,
                caption="(Fallback – לא הצלחתי לשלוח לקבוצת לוגים)\n\n" + caption_log,
                reply_markup=admin_approval_keyboard(user.id),
            )
        except Exception as e2:
            logger.error("Failed to send fallback payment to developer: %s", e2)

    await message.reply_text(
        "תודה! אישור התשלום התקבל ונשלח לבדיקה ✅\n"
        "לאחר אישור ידני תקבל ממני קישור להצטרפות לקהילת העסקים.\n\n"
        "אם יש שאלה דחופה – אפשר לפנות גם לקבוצת התמיכה.",
        reply_markup=support_keyboard(),
    )

# =========================
# עוזרים לאישור/דחייה – משותף לכפתורים ולפקודות
# =========================

async def do_approve(target_id: int, context: ContextTypes.DEFAULT_TYPE, source_message) -> None:
    """לוגיקת אישור תשלום – משותפת ל-/approve ולכפתור"""
    text = (
        "✅ התשלום שלך אושר!\n\n"
        "ברוך הבא לקהילת העסקים שלנו 🎉\n"
        "הנה הקישור להצטרפות לקהילה:\n"
        f"{COMMUNITY_GROUP_LINK}\n\n"
        "וכמו שהבטחנו – קבל את העותק הממוספר שלך של שער הקהילה בהודעה נפרדת 🎁\n"
        "ניפגש בפנים 🙌"
    )
    try:
        await context.bot.send_message(chat_id=target_id, text=text)
        # שליחת העותק הממוספר של התמונה
        await send_start_image(context, target_id, mode="download")

        # עדכון סטטוס ב-DB
        if DB_AVAILABLE:
            try:
                update_payment_status(target_id, "approved", None)
            except Exception as e:
                logger.error("Failed to update payment status in DB: %s", e)

        if source_message:
            await source_message.reply_text(
                f"אושר ונשלח קישור + עותק ממוספר למשתמש {target_id}."
            )
    except Exception as e:
        logger.error("Failed to send approval message: %s", e)
        if source_message:
            await source_message.reply_text(f"שגיאה בשליחת הודעה למשתמש {target_id}: {e}")

async def do_reject(target_id: int, reason: str, context: ContextTypes.DEFAULT_TYPE, source_message) -> None:
    """לוגיקת דחיית תשלום – משותפת ל-/reject ולזרימת כפתור"""
    payments = context.application.bot_data.get("payments", {})
    payment_info = payments.get(target_id)

    base_text = (
        "לצערנו לא הצלחנו לאמת את התשלום שנשלח.\n\n"
        f"סיבה: {reason}\n\n"
        "אם לדעתך מדובר בטעות – אנא פנה אלינו עם פרטי התשלום או נסה לשלוח מחדש."
    )

    try:
        if payment_info and payment_info.get("file_id"):
            # שליחת צילום + הסבר
            if DB_AVAILABLE:
        try:
            if mode == "view":
                increment_metric("start_image_views", 1)
            elif mode == "download":
                increment_metric("start_image_downloads", 1)
        except Exception as e:
            logger.error("Failed to increment metrics: %s", e)
    await context.bot.send_photo(
                chat_id=target_id,
                photo=payment_info["file_id"],
                caption=base_text,
            )
        else:
            await context.bot.send_message(chat_id=target_id, text=base_text)

        # עדכון סטטוס ב-DB
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

# =========================
# אישור/דחייה – פקודות טקסט
# =========================

async def approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """אישור תשלום למשתמש: /approve <user_id>"""
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
    """דחיית תשלום למשתמש: /reject <user_id> <סיבה>"""
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
# Leaderboard / סטטיסטיקות / Rewards – פקודות אדמין
# =========================

async def admin_leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """לוח מפנים – /leaderboard"""
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
        rows: List[Dict[str, Any]] = get_top_referrers(10)
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
        "\n".join(lines),
        parse_mode="Markdown",
    )

async def admin_payments_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """דוח תשלומים – /payments_stats"""
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
    year = now.year
    month = now.month

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
        "\n".join(lines),
        parse_mode="Markdown",
    )

async def admin_reward_slh_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    יצירת Reward ידני למשתמש – לדוגמה:
    /reward_slh <user_id> <points> <reason...>
    """
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
        await update.effective_message.reply_text("user_id ו-points חייבים להיות מספריים.")
        return

    reason = " ".join(context.args[2:])

    try:
        create_reward(target_id, "SLH", reason, points)
    except Exception as e:
        logger.error("Failed to create reward: %s", e)
        await update.effective_message.reply_text("שגיאה ביצירת Reward.")
        return

    # הודעה למשתמש (עדיין ללא mint אמיתי – לוגי)
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
                "Reward זה יאסף למאזן שלך ויאפשר הנפקת מטבעות/נכסים "
                "דיגיטליים לפי המדיניות שתפורסם בקהילה."
            ),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error("Failed to notify user about reward: %s", e)

# =========================
# אישור/דחייה – כפתורי אדמין
# =========================

async def admin_approve_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """כפתור 'אשר תשלום' בלוגים"""
    query = update.callback_query
    await query.answer()
    admin = query.from_user

    if admin.id not in ADMIN_IDS:
        await query.answer(
            "אין לך הרשאה.\nאם אתה חושב שזו טעות – דבר עם @OsifEU",
            show_alert=True,
        )
        return

    data = query.data or ""
    try:
        _, user_id_str = data.split(":", 1)
        target_id = int(user_id_str)
    except Exception:
        await query.answer("שגיאה בנתוני המשתמש.", show_alert=True)
        return

    await do_approve(target_id, context, query.message)

async def admin_reject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """כפתור 'דחה תשלום' – מבקש מהאדמין סיבה בהודעה הבאה שלו"""
    query = update.callback_query
    await query.answer()
    admin = query.from_user

    if admin.id not in ADMIN_IDS:
        await query.answer(
            "אין לך הרשאה.\nאם אתה חושב שזו טעות – דבר עם @OsifEU",
            show_alert=True,
        )
        return

    data = query.data or ""
    try:
        _, user_id_str = data.split(":", 1)
        target_id = int(user_id_str)
    except Exception:
        await query.answer("שגיאה בנתוני המשתמש.", show_alert=True)
        return

    pending = get_pending_rejects(context)
    pending[admin.id] = target_id

    await query.message.reply_text(
        f"❌ בחרת לדחות את התשלום של המשתמש {target_id}.\n"
        "שלח עכשיו את סיבת הדחייה בהודעה אחת (טקסט), והיא תישלח אליו יחד עם צילום התשלום."
    )

async def admin_reject_reason_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    הודעת טקסט מאדמין אחרי שלחץ 'דחה תשלום':
    משתמשים בזה כסיבה לדחייה.
    """
    user = update.effective_user
    if user is None or user.id not in ADMIN_IDS:
        return

    pending = get_pending_rejects(context)
    if user.id not in pending:
        return  # אין דחייה ממתינה עבור האדמין הזה

    target_id = pending.pop(user.id)
    reason = update.message.text.strip()
    await do_reject(target_id, reason, context, update.effective_message)

# =========================
# עזרה + תפריט אדמין
# =========================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """עזרה בסיסית"""
    message = update.message or update.effective_message
    if not message:
        return

    text = (
        "/start – התחלה מחדש ותפריט ראשי\n"
        "/help – עזרה\n\n"
        "אחרי ביצוע תשלום – שלח צילום מסך של האישור לבוט.\n\n"
        "לשיתוף שער הקהילה: כפתור '🔗 שתף את שער הקהילה' בתפריט הראשי.\n\n"
        "למארגנים / אדמינים:\n"
        "/admin – תפריט אדמין\n"
        "/leaderboard – לוח מפנים (Top 10)\n"
        "/payments_stats – סטטיסטיקות תשלומים\n"
        "/reward_slh <user_id> <points> <reason> – יצירת Reward ל-SLH\n"
        "/approve <user_id> – אישור תשלום\n"
        "/reject <user_id> <סיבה> – דחיית תשלום\n"
        "או שימוש בכפתורי האישור/דחייה ליד כל תשלום בלוגים."
    )

    await message.reply_text(text)

async def admin_menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """פקודת /admin – תפריט אדמין"""
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
        "• מוני תמונת שער (כמה פעמים הוצגה/נשלחה)\n"
        "• רעיונות לפיצ'רים עתידיים לבוט\n\n"
        "פקודות נוספות:\n"
        "/leaderboard – לוח מפנים\n"
        "/payments_stats – דוח תשלומים\n"
        "/reward_slh – יצירת Reward SLH\n"
    )

    await update.effective_message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=admin_menu_keyboard(),
    )

async def admin_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """טיפול בכפתורי תפריט האדמין"""
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

    app_data = context.application.bot_data
    views = app_data.get("start_image_views", 0)
    downloads = app_data.get("start_image_downloads", 0)

    if data == "adm_status":
        text = (
            "📊 *סטטוס מערכת*\n\n"
            f"• DB: {'פעיל' if DB_AVAILABLE else 'כבוי'}\n"
            f"• Webhook URL: `{WEBHOOK_URL}`\n"
            f"• LANDING_URL: `{LANDING_URL}`\n"
            f"• PAYBOX_URL: `{PAYBOX_URL}`\n"
            f"• BIT_URL: `{BIT_URL}`\n"
            f"• PAYPAL_URL: `{PAYPAL_URL}`\n"
        )
        await query.message.edit_text(
            text,
            parse_mode="Markdown",
            reply_markup=admin_menu_keyboard(),
        )

    elif data == "adm_counters":
        text = (
            "📈 *מוני תמונת שער*\n\n"
            f"• מספר הצגות (start): {views}\n"
            f"• עותקים ממוספרים שנשלחו אחרי אישור: {downloads}\n\n"
            "המונים מאופסים בכל הפעלה מחדש של הבוט (in-memory)."
        )
        await query.message.edit_text(
            text,
            parse_mode="Markdown",
            reply_markup=admin_menu_keyboard(),
        )

    elif data == "adm_ideas":
        text = (
            "💡 *רעיונות לפיצ'רים עתידיים לבוט*\n\n"
            "1. מערכת ניקוד מלאה למפנים (Leaderboard בקבוצה).\n"
            "2. דוחות מתקדמים יותר ב-DB:\n"
            "   • פילוח לפי זמנים\n"
            "   • פילוח לפי מקור הפניה.\n"
            "3. הנפקת נכסים דיגיטליים (NFT / SLH) אוטומטית למשתתפים:\n"
            "   • לפי מספר הפניות\n"
            "   • לפי רמת פעילות בקהילה.\n"
            "4. דשבורד וובי קטן (Read-only) להצגת הסטטיסטיקות.\n"
            "5. אינטגרציה עם בוטי תוכן / קווסטים שמזינים את אותה מערכת נקודות.\n"
        )
        await query.message.edit_text(
            text,
            parse_mode="Markdown",
            reply_markup=admin_menu_keyboard(),
        )

# =========================
# רישום handlers
# =========================

ptb_app.add_handler(CommandHandler("start", entry_start))
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

# כל תמונה בפרטי – נניח כאישור תשלום
ptb_app.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, handle_payment_photo))

# הודעת טקסט מאדמין – אם יש דחייה ממתינה
ptb_app.add_handler(MessageHandler(filters.TEXT & filters.User(list(ADMIN_IDS)), admin_reject_reason_handler))

# =========================
# JobQueue – תזכורת כל 6 ימים לעדכון לינקים
# =========================

async def remind_update_links(context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_start_image(context, PAYMENTS_LOG_CHAT_ID, mode="reminder")

# =========================
# FastAPI + lifespan
# =========================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    בזמן עליית השרת:
    1. מגדירים webhook ב-Telegram ל-WEBHOOK_URL
    2. מפעילים את אפליקציית ה-Telegram
    3. מפעילים JobQueue לתזכורת כל 6 ימים
    4. אם יש DB – מרימים schema
    """
    logger.info("Setting Telegram webhook to %s", WEBHOOK_URL)
    await ptb_app.bot.setWebhook(url=WEBHOOK_URL, allowed_updates=Update.ALL_TYPES)

    # init DB schema אם זמין
    if DB_AVAILABLE:
        try:
            init_schema()
            logger.info("DB schema initialized.")
        except Exception as e:
            logger.error("Failed to init DB schema: %s", e)

    async with ptb_app:
        logger.info("Starting Telegram Application")
        await ptb_app.start()

        # תזכורת כל 6 ימים
        if ptb_app.job_queue:
            ptb_app.job_queue.run_repeating(
                remind_update_links,
                interval=6 * 24 * 60 * 60,  # 6 ימים בשניות
                first=6 * 24 * 60 * 60,
            )

        yield
        logger.info("Stopping Telegram Application")
        await ptb_app.stop()

app = FastAPI(lifespan=lifespan)

# =========================
# Routes – Webhook + Health + Admin Stats API
# =========================

@app.post("/webhook")
async def telegram_webhook(request: Request) -> Response:
    """נקודת ה-webhook שטלגרם קורא אליה"""
    data = await request.json()
    update = Update.de_json(data, ptb_app.bot)

    if is_duplicate_update(update):
        logger.warning("Duplicate update_id=%s – ignoring", update.update_id)
        return Response(status_code=HTTPStatus.OK.value)

    await ptb_app.process_update(update)
    return Response(status_code=HTTPStatus.OK.value)


@app.get("/health")
async def health():
    """Healthcheck ל-Railway / ניטור"""
    return {
        "status": "ok",
        "service": "telegram-gateway-community-bot",
        "db": "enabled" if DB_AVAILABLE else "disabled",
    }


@app.get("/admin/stats")
async def admin_stats(token: str = ""):
    """
    דשבורד API קטן לקריאה בלבד.
    להשתמש ב-ADMIN_DASH_TOKEN ב-ENV.
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

    metrics = {
        "start_image_views": get_metric("start_image_views"),
        "start_image_downloads": get_metric("start_image_downloads"),
    }

    return {
        "db": "enabled",
        "payments_stats": stats,
        "monthly_breakdown": monthly,
        "top_referrers": top_ref,
        "metrics": metrics,
    }


# === SLH GATEWAY START TEXT v2 ===
# שער כניסה משודרג  נכס דיגיטלי, אימות כפול, חינוך פיננסי

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

def get_user_lang(update: Update) -> str:
    code = (update.effective_user.language_code or "").lower()
    if code.startswith("he"):
        return "he"
    return "en"


async def entry_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat
    lang = get_user_lang(update)

    # טקסט בעברית  ברירת מחדל
    if lang == "he":
        text = (
            "ברוך הבא לשער המערכת של החיים שלנו  Buy_My_Shop / SLH Gateway \\n\\n"
            "כאן התשלום *לא קונה סתם גישה לבוט*, אלא נכס דיגיטלי מניב: קישור לקבוצה עסקית סגורה, "
            "שמייצגת את הזכאות שלך להשתתף במערכת התגמולים וההטבות שלנו.\\n\\n"
            " *למה אימות כפול?*\\n"
            "כמו בכל מערכת בנקאית רצינית  גם כאן אנחנו עובדים באימות כפול: \\n"
            "1) אתה מאמת ששילמת (באמצעות צילום מסך / אישור העברה)\\n"
            "2) אנחנו מאמתים ידנית שקיבלנו את התשלום ומאשרים את הקישור לקבוצה.\\n"
            "כך אף אחד לא יכול למכור 'נכס' (הקישור לקבוצה) בלי לקבל כסף בפועל, גם היום וגם בעתיד.\\n\\n"
            " *איך זה מתחבר לעתיד שלך?*\\n"
            "לאחר ההצטרפות, תוכל:\\n"
            " להגדיר קבוצה עסקית אחת משלך (למשל קהילה/חנות/ערוץ משלך)\\n"
            " להגדיר חשבון בנק / ביט / פייבוקס לקבלת תשלומים\\n"
            " לשתף את מערכת Buy_My_Shop עם אחרים ולקבל קרדיט על כל מי שנכנס דרכך\\n"
            " אחרי 39 שיתופים מאושרים  תוכל להיכנס לפאנל האדמין שלך,\\n"
            "  או לחלופין לשלם 39 ש\"ח נוספים כדי לפתוח גישה ישירה לפאנל.\\n\\n"
            " *חוזה חכם  בשפה פשוטה*\\n"
            "כל פעולה  הצטרפות, הגדרת קבוצה, הוספת פרטי תשלום, בקשת שירות נוסף  נרשמת במערכת כחוזה "
            "חכם בסיסי: אנחנו יודעים מי ביקש מה, מה הוסכם, ומה מצב הטיפול. בהמשך זה יתחבר גם לבלוקצ'יין ו-NFT.\\n\\n"
            "כדי להמשיך  בחר אחת מהאפשרויות למטה. אתה יכול להתחיל מתשלום, או קודם להבין לעומק איך זה עובד."
        )
    else:
        # גרסה באנגלית למי שהטלגרם שלו לא בעברית
        text = (
            "Welcome to the SLH / Buy_My_Shop Gateway \\n\\n"
            "Here your payment does *not* just buy access to a bot  it buys a digital, income-producing asset: "
            "a private business-group link that represents your right to participate in our rewards and benefits system.\\n\\n"
            " *Why double verification?*\\n"
            "Just like serious banking systems, we use double verification:\\n"
            "1) You confirm that you paid (by sending a screenshot / payment proof)\\n"
            "2) We manually confirm that the funds arrived and only then unlock the group link.\\n\\n"
            "After joining you will be able to:\\n"
            " Register one business group of your own\\n"
            " Add your bank / PayBox / Bit details for payouts\\n"
            " Share the system with others and earn credit for every user that joins through you\\n"
            " After 39 confirmed referrals  you unlock your personal admin panel, "
            "or pay an additional 39 NIS to unlock it directly.\\n\\n"
            "Every step is saved as a simple 'smart contract' inside our system, and later this will be "
            "anchored on-chain.\\n\\n"
            "Use the menu below to continue."
        )

    keyboard = [
        [
            InlineKeyboardButton(" שלח צילום תשלום", callback_data="send_payment_proof"),
        ],
        [
            InlineKeyboardButton("ℹ איך זה עובד?", callback_data="how_it_works"),
        ],
        [
            InlineKeyboardButton(" הקבוצה העסקית שלי", callback_data="user_group_info"),
        ],
        [
            InlineKeyboardButton(" פרטי תשלום שלי", callback_data="user_payment_info"),
        ],
        [
            InlineKeyboardButton(" הפאנל האישי שלי", callback_data="user_panel"),
        ],
    ]

    await update.effective_message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        disable_web_page_preview=True,
    )

# סוף שער מערכת v2



##############################################################
# Social Layer + HTML dashboard + /site (SAFE VERSION)
##############################################################

from fastapi.responses import HTMLResponse
from social_api import social_router
from db import ensure_social_tables
from pathlib import Path
import httpx
import logging

logger = logging.getLogger("social")

# --- הפעלת טבלאות רשת חברתית ---
@app.on_event("startup")
async def init_social_tables():
    try:
        ensure_social_tables()
        logger.info("Social tables ready")
    except Exception as e:
        logger.exception("Failed to init social tables")

# --- חיבור הAPI של הרשת החברתית ---
app.include_router(social_router, prefix="/api/social", tags=["social"])

# --- דף index של BizNet ---
@app.get("/site", response_class=HTMLResponse)
async def biznet_site():
    index_path = Path(__file__).parent / "docs" / "index.html"
    if not index_path.exists():
        return HTMLResponse("<h1>No BizNet found</h1>", status_code=404)
    return HTMLResponse(index_path.read_text(encoding="utf-8"))

# --- root מציג את BizNet ---
@app.get("/", response_class=HTMLResponse)
async def root_redirect():
    index_path = Path(__file__).parent / "docs" / "index.html"
    if index_path.exists():
        return HTMLResponse(index_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>API OK</h1><p>Docs at /docs</p>")

# --- לוח HTML על בסיס /admin/stats ---
@app.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard(request: Request, token: str = ""):
    if not token:
        return HTMLResponse("<h1>Missing token</h1>", status_code=401)

    base = str(request.base_url).rstrip("/")
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{base}/admin/stats", params={"token": token})
    except Exception as e:
        logger.exception("Dashboard error")
        return HTMLResponse("<h1>Error contacting stats API</h1>", status_code=500)

    if r.status_code != 200:
        return HTMLResponse(f"<h1>Error {r.status_code}</h1>{r.text}")

    data = r.json()
    html = f"<html><body><h1>Admin Dashboard</h1><pre>{data}</pre></body></html>"
    return HTMLResponse(html)
##############################################################
import httpx
from pathlib import Path
from fastapi.responses import HTMLResponse

# =========================
# HTML Site + Admin Dashboard
# =========================

@app.get("/site", response_class=HTMLResponse)
async def biznet_site():
    index_path = Path(__file__).parent / "docs" / "index.html"
    if not index_path.exists():
        return HTMLResponse("<h1>BizNet לא הותקן (docs/index.html חסר)</h1>", status_code=404)
    return HTMLResponse(index_path.read_text(encoding="utf-8"))

@app.get("/", response_class=HTMLResponse)
async def root():
    index_path = Path(__file__).parent / "docs" / "index.html"
    if index_path.exists():
        return HTMLResponse(index_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Botshop API</h1><p>Health at /health</p>")

@app.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard(request: Request, token: str = ""):
    if not ADMIN_DASH_TOKEN or token != ADMIN_DASH_TOKEN:
        return HTMLResponse("<h1>Unauthorized</h1>", status_code=401)

    base = str(request.base_url).rstrip("/")
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{base}/admin/stats", params={"token": token})
    except Exception as e:
        logger.error("Failed to call /admin/stats: %s", e)
        return HTMLResponse("<h1>Error contacting /admin/stats</h1>", status_code=500)

    if r.status_code != 200:
        return HTMLResponse(f"<h1>Error {r.status_code}</h1><pre>{r.text}</pre>", status_code=r.status_code)

    data = r.json()
    html = f"""
    <html dir="rtl" lang="he">
    <head>
      <meta charset="utf-8" />
      <title>Admin Dashboard</title>
      <style>
        body {{
          font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          background: #020617;
          color: #f9fafb;
          padding: 2rem;
        }}
        pre {{
          background: #0f172a;
          padding: 1rem;
          border-radius: 0.75rem;
          overflow-x: auto;
        }}
      </style>
    </head>
    <body>
      <h1> Admin Dashboard</h1>
      <pre>{data}</pre>
    </body>
    </html>
    """
    return HTMLResponse(html)
