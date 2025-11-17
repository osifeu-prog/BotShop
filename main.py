# main.py
import os
import logging
import secrets
import string
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime
from http import HTTPStatus
from typing import Deque, Set, Literal, Optional, Dict, Any, List

from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
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
        create_support_ticket,
        get_support_tickets,
        update_ticket_status,
        get_user,
        create_user_bot,
        get_user_bot,
        update_user_bot_status,
        get_all_active_bots,
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
# בדיקת BOT_TOKEN
# =========================
import requests

def validate_bot_token(token: str) -> bool:
    """בודק אם הטוקן תקין"""
    try:
        test_url = f"https://api.telegram.org/bot{token}/getMe"
        response = requests.get(test_url, timeout=10)
        if response.status_code == 200:
            logger.info("✅ Bot token is valid")
            return True
        else:
            logger.warning(f"⚠️ BOT_TOKEN may be invalid. Telegram API returned: {response.status_code}")
            return False
    except Exception as e:
        logger.warning(f"⚠️ Failed to validate BOT_TOKEN: {e}")
        return False

# הרץ את הבדיקה
if BOT_TOKEN:
    is_valid = validate_bot_token(BOT_TOKEN)
    if not is_valid:
        logger.error("❌ Invalid BOT_TOKEN. The bot will not work properly.")

# =========================
# קבועים של המערכת
# =========================
COMMUNITY_GROUP_LINK = os.environ.get("COMMUNITY_GROUP_LINK", "https://t.me/+HIzvM8sEgh1kNWY0")
SUPPORT_GROUP_LINK = os.environ.get("SUPPORT_GROUP_LINK", "https://t.me/+1ANn25HeVBoxNmRk")
DEVELOPER_USER_ID = 224223270
PAYMENTS_LOG_CHAT_ID = -1001748319682
SUPPORT_LOG_CHAT_ID = -1001748319682

def build_personal_share_link(user_id: int) -> str:
    base_username = BOT_USERNAME or "Buy_My_Shop_bot"
    return f"https://t.me/{base_username}?start=ref_{user_id}"

# לינקי תשלום
PAYBOX_URL = os.environ.get("PAYBOX_URL", "https://links.payboxapp.com/1SNfaJ6XcYb")
BIT_URL = os.environ.get("BIT_URL", "https://www.bitpay.co.il/app/share-info?i=190693822888_19l4oyvE")
PAYPAL_URL = os.environ.get("PAYPAL_URL", "https://paypal.me/osifdu")
LANDING_URL = os.environ.get("LANDING_URL", "https://slh-nft.com/")
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

# =========================
# פונקציות ליצירת בוטים חדשים
# =========================

def generate_bot_token() -> str:
    """מייצר טוקן אקראי לבוט (פורמט דומה לטוקן אמיתי)"""
    alphabet = string.ascii_letters + string.digits + ":_-"
    random_part = ''.join(secrets.choice(alphabet) for _ in range(35))
    return f"1234567890:ABC{random_part}"

def generate_bot_username(user_id: int, username: str = None) -> str:
    """מייצר שם משתמש ייחודי לבוט"""
    base_name = username.replace('_', '') if username else f"user{user_id}"
    random_suffix = ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(6))
    return f"{base_name}_{random_suffix}_bot"[:32]

async def create_new_bot_for_user(user_id: int, username: str = None) -> Dict[str, Any]:
    """
    יוצר בוט חדש למשתמש
    """
    try:
        bot_token = generate_bot_token()
        bot_username = generate_bot_username(user_id, username)
        
        bot_data = {
            "token": bot_token,
            "username": bot_username,
            "webhook_url": f"{WEBHOOK_URL}/{bot_token}",
            "created_at": datetime.utcnow(),
            "status": "active"
        }
        
        # שמירה ב-DB
        if DB_AVAILABLE:
            bot_id = create_user_bot(user_id, bot_token, bot_username, bot_data["webhook_url"])
            bot_data["id"] = bot_id
        
        logger.info(f"Created new bot for user {user_id}: {bot_username}")
        return bot_data
        
    except Exception as e:
        logger.error(f"Failed to create bot for user {user_id}: {e}")
        raise

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
# FastAPI + lifespan
# =========================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    בזמן עליית השרת:
    1. מגדירים webhook ב-Telegram ל-WEBHOOK_URL
    2. מפעילים את אפליקציית ה-Telegram
    3. אם יש DB – מרימים schema
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
        yield
        logger.info("Stopping Telegram Application")
        await ptb_app.stop()

app = FastAPI(lifespan=lifespan)

# =========================
# API Routes
# =========================

@app.get("/")
async def serve_site():
    """מגיש את אתר האינטרנט"""
    return FileResponse("docs/index.html")

@app.get("/site")
async def serve_site_alt():
    """מגיש את אתר האינטרנט (alias)"""
    return FileResponse("docs/index.html")

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
    """
    if not ADMIN_DASH_TOKEN or token != ADMIN_DASH_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if not DB_AVAILABLE:
        return {"db": "disabled"}

    try:
        stats = get_approval_stats()
        monthly = get_monthly_payments(datetime.utcnow().year, datetime.utcnow().month)
        top_ref = get_top_referrers(5)
        active_bots = get_all_active_bots()
    except Exception as e:
        logger.error("Failed to get admin stats: %s", e)
        raise HTTPException(status_code=500, detail="DB error")

    return {
        "db": "enabled",
        "payments_stats": stats,
        "monthly_breakdown": monthly,
        "top_referrers": top_ref,
        "active_bots_count": len(active_bots),
    }

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

@app.post("/webhook/{bot_token}")
async def user_bot_webhook(bot_token: str, request: Request):
    """Webhook לבוטים של משתמשים"""
    try:
        # כאן תוכל להוסיף לוגיקה לטיפול בבוטים של משתמשים
        return Response(status_code=HTTPStatus.OK.value)
    except Exception as e:
        logger.error(f"Error in user bot webhook: {e}")
        return Response(status_code=HTTPStatus.OK.value)

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
            InlineKeyboardButton("🌟 חזון SLH", callback_data="vision"),
        ],
        [
            InlineKeyboardButton("👤 האזור האישי שלי", callback_data="my_area"),
        ],
        [
            InlineKeyboardButton("🆘 תמיכה טכנית", callback_data="technical_support"),
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
            InlineKeyboardButton("🤖 הבוט שלי", callback_data="my_bot"),
        ],
        [
            InlineKeyboardButton("⬅ חזרה", callback_data="back_main"),
        ],
    ])

def support_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🛠️ תמיכה טכנית", callback_data="technical_support"),
        ],
        [
            InlineKeyboardButton("📞 פניה למנהל", callback_data="contact_admin"),
        ],
        [
            InlineKeyboardButton("❓ עזרה", callback_data="help_support"),
        ],
        [
            InlineKeyboardButton("⬅ חזרה", callback_data="back_main"),
        ],
    ])

def technical_support_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📋 דיווח באג", callback_data="report_bug"),
        ],
        [
            InlineKeyboardButton("❓ בעיה טכנית", callback_data="tech_issue"),
        ],
        [
            InlineKeyboardButton("🔧 בעיית תשלום", callback_data="payment_issue"),
        ],
        [
            InlineKeyboardButton("⬅ חזרה", callback_data="back_support"),
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

async def send_new_user_notification(user_data: dict, user_id: int):
    """שולח התראה על משתמש חדש"""
    try:
        username_link = f"https://t.me/{user_data['username']}" if user_data.get('username') else f"tg://user?id={user_id}"
        
        message = (
            f"👤 משתמש חדש התחיל את הבוט:\n"
            f"🆔 ID: {user_id}\n"
            f"📛 שם: {user_data.get('first_name', 'לא צוין')}\n"
            f"👤 משתמש: @{user_data.get('username', 'לא צוין')}\n"
            f"📅 תאריך: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
            f"💬 <a href='{username_link}'>לחץ כאן לשליחת הודעה</a>"
        )
        
        await ptb_app.bot.send_message(
            chat_id=PAYMENTS_LOG_CHAT_ID,
            text=message,
            parse_mode='HTML',
            disable_web_page_preview=True
        )
    except Exception as e:
        logging.error(f"שגיאה בשליחת התראה על משתמש חדש: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message or update.effective_message
    if not message:
        return

    user = update.effective_user

    # לוג ל-DB ולקבוצת הלוגים
    if DB_AVAILABLE and user:
        try:
            store_user(user.id, user.username, user.first_name, user.last_name)
            incr_metric("total_starts")
            
            # שליחת התראה על משתמש חדש
            user_data = {
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name
            }
            await send_new_user_notification(user_data, user.id)
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

    # ניסיון לשלוח תמונה אם קיימת
    try:
        if os.path.exists(START_IMAGE_PATH):
            with open(START_IMAGE_PATH, 'rb') as photo:
                await message.reply_photo(
                    photo=photo,
                    caption="🎉 *ברוך הבא לנכס הדיגיטלי המניב שלך!*",
                    parse_mode="Markdown"
                )
    except Exception as e:
        logger.error("Failed to send start image: %s", e)

    # שליחת הודעת ברוכים הבאים
    text = (
        "🎉 *ברוך הבא לנכס הדיגיטלי המניב שלך!*\n\n"
        
        "💎 *מה זה הנכס הדיגיטלי?*\n"
        "זהו שער כניסה אישי לקהילת עסקים פעילה. לאחר רכישה תקבל:\n"
        "• לינק אישי להפצה\n"
        "• אפשרות למכור את הנכס הלאה\n"
        "• גישה לקבוצת משחק כללית\n"
        "• מערכת הפניות מתגמלת\n"
        "• 🤖 *בוט טלגרם אישי משלך!*\n\n"
        
        "🔄 *איך זה עובד?*\n"
        "1. רוכשים נכס ב-39₪\n"
        "2. מקבלים לינק אישי + בוט אישי\n"
        "3. מפיצים - כל רכישה דרך הלינק שלך מתועדת\n"
        "4. מרוויחים מהפצות נוספות\n\n"
        
        "🚀 *מה תקבל?*\n"
        "✅ גישה לקהילת עסקים\n"
        "✅ נכס דיגיטלי אישי\n"
        "✅ לינק הפצה ייחודי\n"
        "✅ 🤖 בוט טלגרם אישי\n"
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
        "• גישה למערכת שלמה\n"
        "• 🤖 *בוט טלגרם אישי משלך!*\n\n"
        
        "💸 *איך מרוויחים?*\n"
        "1. אתה רוכש נכס ב-39₪\n"
        "2. מקבל לינק אישי להפצה + בוט אישי\n"
        "3 *כל אדם* שקונה דרך הלינק שלך - הרכישה מתועדת לזכותך\n"
        "4. הנכס שלך ממשיך להניב הכנסות\n\n"
        
        "🔄 *מודל מכירה חוזרת:*\n"
        "אתה לא רק 'משתמש' - אתה 'בעל נכס'!\n"
        "יכול למכור נכסים נוספים לאחרים\n"
        "כל רכישה נוספת מתועדת בשרשרת ההפניה\n"
        "🤖 *מקבל בוט אישי למכירות!*\n\n"
        
        "📈 *יתרונות:*\n"
        "• הכנסה פסיבית מהפצות\n"
        "• נכס ששווה יותר עם הזמן\n"
        "• קהילה תומכת\n"
        "• 🤖 בוט אישי למכירות\n"
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
        "• אפשרות למכור נכסים נוספים\n"
        "• 🤖 *בוט טלגרם אישי משלך!*\n\n"
        
        "🔄 *איך התהליך עובד?*\n"
        "1. בוחרים אמצעי תשלום\n"
        "2. משלמים 39₪\n"
        "3. שולחים אישור תשלום\n"
        "4. מקבלים אישור + לינק אישי + בוט אישי\n"
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
        user_bot = get_user_bot(user.id)
        
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
            )
            
            if user_bot:
                text += f"🤖 *הבוט שלך:* פעיל - @{user_bot['bot_username']}\n\n"
            else:
                text += "🤖 *הבוט שלך:* לא פעיל - רכוש נכס כדי לקבל בוט\n\n"
                
            text += "*ניהול נכס:*"
        else:
            text = (
                "👤 *האזור האישי שלך*\n\n"
                "עדיין אין לך נכס דיגיטלי.\n"
                "רכש נכס כדי לקבל:\n"
                "• לינק אישי להפצה\n"
                "• אפשרות למכור נכסים\n"
                "• 🤖 בוט טלגרם אישי\n"
                "• גישה למערכת המלאה"
            )
    else:
        text = "מערכת הזמנית לא זמינת. נסה שוב מאוחר יותר."

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=my_area_keyboard(),
    )

async def my_bot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """מציג למשתמש את הבוט האישי שלו"""
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    if not user:
        return

    if DB_AVAILABLE:
        user_bot = get_user_bot(user.id)
        
        if user_bot and user_bot['status'] == 'active':
            bot_username = user_bot['bot_username']
            bot_link = f"https://t.me/{bot_username}"
            
            text = (
                "🤖 *הבוט האישי שלך*\n\n"
                f"🔗 *קישור לבוט:* {bot_link}\n"
                f"👤 *שם משתמש:* @{bot_username}\n"
                f"📊 *סטטוס:* פעיל\n\n"
                "*מה אפשר לעשות עם הבוט?*\n"
                "• למכור נכסים דיגיטליים\n"
                "• לנהל לקוחות\n"
                "• לעקוב אחר מכירות\n"
                "• להפיץ את העסק שלך\n\n"
                "🚀 *התחל במכירות!*"
            )
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🤖 פתח את הבוט שלי", url=bot_link)],
                [InlineKeyboardButton("⬅ חזרה", callback_data="my_area")],
            ])
        else:
            text = (
                "🤖 *עדיין אין לך בוט אישי*\n\n"
                "כדי לקבל בוט טלגרם אישי משלך:\n"
                "1. רכוש נכס דיגיטלי ב-39₪\n"
                "2. שלח אישור תשלום\n"
                "3. לאחר האישור - תקבל בוט אישי!\n\n"
                "הבוט שלך יהיה מוכן למכירות וינוהל אוטומטית."
            )
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("💎 רכוש נכס עכשיו", callback_data="join")],
                [InlineKeyboardButton("⬅ חזרה", callback_data="my_area")],
            ])
    else:
        text = "מערכת הזמנית לא זמינת. נסה שוב מאוחר יותר."
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅ חזרה", callback_data="my_area")],
        ])

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=keyboard,
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
        "3. תקבל את הנכס הדיגיטלי שלך + 🤖 בוט אישי!\n"
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

    # יצירת לינק ישיר למשתמש
    username_link = f"https://t.me/{user.username}" if user.username else f"tg://user?id={user.id}"
    
    caption_log = (
        f"💰 <b>אישור תשלום חדש התקבל!</b>\n\n"
        f"👤 <b>user_id:</b> <code>{user.id}</code>\n"
        f"📛 <b>username:</b> @{user.username or 'ללא'}\n"
        f"💳 <b>שיטת תשלום:</b> {pay_method_text}\n"
        f"🕐 <b>זמן:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"💬 <a href='{username_link}'>לחץ כאן לשליחת הודעה למשתמש</a>\n\n"
        f"<b>פעולות:</b>"
    )

    try:
        await context.bot.send_photo(
            chat_id=PAYMENTS_LOG_CHAT_ID,
            photo=file_id,
            caption=caption_log,
            parse_mode="HTML",
            reply_markup=admin_approval_keyboard(user.id),
        )
    except Exception as e:
        logger.error("Failed to send payment to log group: %s", e)

    await message.reply_text(
        "✅ *אישור התשלום התקבל!*\n\n"
        "האישור נשלח לצוות שלנו לאימות.\n"
        "תקבל הודעה עם הנכס הדיגיטלי שלך + 🤖 בוט אישי בתוך זמן קצר.\n\n"
        "💎 *מה תקבל לאחר אישור:*\n"
        "• לינק אישי להפצה\n"
        "• גישה לקהילה\n"
        "• 🤖 בוט טלגרם אישי\n"
        "• אפשרות למכור נכסים נוספים",
        parse_mode="Markdown",
    )

async def do_approve(target_id: int, context: ContextTypes.DEFAULT_TYPE, source_message) -> None:
    """מאשר תשלום ויוצר בוט אישי למשתמש"""
    try:
        # יצירת בוט אישי למשתמש
        user = get_user(target_id)
        username = user.get('username') if user else None
        
        bot_data = await create_new_bot_for_user(target_id, username)
        personal_link = build_personal_share_link(target_id)
        
        # הודעת אישור למשתמש
        approval_text = (
            "🎉 *התשלום אושר! ברוך הבא לבעלי הנכסים!*\n\n"
            
            "💎 *הנכס הדיגיטלי שלך מוכן:*\n"
            f"🔗 *לינק אישי:* `{personal_link}`\n\n"
            
            "🤖 *הבוט האישי שלך נוצר!*\n"
            f"👤 @{bot_data['username']}\n\n"
            
            "🚀 *מה עכשיו?*\n"
            "1. שתף את הלינק עם אחרים\n"
            "2. השתמש בבוט האישי שלך למכירות\n"
            "3. כל רכישה דרך הלינק שלך מתועדת\n"
            "4. תוכל למכור נכסים נוספים\n"
            "5. צבור הכנסה מהפצות\n\n"
            
            "👥 *גישה לקהילה:*\n"
            f"{COMMUNITY_GROUP_LINK}\n\n"
            
            "💼 *ניהול הנכס:*\n"
            "השתמש בכפתור '👤 האזור האישי שלי'\n"
            "כדי לגשת לבוט שלך ולנהל את הנכס"
        )

        await context.bot.send_message(chat_id=target_id, text=approval_text, parse_mode="Markdown")
        
        # עדכון DB
        if DB_AVAILABLE:
            try:
                update_payment_status(target_id, "approved", None)
                ensure_promoter(target_id)
                incr_metric("approved_payments")
                incr_metric("total_bots_created")
            except Exception as e:
                logger.error("Failed to update DB: %s", e)

        if source_message:
            await source_message.reply_text(f"✅ אושר למשתמש {target_id} - נשלח נכס דיגיטלי + בוט אישי")
            
    except Exception as e:
        logger.error("Failed to send approval: %s", e)
        if source_message:
            await source_message.reply_text(f"❌ שגיאה באישור למשתמש {target_id}: {e}")

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

async def back_support_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "🆘 *תמיכה ועזרה*\n\n"
        "בחר את סוג התמיכה שאתה צריך:",
        parse_mode="Markdown",
        reply_markup=support_keyboard(),
    )

async def technical_support_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    text = (
        "🛠️ *תמיכה טכנית*\n\n"
        "בחר את סוג הבעיה שאתה נתקל בה:\n\n"
        "• 📋 דיווח באג - דיווח על תקלה טכנית\n"
        "• ❓ בעיה טכנית - בעיה בהפעלת המערכת\n"
        "• 🔧 בעיית תשלום - בעיה בתהליך התשלום"
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=technical_support_keyboard(),
    )

async def contact_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    text = (
        "📞 *פניה למנהל*\n\n"
        "לפנייה ישירה למנהל המערכת:\n\n"
        f"👤 <a href='tg://user?id={DEVELOPER_USER_ID}'>לחץ כאן לשליחת הודעה למנהל</a>\n\n"
        "או השתמש בכפתור למטה:"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 שלח הודעה למנהל", url=f"tg://user?id={DEVELOPER_USER_ID}")],
        [InlineKeyboardButton("⬅ חזרה", callback_data="back_support")],
    ])

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

async def help_support_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    text = (
        "❓ *עזרה כללית*\n\n"
        "לעזרה כללית והסברים על המערכת:\n\n"
        f"👥 <a href='{SUPPORT_GROUP_LINK}'>קבוצת התמיכה שלנו</a>\n\n"
        "בקבוצה תוכל לקבל עזרה ממשתמשים אחרים ומהצוות."
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 הצטרף לקבוצת התמיכה", url=SUPPORT_GROUP_LINK)],
        [InlineKeyboardButton("⬅ חזרה", callback_data="back_support")],
    ])

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

async def report_bug_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    context.user_data['support_type'] = 'bug_report'
    
    await query.edit_message_text(
        "📋 *דיווח באג*\n\n"
        "אנא תאר את הבאג או התקלה הטכנית שאתה נתקל בה:\n\n"
        "שלח הודעה עם פרטים מלאים על הבעיה.",
        parse_mode="Markdown",
    )

async def tech_issue_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    context.user_data['support_type'] = 'tech_issue'
    
    await query.edit_message_text(
        "❓ *בעיה טכנית*\n\n"
        "אנא תאר את הבעיה הטכנית שאתה נתקל בה:\n\n"
        "שלח הודעה עם פרטים מלאים על הבעיה.",
        parse_mode="Markdown",
    )

async def payment_issue_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    context.user_data['support_type'] = 'payment_issue'
    
    await query.edit_message_text(
        "🔧 *בעיית תשלום*\n\n"
        "אנא תאר את בעיית התשלום שאתה נתקל בה:\n\n"
        "שלח הודעה עם פרטים מלאים על הבעיה.",
        parse_mode="Markdown",
    )

async def handle_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """מטפל בהודעות תמיכה מהמשתמש"""
    message = update.message
    if not message or not message.text:
        return

    user = update.effective_user
    support_type = context.user_data.get('support_type')
    
    if not support_type:
        return

    # יצירת כרטיס תמיכה ב-DB
    ticket_id = -1
    if DB_AVAILABLE:
        subject = {
            'bug_report': 'דיווח באג',
            'tech_issue': 'בעיה טכנית',
            'payment_issue': 'בעיית תשלום'
        }.get(support_type, 'תמיכה כללית')
        
        ticket_id = create_support_ticket(
            user.id, 
            user.username, 
            subject, 
            message.text
        )

    # שליחת הודעה לקבוצת הלוגים
    username_link = f"https://t.me/{user.username}" if user.username else f"tg://user?id={user.id}"
    
    support_message = (
        f"🆘 <b>כרטיס תמיכה חדש</b>\n\n"
        f"📋 <b>סוג:</b> {support_type}\n"
        f"👤 <b>משתמש:</b> @{user.username or 'ללא'} (<code>{user.id}</code>)\n"
        f"🆔 <b>כרטיס:</b> #{ticket_id if ticket_id != -1 else 'N/A'}\n"
        f"📅 <b>זמן:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"💬 <b>הודעה:</b>\n{message.text}\n\n"
        f"💬 <a href='{username_link}'>לחץ כאן לשליחת הודעה למשתמש</a>"
    )

    try:
        await context.bot.send_message(
            chat_id=SUPPORT_LOG_CHAT_ID,
            text=support_message,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error("Failed to send support message to log group: %s", e)

    # אישור למשתמש
    await message.reply_text(
        "✅ *הודעת התמיכה התקבלה!*\n\n"
        "ההודעה נשלחה לצוות התמיכה שלנו.\n"
        "נחזור אליך בהקדם האפשרי.\n\n"
        f"מספר כרטיס: #{ticket_id if ticket_id != -1 else 'לא נרשם'}",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )

    # ניקוי סוג התמיכה
    context.user_data.pop('support_type', None)

async def share_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    if not user:
        return

    # בדיקה אם יש למשתמש כבר נכס
    has_asset = False
    if DB_AVAILABLE:
        try:
            summary = get_promoter_summary(user.id)
            has_asset = summary is not None
        except:
            has_asset = False

    if has_asset:
        # אם יש לו נכס - הלינק האישי שלו
        personal_link = build_personal_share_link(user.id)
        text = (
            "🔗 *שתף את שער הקהילה*\n\n"
            "הלינק האישי שלך להפצה:\n"
            f"`{personal_link}`\n\n"
            "מומלץ לשתף בסטורי / סטטוס / קבוצות, ולהוסיף כמה מילים אישיות משלך.\n"
            "כל מי שייכנס דרך הלינק וילחץ על Start בבוט – יעבור דרך שער הקהילה שלך."
        )
    else:
        # אם אין לו נכס - הלינק הכללי + הסבר על 39 שיתופים
        text = (
            "🔗 *שתף את שער הקהילה*\n\n"
            "כדי להזמין חברים לקהילה, אפשר לשלוח להם את הקישור הבא:\n"
            f"{LANDING_URL}\n\n"
            
            "💝 *אפשרות צדקה - 39 שיתופים*\n"
            "לאחר 39 שיתופים איכותיים של הקישור, תוכל לקבל גישה מלאה לקהילה ללא תשלום!\n"
            "זו הזדמנות גם למי שידו אינה משגת להצטרף ולצמוח איתנו.\n\n"
            
            "📢 *איך לשתף:*\n"
            "מומלץ לשתף בסטורי / סטטוס / קבוצות\n"
            "ולהוסיף כמה מילים אישיות משלך.\n\n"
            
            "*כל מי שייכנס דרך הלינק וילחץ על Start בבוט - יעבור דרך שער הקהילה.*"
        )

    await query.message.reply_text(
        text,
        parse_mode="Markdown",
    )

async def vision_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    text = (
        "🌟 *Human Capital Protocol - SLH*\n\n"
        
        "💫 *מה זה SLH במשפט אחד?*\n"
        "SLH הוא פרוטוקול הון אנושי שמחבר בין משפחות, קהילות ומומחים לרשת כלכלית אחת "
        "– עם בוטים, חנויות, טוקן SLH, אקדמיה, משחק, ו־Exchange – כך שכל אדם יכול להפוך "
        "לעסק, למומחה ולצומת כלכלי, מתוך הטלפון שלו.\n\n"
        
        "🎯 *החזון ארוך־טווח:*\n"
        "• להפוך כל אדם ומשפחה ליחידת כלכלה עצמאית\n"
        "• לבנות רשת מסחר גלובלית מבוזרת\n"
        "• ליצור Meta-Economy: שכבת־על טכנולוגית\n"
        "• להפוך את SLH לסטנדרט עולמי למדידת מומחיות\n\n"
        
        "🏗 *האקו־סיסטם המלא:*\n"
        "• 🤖 Bots Layer - בוטי טלגרם\n"
        "• 🛒 Commerce Layer - חנויות ומרקטפלייס\n"
        "• ⛓️ Blockchain Layer - BSC + TON\n"
        "• 🎓 Expertise Layer - Pi Index\n"
        "• 🎮 Academy Layer - למידה ומשחק\n"
        "• 💱 Exchange Layer - מסחר ונזילות\n\n"
        
        "🚀 *Human Capital Protocol*\n"
        "SLH אינו עוד 'אפליקציה' אלא Meta-Protocol: כמו HTTP / Email לכלכלת משפחה וקהילה. "
        "אנשים הם האלגוריתם, המערכת רק מודדת ומתגמלת.\n\n"
        "*ידע = הון | משפחות = נכסים | קהילות = רשתות | אנשים = פרוטוקול*"
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )

# =========================
# Additional command handlers
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
    )

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
        lines.append(f"{rank}. {uname} – {total} הפניות")
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
        stats = get_approval_stats()
    except Exception as e:
        logger.error("Failed to get payment stats: %s", e)
        await update.effective_message.reply_text("שגיאה בקריאת נתוני תשלום.")
        return

    lines = [f"📊 *דוח תשלומים – {month:02d}/{year}* \n"]

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

async def my_bot_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    מציג למשתמש מידע על הנכס הדיגיטלי שלו (אם קיים).
    """
    user = update.effective_user
    if user is None:
        return

    if not DB_AVAILABLE:
        await update.effective_message.reply_text("DB לא פעיל כרגע, נסה מאוחר יותר.")
        return

    summary = get_promoter_summary(user.id)
    personal_link = build_personal_share_link(user.id)

    if not summary:
        await update.effective_message.reply_text(
            "כרגע עדיין לא רשום לך נכס דיגיטלי כמקדם.\n"
            "אם ביצעת תשלום והתקבל אישור – נסה שוב בעוד מספר דקות."
        )
        return

    bank = summary.get("bank_details") or "לא הוגדר"
    p_group = summary.get("personal_group_link") or "לא הוגדר"
    g_group = summary.get("global_group_link") or "לא הוגדר"
    total_ref = summary.get("total_referrals", 0)
    approved_ref = summary.get("approved_referrals", 0)

    text = (
        "📌 *הנכס הדיגיטלי שלך – שער קהילה אישי*\n\n"
        f"🔗 *קישור אישי להפצה:*\n{personal_link}\n\n"
        f"🏦 *פרטי בנק לקבלת תשלום:*\n"
        f"{bank}\n\n"
        f"👥 *קבוצת לקוחות פרטית:*\n"
        f"{p_group}\n\n"
        f"👥 *קבוצת משחק/קהילה כללית:*\n"
        f"{g_group}\n\n"
        f"📊 *סטטוס פעילות:*\n"
        f"- סה\"כ הפניות רשומות: {total_ref}\n"
        f"- מהן אושרו עם תשלום: {approved_ref}\n\n"
        "אפשר לעדכן פרטים בכל רגע עם:\n"
        "/set_bank – עדכון פרטי בנק\n"
        "/set_groups – עדכון קישורי קבוצות"
    )

    await update.effective_message.reply_text(text, parse_mode="Markdown")

async def set_bank_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    עדכון פרטי הבנק של המקדם. שימוש:
    /set_bank <טקסט חופשי עם פרטי החשבון>
    """
    user = update.effective_user
    if user is None:
        return

    if not DB_AVAILABLE:
        await update.effective_message.reply_text("DB לא פעיל כרגע, נסה מאוחר יותר.")
        return

    if not context.args:
        await update.effective_message.reply_text(
            "שלח את הפקודה כך:\n"
            "/set_bank בנק הפועלים, סניף 153, חשבון 73462, המוטב: קאופמן צביקה"
        )
        return

    bank_details = " ".join(context.args).strip()

    # נוודא שקיימת רשומת promoter
    ensure_promoter(user.id)
    update_promoter_settings(user.id, bank_details=bank_details)

    await update.effective_message.reply_text("פרטי הבנק עודכנו בהצלחה ✅")

async def set_groups_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    עדכון קישורי קבוצות. שימוש:
    /set_groups <קישור לקבוצה שלך> <קישור לקבוצת המשחק הכללית (אופציונלי)>
    """
    user = update.effective_user
    if user is None:
        return

    if not DB_AVAILABLE:
        await update.effective_message.reply_text("DB לא פעיל כרגע, נסה מאוחר יותר.")
        return

    if not context.args:
        await update.effective_message.reply_text(
            "שלח את הפקודה כך:\n"
            "/set_groups <קישור לקבוצת הלקוחות שלך> <קישור לקבוצת המשחק הכללית (אופציונלי)>"
        )
        return

    personal_group_link = context.args[0]
    global_group_link = context.args[1] if len(context.args) > 1 else None

    ensure_promoter(user.id)
    update_promoter_settings(
        user.id,
        personal_group_link=personal_group_link,
        global_group_link=global_group_link,
    )

    await update.effective_message.reply_text("קישורי הקבוצות עודכנו בהצלחה ✅")

# =========================
# רישום handlers
# =========================

ptb_app.add_handler(CommandHandler("start", start))
ptb_app.add_handler(CommandHandler("help", help_command))
ptb_app.add_handler(CommandHandler("admin", admin_menu_command))
ptb_app.add_handler(CommandHandler("approve", approve_command))
ptb_app.add_handler(CommandHandler("reject", reject_command))
ptb_app.add_handler(CommandHandler("leaderboard", admin_leaderboard_command))
ptb_app.add_handler(CommandHandler("payments_stats", admin_payments_stats_command))
ptb_app.add_handler(CommandHandler("reward_slh", admin_reward_slh_command))
ptb_app.add_handler(CommandHandler("my_bot", my_bot_command))
ptb_app.add_handler(CommandHandler("set_bank", set_bank_command))
ptb_app.add_handler(CommandHandler("set_groups", set_groups_command))

ptb_app.add_handler(CallbackQueryHandler(digital_asset_info, pattern="^digital_asset_info$"))
ptb_app.add_handler(CallbackQueryHandler(join_callback, pattern="^join$"))
ptb_app.add_handler(CallbackQueryHandler(technical_support_callback, pattern="^technical_support$"))
ptb_app.add_handler(CallbackQueryHandler(contact_admin_callback, pattern="^contact_admin$"))
ptb_app.add_handler(CallbackQueryHandler(help_support_callback, pattern="^help_support$"))
ptb_app.add_handler(CallbackQueryHandler(share_callback, pattern="^share$"))
ptb_app.add_handler(CallbackQueryHandler(vision_callback, pattern="^vision$"))
ptb_app.add_handler(CallbackQueryHandler(back_main_callback, pattern="^back_main$"))
ptb_app.add_handler(CallbackQueryHandler(back_support_callback, pattern="^back_support$"))
ptb_app.add_handler(CallbackQueryHandler(payment_method_callback, pattern="^pay_"))
ptb_app.add_handler(CallbackQueryHandler(my_area_callback, pattern="^my_area$"))
ptb_app.add_handler(CallbackQueryHandler(my_bot_callback, pattern="^my_bot$"))
ptb_app.add_handler(CallbackQueryHandler(admin_approve_callback, pattern="^adm_approve:"))
ptb_app.add_handler(CallbackQueryHandler(admin_reject_callback, pattern="^adm_reject:"))

# handlers לתמיכה טכנית
ptb_app.add_handler(CallbackQueryHandler(report_bug_callback, pattern="^report_bug$"))
ptb_app.add_handler(CallbackQueryHandler(tech_issue_callback, pattern="^tech_issue$"))
ptb_app.add_handler(CallbackQueryHandler(payment_issue_callback, pattern="^payment_issue$"))

# כל תמונה בפרטי – נניח כאישור תשלום
ptb_app.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, handle_payment_photo))

# הודעות תמיכה טכנית
ptb_app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, handle_support_message))

# הודעת טקסט מאדמין – אם יש דחייה ממתינה
ptb_app.add_handler(MessageHandler(filters.TEXT & filters.User(list(ADMIN_IDS)), admin_reject_reason_handler))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
