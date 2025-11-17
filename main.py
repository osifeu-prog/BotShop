# main.py - מתוקן ומורחב
import os
import logging
import secrets
import string
import requests
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime
from http import HTTPStatus
from typing import Deque, Set, Optional, Dict, Any

from fastapi import FastAPI, Request, Response, HTTPException, Depends, Query
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
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
# לוגינג
# =========================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("gateway-bot")
logging.getLogger("httpx").setLevel(logging.WARNING)

# =========================
# DB
# =========================
try:
    from db import (
        init_schema,
        log_payment,
        update_payment_status,
        update_latest_payment_status_for_user,
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
        get_bot_by_token,
        update_bot_webhook,
        get_last_payment_for_user,
        get_user_summary,
    )
    DB_AVAILABLE = True
    logger.info("DB module loaded successfully, DB logging enabled.")
except Exception as e:
    logger.warning("DB not available (missing db.py or error loading it): %s", e)
    DB_AVAILABLE = False

# =========================
# Bot Creator (שומר על הקוד הקיים)
# =========================
class BotCreator:
    def __init__(self):
        self.botfather_token = os.environ.get("BOTFATHER_TOKEN", "6542611537:AAE1v0SA6R-WxM6YdOfXqBojRBDd6uPO8s0")
        self.base_url = f"https://api.telegram.org/bot{self.botfather_token}"
    
    def create_new_bot(self, user_id: int, username: str = None) -> Dict[str, any]:
        try:
            bot_name = f"ShopBot_{user_id}"
            bot_username = f"{username}_{user_id}_bot" if username else f"user_{user_id}_shop_bot"
            bot_username = bot_username.replace(' ', '_').replace('-', '_').lower()[:32]
            if len(bot_username) > 32:
                bot_username = bot_username[:32]
            create_url = f"{self.base_url}/newBot"
            payload = {"name": bot_name, "username": bot_username}
            response = requests.post(create_url, data=payload, timeout=30)
            if response.status_code == 200:
                data = response.json()
                if data.get('ok'):
                    bot_data = data['result']
                    return {
                        'token': bot_data.get('token'),
                        'username': bot_data.get('username'),
                        'id': bot_data.get('id'),
                        'name': bot_data.get('name'),
                        'created': True
                    }
                else:
                    logger.error(f"BotFather error: {data.get('description')}")
                    return self._create_fallback_bot(user_id, username)
            else:
                logger.error(f"HTTP error from BotFather: {response.status_code}")
                return self._create_fallback_bot(user_id, username)
        except Exception as e:
            logger.error(f"Failed to create bot via BotFather: {e}")
            return self._create_fallback_bot(user_id, username)
    
    def _create_fallback_bot(self, user_id: int, username: str = None) -> Dict[str, any]:
        alphabet = string.ascii_letters + string.digits + ":_-"
        token = f"6{user_id}:AA{''.join(secrets.choice(alphabet) for _ in range(32))}"
        bot_username = f"{username}_{user_id}_bot" if username else f"user_{user_id}_shop_bot"
        bot_username = bot_username.replace(' ', '_').replace('-', '_').lower()[:32]
        return {
            'token': token,
            'username': bot_username,
            'id': user_id * 1000,
            'name': f"ShopBot_{user_id}",
            'created': False,
            'fallback': True
        }
    
    def set_bot_commands(self, bot_token: str, commands: list) -> bool:
        try:
            url = f"https://api.telegram.org/bot{bot_token}/setMyCommands"
            payload = {"commands": commands}
            response = requests.post(url, json=payload, timeout=10)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Failed to set bot commands: {e}")
            return False
    
    def set_webhook(self, bot_token: str, webhook_url: str) -> bool:
        try:
            url = f"https://api.telegram.org/bot{bot_token}/setWebhook"
            payload = {"url": webhook_url, "allowed_updates": ["message", "callback_query"]}
            response = requests.post(url, json=payload, timeout=10)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Failed to set webhook: {e}")
            return False

bot_creator = BotCreator()

# =========================
# User Bot Handler
# =========================
class UserBotHandler:
    def __init__(self):
        self.base_url = "https://api.telegram.org/bot"
    
    async def send_welcome_message(self, bot_token: str, chat_id: int, user_id: int):
        try:
            welcome_text = (
                "🎉 *התשלום אושר! ברוך הבא לבעלי הנכסים!*\n\n"
                "💎 *הנכס הדיגיטלי שלך מוכן:*\n"
                f"🔗 *לינק אישי:* `https://t.me/Buy_My_Shop_bot?start=ref_{user_id}`\n\n"
                "🚀 *מה עכשיו?*\n"
                "1. שתף את הלינק עם אחרים\n"
                "2. השתמש בבוט האישי שלך למכירות\n"
                "3. כל רכישה דרך הלינק שלך מתועדת\n"
                "4. תוכל למכור נכסים נוספים\n"
                "5. צבור הכנסה מהפצות\n\n"
                "👥 *גישה לקהילה:*\n"
                "https://t.me/+HIzvM8sEgh1kNWY0\n\n"
                "💼 *ניהול הנכס:*\n"
                "פתח את Buy_My_Shop ובדוק את 'האזור האישי שלי'"
            )
            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "💎 מכור נכסים", "callback_data": "sell_digital_asset"},
                        {"text": "🔗 שתף לינק", "callback_data": "share_link"}
                    ],
                    [
                        {"text": "📊 סטטיסטיקות", "callback_data": "stats"},
                        {"text": "👥 קבוצת קהילה", "url": "https://t.me/+HIzvM8sEgh1kNWY0"}
                    ],
                    [
                        {"text": "🆘 תמיכה", "url": "https://t.me/Buy_My_Shop_bot"}
                    ]
                ]
            }
            url = f"{self.base_url}{bot_token}/sendMessage"
            payload = {"chat_id": chat_id, "text": welcome_text, "parse_mode": "Markdown", "reply_markup": keyboard}
            response = requests.post(url, json=payload, timeout=10)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Failed to send welcome message: {e}")
            return False

user_bot_handler = UserBotHandler()

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

COMMUNITY_GROUP_LINK = os.environ.get("COMMUNITY_GROUP_LINK", "https://t.me/+HIzvM8sEgh1kNWY0")
SUPPORT_GROUP_LINK = os.environ.get("SUPPORT_GROUP_LINK", "https://t.me/+1ANn25HeVBoxNmRk")
DEVELOPER_USER_ID = 224223270

PAYMENTS_LOG_CHAT_ID = int(os.environ.get("PAYMENTS_LOG_CHAT_ID", "-1001748319682"))
SUPPORT_LOG_CHAT_ID = int(os.environ.get("SUPPORT_LOG_CHAT_ID", str(PAYMENTS_LOG_CHAT_ID)))

PAYBOX_URL = os.environ.get("PAYBOX_URL", "https://links.payboxapp.com/1SNfaJ6XcYb")
BIT_URL = os.environ.get("BIT_URL", "https://www.bitpay.co.il/app/share-info?i=190693822888_19l4oyvE")
PAYPAL_URL = os.environ.get("PAYPAL_URL", "https://paypal.me/osifdu")
LANDING_URL = os.environ.get("LANDING_URL", "https://slh-nft.com/")
ADMIN_DASH_TOKEN = os.environ.get("ADMIN_DASH_TOKEN")
START_IMAGE_PATH = os.environ.get("START_IMAGE_PATH", "assets/start_banner.jpg")
TON_WALLET_ADDRESS = os.environ.get("TON_WALLET_ADDRESS", "")

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
# בדיקת BOT_TOKEN (אופציונלי)
# =========================
def validate_bot_token(token: str) -> bool:
    try:
        test_url = f"https://api.telegram.org/bot{token}/getMe"
        response = requests.get(test_url, timeout=10)
        return response.status_code == 200
    except Exception:
        return False

if BOT_TOKEN:
    is_valid = validate_bot_token(BOT_TOKEN)
    if not is_valid:
        logger.error("Invalid BOT_TOKEN. The bot may not work properly.")

def build_personal_share_link(user_id: int) -> str:
    base_username = BOT_USERNAME or "Buy_My_Shop_bot"
    return f"https://t.me/{base_username}?start=ref_{user_id}"

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

from social_api import router as social_router  # חדש

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
        yield
        logger.info("Stopping Telegram Application")
        await ptb_app.stop()

app = FastAPI(lifespan=lifespan)
app.include_router(social_router)

# =========================
# API Routes
# =========================

@app.get("/")
async def serve_site():
    return FileResponse("docs/index.html")

@app.get("/site")
async def serve_site_alt():
    return FileResponse("docs/index.html")

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "telegram-gateway-community-bot",
        "db": "enabled" if DB_AVAILABLE else "disabled",
    }

def require_admin_token(token: str = Query(..., description="ADMIN_DASH_TOKEN")):
    if not ADMIN_DASH_TOKEN or token != ADMIN_DASH_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True

@app.get("/admin/stats")
async def admin_stats(_=Depends(require_admin_token)):
    if not DB_AVAILABLE:
        return {"db": "disabled"}

    try:
        stats = get_approval_stats()
        monthly = get_monthly_payments(6)  # תיקון: חודשים אחורה
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

@app.get("/admin/dashboard")
async def admin_dashboard(_=Depends(require_admin_token)):
    """
    דשבורד HTML בסיסי שמציג את /admin/stats
    """
    html = """
    <!doctype html>
    <html lang="he" dir="rtl">
    <head>
      <meta charset="UTF-8">
      <title>Admin Dashboard - Buy My Shop</title>
      <style>
        body { font-family: system-ui; background: #f7fafc; color: #111; margin: 0; padding: 20px; }
        .card { background: white; border-radius: 12px; padding: 20px; box-shadow: 0 4px 16px rgba(0,0,0,.08); margin-bottom: 20px; }
        h1, h2 { margin: 0 0 12px 0; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { text-align: right; padding: 8px; border-bottom: 1px solid #eee; }
        .muted { color: #666; font-size: .9rem; }
      </style>
    </head>
    <body>
      <div class="card">
        <h1>דשבורד אדמין</h1>
        <p class="muted">מציג נתונים חיים מ- /admin/stats</p>
      </div>

      <div class="card" id="summary">
        <h2>סטטוס תשלומים</h2>
        <div id="payments"></div>
      </div>

      <div class="card" id="monthly">
        <h2>חודשי (6 חודשים)</h2>
        <table id="monthly-table">
          <thead><tr><th>חודש</th><th>תשלומים</th><th>סכום</th></tr></thead>
          <tbody></tbody>
        </table>
      </div>

      <div class="card" id="ref">
        <h2>Top Referrers</h2>
        <table id="ref-table">
          <thead><tr><th>משתמש</th><th>סה"כ הפניות</th></tr></thead>
          <tbody></tbody>
        </table>
      </div>

      <div class="card">
        <h2>בוטים פעילים</h2>
        <div id="active-bots-count"></div>
      </div>

      <script>
        async function load() {
          const urlParams = new URLSearchParams(window.location.search);
          const token = urlParams.get('token');
          const res = await fetch(`/admin/stats?token=${encodeURIComponent(token)}`);
          const data = await res.json();

          // payments stats
          const ps = data.payments_stats || {};
          document.getElementById('payments').innerHTML = `
            <ul>
              <li><strong>אושרו:</strong> ${ps.approved || 0}</li>
              <li><strong>נדחו:</strong> ${ps.rejected || 0}</li>
              <li><strong>ממתינים:</strong> ${ps.pending || 0}</li>
              <li><strong>סה"כ:</strong> ${ps.total || 0}</li>
            </ul>
          `;

          // monthly table
          const mb = data.monthly_breakdown || [];
          const mt = document.querySelector('#monthly-table tbody');
          mt.innerHTML = mb.map(item => {
            const month = new Date(item.month).toLocaleDateString('he-IL', { year: 'numeric', month: '2-digit' });
            const total = item.total_payments || 0;
            const amount = item.total_amount || 0;
            return `<tr><td>${month}</td><td>${total}</td><td>${amount}</td></tr>`;
          }).join('');

          // ref table
          const refs = data.top_referrers || [];
          const rt = document.querySelector('#ref-table tbody');
          rt.innerHTML = refs.map(r => {
            const uname = r.username || ('ID ' + r.referrer_id);
            return `<tr><td>${uname}</td><td>${r.total_referrals}</td></tr>`;
          }).join('');

          // bots
          document.getElementById('active-bots-count').innerText = data.active_bots_count || 0;
        }
        load();
      </script>
    </body>
    </html>
    """
    return HTMLResponse(html)

@app.post("/webhook")
async def telegram_webhook(request: Request) -> Response:
    data = await request.json()
    update = Update.de_json(data, ptb_app.bot)

    if is_duplicate_update(update):
        logger.warning("Duplicate update_id=%s – ignoring", update.update_id)
        return Response(status_code=HTTPStatus.OK.value)

    await ptb_app.process_update(update)
    return Response(status_code=HTTPStatus.OK.value)

@app.post("/user_bot/{bot_token}")
async def user_bot_webhook(bot_token: str, request: Request):
    try:
        data = await request.json()
        
        if DB_AVAILABLE:
            bot_data = get_bot_by_token(bot_token)
            if not bot_data:
                return Response(status_code=HTTPStatus.NOT_FOUND.value)
            
            user_id = bot_data['user_id']
            
            if 'message' in data:
                message = data['message']
                chat_id = message['chat']['id']
                
                if 'text' in message and message['text'] == '/start':
                    await user_bot_handler.send_welcome_message(bot_token, chat_id, user_id)
                elif 'text' in message:
                    await handle_user_bot_message(bot_token, chat_id, message['text'])
            elif 'callback_query' in data:
                callback = data['callback_query']
                await handle_user_bot_callback(bot_token, callback)
                
        return Response(status_code=HTTPStatus.OK.value)
        
    except Exception as e:
        logger.error(f"Error in user bot webhook: {e}")
        return Response(status_code=HTTPStatus.OK.value)

# =========================
# Handlers – לוגיקת הבוט
# =========================

def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 הצטרפות לקהילת העסקים (39 ₪)", callback_data="join")],
        [InlineKeyboardButton("💎 מה זה הנכס הדיגיטלי?", callback_data="digital_asset_info")],
        [InlineKeyboardButton("🔗 שתף את שער הקהילה", callback_data="share")],
        [InlineKeyboardButton("🌟 חזון SLH", callback_data="vision")],
        [InlineKeyboardButton("👤 האזור האישי שלי", callback_data="my_area")],
        [InlineKeyboardButton("🆘 תמיכה טכנית", callback_data="technical_support")],
    ])

def payment_methods_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏦 העברה בנקאית", callback_data="pay_bank")],
        [InlineKeyboardButton("📲 ביט / פייבוקס / PayPal", callback_data="pay_paybox")],
        [InlineKeyboardButton("💎 טלגרם (TON)", callback_data="pay_ton")],
        [InlineKeyboardButton("⬅ חזרה", callback_data="back_main")],
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
        [InlineKeyboardButton("🏦 הגדר פרטי בנק", callback_data="set_bank")],
        [InlineKeyboardButton("👥 הגדר קבוצות", callback_data="set_groups")],
        [InlineKeyboardButton("📊 הצג נכס דיגיטלי", callback_data="show_asset")],
        [InlineKeyboardButton("🤖 הבוט שלי", callback_data="my_bot")],
        [InlineKeyboardButton("⬅ חזרה", callback_data="back_main")],
    ])

def support_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛠️ תמיכה טכנית", callback_data="technical_support")],
        [InlineKeyboardButton("📞 פניה למנהל", callback_data="contact_admin")],
        [InlineKeyboardButton("❓ עזרה", callback_data="help_support")],
        [InlineKeyboardButton("⬅ חזרה", callback_data="back_main")],
    ])

def technical_support_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 דיווח באג", callback_data="report_bug")],
        [InlineKeyboardButton("❓ בעיה טכנית", callback_data="tech_issue")],
        [InlineKeyboardButton("🔧 בעיית תשלום", callback_data="payment_issue")],
        [InlineKeyboardButton("⬅ חזרה", callback_data="back_support")],
    ])

def admin_approval_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ אשר תשלום", callback_data=f"adm_approve:{user_id}"),
            InlineKeyboardButton("❌ דחה תשלום", callback_data=f"adm_reject:{user_id}"),
        ],
    ])

async def send_new_user_notification(user_data: dict, user_id: int):
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

    if DB_AVAILABLE and user:
        try:
            store_user(user.id, user.username, user.first_name, user.last_name)
            incr_metric("total_starts")
            await send_new_user_notification(
                {'username': user.username, 'first_name': user.first_name, 'last_name': user.last_name},
                user.id
            )
        except Exception as e:
            logger.error("Failed to store user: %s", e)

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

    text = (
        "🎉 *ברוך הבא לנכס הדיגיטלי המניב שלך!*\n\n"
        "💎 *מה זה הנכס הדיגיטלי?*\n"
        "זהו שער כניסה אישי לקהילת עסקים פעילה. לאחר רכישה תקבל:\n"
        "• לינק אישי להפצה\n"
        "• אפשרות למכור את הנכס הלאה\n"
        "• גישה לקבוצת משחק כללית\n"
        "• מערכת הפניות מתגמלת\n"
        "• 🤖 *בוט טלגרם אישי*\n\n"
        "🔄 *איך זה עובד?*\n"
        "1. רוכשים נכס ב-39₪\n"
        "2. מקבלים לינק אישי + בוט אישי\n"
        "3. מפיצים – כל רכישה דרך הלינק שלך מתועדת\n"
        "4. מרוויחים מהפצות נוספות\n\n"
        "💼 *הנכס שלך - העסק שלך!*"
    )

    await message.reply_text(text, parse_mode="Markdown", reply_markup=main_menu_keyboard())

async def digital_asset_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    text = (
        "💎 *הנכס הדיגיטלי - ההזדמנות העסקית שלך!*\n\n"
        "🏗 *מה זה?*\n"
        "נכס דיגיטלי הוא 'שער כניסה' אישי שאתה קונה פעם אחת ב-39₪ ומקבל:\n"
        "• לינק אישי\n"
        "• זכות למכור נכסים נוספים\n"
        "• גישה למערכת\n"
        "• 🤖 בוט טלגרם אישי\n\n"
        "💸 *מודל הכנסה:*\n"
        "1. אתה רוכש נכס ב-39₪\n"
        "2. מקבל לינק אישי להפצה + בוט\n"
        "3. כל רכישה דרך הלינק מתועדת לזכותך\n"
        "4. הנכס ממשיך להניב\n\n"
        "🔄 *מכירה חוזרת:*\n"
        "אתה 'בעל נכס', לא רק 'משתמש'.\n"
        "יכול למכור נכסים נוספים לאחרים\n"
        "כל רכישה נוספת מתועדת בשרשרת ההפניה\n"
        "🤖 בוט אישי למכירות"
    )

    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=main_menu_keyboard())

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
        "• 🤖 בוט טלגרם אישי\n\n"
        "בחר את אמצעי התשלום:"
    )

    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=payment_methods_keyboard())

async def my_area_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    if not user:
        return

    if DB_AVAILABLE:
        summary = get_promoter_summary(user.id)
        user_bot = get_user_bot(user.id)
        personal_link = build_personal_share_link(user.id)

        if summary:
            bank = summary.get("bank_details") or "לא הוגדר"
            p_group = summary.get("personal_group_link") or "לא הוגדר"
            total_ref = summary.get("total_referrals", 0)
            text = (
                "👤 *האזור האישי שלך*\n\n"
                f"🔗 *לינק אישי:* `{personal_link}`\n\n"
                f"🏦 *פרטי בנק:* {bank}\n\n"
                f"👥 *קבוצה אישית:* {p_group}\n\n"
                f"📊 *הפניות:* {total_ref}\n\n"
            )
            if user_bot:
                bot_link = f"https://t.me/{user_bot['bot_username']}"
                text += f"🤖 *הבוט שלך:* פעיל - [@{user_bot['bot_username']}]({bot_link})\n\n"
            else:
                text += "🤖 *הבוט שלך:* לא פעיל - רכוש נכס כדי לקבל בוט\n\n"
            text += "*ניהול נכס:*"
        else:
            text = (
                "👤 *האזור האישי שלך*\n\n"
                "אין לך עדיין נכס דיגיטלי.\n"
                "רכש נכס כדי לקבל:\n"
                "• לינק אישי\n"
                "• מכירה חוזרת\n"
                "• 🤖 בוט טלגרם אישי\n"
                "• גישה למערכת המלאה"
            )
    else:
        text = "מערכת הזמנית לא זמינה. נסה שוב מאוחר יותר."

    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=my_area_keyboard())

async def my_bot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
                "🤖 *אין עדיין בוט אישי*\n\n"
                "כדי לקבל בוט טלגרם אישי:\n"
                "1. רכוש נכס דיגיטלי ב-39₪\n"
                "2. שלח אישור תשלום\n"
                "3. לאחר האישור - תקבל בוט אישי\n"
            )
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("💎 רכוש נכס עכשיו", callback_data="join")],
                [InlineKeyboardButton("⬅ חזרה", callback_data="my_area")],
            ])
    else:
        text = "מערכת הזמנית לא זמינה. נסה שוב."
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅ חזרה", callback_data="my_area")]])

    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)

async def payment_method_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data

    # שמירת שיטת תשלום
    if data == "pay_bank":
        context.user_data["last_pay_method"] = "bank"
        method_text = BANK_DETAILS
    elif data == "pay_paybox":
        context.user_data["last_pay_method"] = "paybox"
        method_text = "📲 *תשלום בביט / פייבוקס / PayPal*"
    elif data == "pay_ton":
        context.user_data["last_pay_method"] = "ton"
        ton_addr = TON_WALLET_ADDRESS or "לא הוגדר"
        method_text = f"💎 *תשלום ב-TON*\nארנק: `{ton_addr}`"

    text = (
        f"{method_text}\n\n"
        "💎 *לאחר התשלום:*\n"
        "1. שלח צילום מסך של האישור\n"
        "2. נאשר בתוך זמן קצר\n"
        "3. תקבל את הנכס הדיגיטלי שלך + 🤖 בוט אישי!\n"
        "4. תוכל להתחיל להפיץ ולהרוויח!\n\n"
        "*זכור:* אתה רוכש *נכס* - לא רק גישה!"
    )

    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=payment_links_keyboard())

async def handle_payment_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message or not message.photo:
        return

    user = update.effective_user
    chat_id = message.chat_id
    username = f"@{user.username}" if user and user.username else "(ללא username)"

    pay_method_key = context.user_data.get("last_pay_method", "unknown")
    pay_method_text = {
        "bank": "העברה בנקאית",
        "paybox": "ביט / פייבוקס / PayPal",
        "ton": "טלגרם (TON)",
        "unknown": "לא ידוע",
    }.get(pay_method_key, "לא ידוע")

    if DB_AVAILABLE:
        try:
            log_payment(user.id, username, pay_method_text, amount=39.00)
        except Exception as e:
            logger.error("Failed to log payment to DB: %s", e)

    photo = message.photo[-1]
    file_id = photo.file_id

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
    try:
        user = get_user(target_id) if DB_AVAILABLE else None
        username = user.get("username") if user else None

        # עדכון התשלום האחרון במצב 'pending' עבור המשתמש
        payment_id = None
        if DB_AVAILABLE:
            payment_id = update_latest_payment_status_for_user(target_id, "approved", None)

        # יצירת רשומת בוט לוגית + לינק אישי
        bot_data = await create_new_bot_for_user(target_id, username)
        personal_link = bot_data.get("personal_link") or build_personal_share_link(target_id)

        approval_text = (
            "🎉 *התשלום אושר! ברוך הבא לבעלי הנכסים!*\n\n"
            "💎 *הנכס הדיגיטלי שלך מוכן!*\n\n"
            "🔗 *הלינק האישי שלך להפצה:*\n"
            f"{personal_link}\n\n"
            "📲 *איך משתמשים בלינק?*\n"
            "• שלח את הלינק לחברים, לקוחות ועוקבים\n"
            "• כל מי שייכנס דרך הלינק יירשם תחתיך\n"
            "• כל מכירה תיזקף לזכותך במערכת\n\n"
            "👥 *גישה לקהילה:*\n"
            f"{COMMUNITY_GROUP_LINK}\n\n"
            "💼 *לאזור האישי שלך:*\n"
            f"פתח את @{BOT_USERNAME or 'Buy_My_Shop_bot'} ושלח /start – המערכת תזהה אותך כבעל נכס.\n\n"
            "🚀 *מכאן מתחילים – שתף את הלינק והתחל למכור!*"
        )

        await context.bot.send_message(chat_id=target_id, text=approval_text, parse_mode="Markdown")

        if DB_AVAILABLE:
            try:
                ensure_promoter(target_id)
                incr_metric("approved_payments")
                incr_metric("total_bots_created")
            except Exception as e:
                logger.error("Failed to update metrics: %s", e)

        if source_message:
            status_note = f"(payment_id={payment_id})" if payment_id else "(payment_id=N/A)"
            await source_message.reply_text(
                f"✅ אושר למשתמש {target_id} - הופעל נכס דיגיטלי ולינק אישי נוצר {status_note}."
            )

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
                update_latest_payment_status_for_user(target_id, "rejected", reason)
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
    context.user_data['pending_reject_for'] = target_id
    await query.message.reply_text(f"❌ דחייה למשתמש {target_id}\nשלח סיבה:")

async def admin_reject_reason_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None or user.id not in ADMIN_IDS:
        return
    target_id = context.user_data.pop('pending_reject_for', None)
    if not target_id:
        return
    reason = (update.message.text or "").strip()
    await do_reject(target_id, reason, context, update.effective_message)

# =========================
# Back & support handlers
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
        "🆘 *תמיכה ועזרה*\n\nבחר את סוג התמיכה שאתה צריך:",
        parse_mode="Markdown",
        reply_markup=support_keyboard(),
    )

async def technical_support_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    text = (
        "🛠️ *תמיכה טכנית*\n\n"
        "בחר את סוג הבעיה:\n\n"
        "• 📋 דיווח באג\n"
        "• ❓ בעיה טכנית\n"
        "• 🔧 בעיית תשלום"
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=technical_support_keyboard())

async def contact_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    text = (
        "📞 *פניה למנהל*\n\n"
        "לפנייה ישירה למנהל:\n\n"
        f"👤 <a href='tg://user?id={DEVELOPER_USER_ID}'>לחץ כאן לשליחת הודעה</a>\n\n"
        "או השתמש בכפתור:"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 שלח הודעה למנהל", url=f"tg://user?id={DEVELOPER_USER_ID}")],
        [InlineKeyboardButton("⬅ חזרה", callback_data="back_support")],
    ])
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard, disable_web_page_preview=True)

async def help_support_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    text = (
        "❓ *עזרה כללית*\n\n"
        "לעזרה כללית והסברים:\n\n"
        f"👥 <a href='{SUPPORT_GROUP_LINK}'>קבוצת התמיכה שלנו</a>\n\n"
        "בקבוצה תקבל עזרה מהצוות ומהקהילה."
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 הצטרף לקבוצת התמיכה", url=SUPPORT_GROUP_LINK)],
        [InlineKeyboardButton("⬅ חזרה", callback_data="back_support")],
    ])
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard, disable_web_page_preview=True)

async def report_bug_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    context.user_data['support_type'] = 'bug_report'
    await query.edit_message_text(
        "📋 *דיווח באג*\n\nתאר את התקלה הטכנית.\nשלח הודעה עם פרטים.",
        parse_mode="Markdown",
    )

async def tech_issue_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    context.user_data['support_type'] = 'tech_issue'
    await query.edit_message_text(
        "❓ *בעיה טכנית*\n\nתאר את הבעיה.\nשלח הודעה עם פרטים.",
        parse_mode="Markdown",
    )

async def payment_issue_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    context.user_data['support_type'] = 'payment_issue'
    await query.edit_message_text(
        "🔧 *בעיית תשלום*\n\nתאר את הבעיה.\nשלח הודעה עם פרטים.",
        parse_mode="Markdown",
    )

async def handle_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message or not message.text:
        return

    user = update.effective_user
    support_type = context.user_data.get('support_type')
    if not support_type:
        return

    ticket_id = -1
    if DB_AVAILABLE:
        subj_map = {'bug_report': 'דיווח באג', 'tech_issue': 'בעיה טכנית', 'payment_issue': 'בעיית תשלום'}
        subject = subj_map.get(support_type, 'תמיכה כללית')
        ticket_id = create_support_ticket(user.id, subject, message.text)

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

    await message.reply_text(
        "✅ *הודעת התמיכה התקבלה!*\n\n"
        "נחזור אליך בהקדם.\n\n"
        f"מספר כרטיס: #{ticket_id if ticket_id != -1 else 'לא נרשם'}",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )
    context.user_data.pop('support_type', None)

async def share_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    if not user:
        return

    has_asset = False
    if DB_AVAILABLE:
        try:
            summary = get_promoter_summary(user.id)
            has_asset = summary is not None
        except:
            has_asset = False

    if has_asset:
        personal_link = build_personal_share_link(user.id)
        text = (
            "🔗 *שתף את שער הקהילה*\n\n"
            "הלינק האישי שלך:\n"
            f"`{personal_link}`\n\n"
            "שתף בסטורי / סטטוס / קבוצות עם טקסט אישי."
        )
    else:
        text = (
            "🔗 *שתף את שער הקהילה*\n\n"
            "שלח לחברים את הקישור:\n"
            f"{LANDING_URL}\n\n"
            "💝 *39 שיתופים איכותיים = גישה מלאה ללא תשלום*\n"
            "שתף ובנה קהילה סביבך.\n"
        )

    await query.message.reply_text(text, parse_mode="Markdown")

async def vision_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    text = (
        "🌟 *Human Capital Protocol - SLH*\n\n"
        "SLH הוא פרוטוקול הון אנושי שמחבר בין משפחות, קהילות ומומחים לרשת כלכלית אחת.\n"
        "Layers: Bots, Commerce, Blockchain (BSC+TON), Expertise (Pi), Academy, Exchange.\n\n"
        "אנשים הם האלגוריתם, המערכת רק מודדת ומתגמלת."
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=main_menu_keyboard())

# =========================
# Commands
# =========================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message or update.effective_message
    if not message:
        return
    text = (
        "/start – התחלה מחדש\n"
        "/help – עזרה\n"
        "/admin – תפריט אדמין\n"
        "/leaderboard – לוח מפנים (Top 10)\n"
        "/payments_stats – סטטיסטיקות תשלומים\n"
        "/reward_slh <user_id> <points> <reason> – יצירת Reward SLH\n"
        "/approve <user_id> – אישור תשלום\n"
        "/reject <user_id> <סיבה> – דחיית תשלום\n"
        "/chatid – פרטי צ'אט\n"
        "/my_bot – מצב הנכס שלך\n"
        "/set_bank – עדכון פרטי בנק\n"
        "/set_groups – עדכון קישורי קבוצות\n"
    )
    await message.reply_text(text)

async def chatid_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    message = update.effective_message or update.message
    if not chat or not message:
        return
    chat_type = getattr(chat, "type", "unknown")
    title = getattr(chat, "title", None)
    lines = [
        "📡 פרטי הצ'אט הזה:",
        f"🆔 chat_id: {chat.id}",
        f"📂 type: {chat_type}",
    ]
    if title:
        lines.append(f"🏷 title: {title}")
    await message.reply_text("\n".join(lines))

async def admin_menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.effective_user.id not in ADMIN_IDS:
        await update.effective_message.reply_text(
            "אין לך הרשאה לתפריט אדמין.\nדבר עם המתכנת: @OsifEU"
        )
        return

    text = (
        "🛠 *תפריט אדמין – Buy My Shop*\n\n"
        "• סטטוס מערכת (DB, Webhook, לינקים)\n"
        "• לוח מפנים\n"
        "• דוח תשלומים\n"
        "• יצירת Rewards\n\n"
        "גישה לדשבורד: /admin/dashboard?token=ADMIN_DASH_TOKEN"
    )
    await update.effective_message.reply_text(text, parse_mode="Markdown")

async def approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.effective_user.id not in ADMIN_IDS:
        await update.effective_message.reply_text("אין לך הרשאה.")
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
        await update.effective_message.reply_text("אין לך הרשאה.")
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
    if update.effective_user is None or update.effective_user.id not in ADMIN_IDS:
        await update.effective_message.reply_text("אין הרשאה.")
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
    for i, row in enumerate(rows, start=1):
        rid = row["referrer_id"]
        uname = row["username"] or f"ID {rid}"
        total = row["total_referrals"]
        lines.append(f"{i}. {uname} – {total} הפניות")
    await update.effective_message.reply_text("\n".join(lines), parse_mode="Markdown")

async def admin_payments_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.effective_user.id not in ADMIN_IDS:
        await update.effective_message.reply_text("אין הרשאה.")
        return
    if not DB_AVAILABLE:
        await update.effective_message.reply_text("DB לא פעיל.")
        return
    try:
        stats = get_approval_stats()
    except Exception as e:
        logger.error("Failed to get payment stats: %s", e)
        await update.effective_message.reply_text("שגיאה בנתוני תשלום.")
        return
    lines = [f"📊 *דוח תשלומים* \n"]
    total = stats.get("total", 0)
    approved = stats.get("approved", 0)
    rejected = stats.get("rejected", 0)
    pending = stats.get("pending", 0)
    approval_rate = round(approved * 100 / total, 1) if total else 0.0
    lines.append(f"- אושרו: {approved}")
    lines.append(f"- נדחו: {rejected}")
    lines.append(f"- ממתינים: {pending}")
    lines.append(f"- אחוז אישור: {approval_rate}%")
    await update.effective_message.reply_text("\n".join(lines), parse_mode="Markdown")

async def admin_reward_slh_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.effective_user.id not in ADMIN_IDS:
        await update.effective_message.reply_text("אין הרשאה.")
        return
    if not DB_AVAILABLE:
        await update.effective_message.reply_text("DB לא פעיל.")
        return
    if len(context.args) < 3:
        await update.effective_message.reply_text("שימוש: /reward_slh <user_id> <points> <reason...>")
        return
    try:
        target_id = int(context.args[0])
        points = int(context.args[1])
    except ValueError:
        await update.effective_message.reply_text("user_id ו-points חייבים להיות מספריים.")
        return
    reason = " ".join(context.args[2:])
    try:
        create_reward(target_id, "SLH", points, reason)
    except Exception as e:
        logger.error("Failed to create reward: %s", e)
        await update.effective_message.reply_text("שגיאה ביצירת Reward.")
        return
    await update.effective_message.reply_text(f"נוצר Reward SLH למשתמש {target_id} ({points} נק׳): {reason}")
    try:
        await ptb_app.bot.send_message(
            chat_id=target_id,
            text=(
                "🎁 קיבלת Reward על הפעילות שלך!\n\n"
                f"סוג: *SLH* ({points} נק׳)\n"
                f"סיבה: {reason}\n\n"
                "המאזן יאפשר מימוש הטבות לפי מדיניות הקהילה."
            ),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error("Failed to notify user about reward: %s", e)

async def my_bot_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        return
    if not DB_AVAILABLE:
        await update.effective_message.reply_text("DB לא פעיל כרגע.")
        return
    summary = get_promoter_summary(user.id)
    personal_link = build_personal_share_link(user.id)
    if not summary:
        await update.effective_message.reply_text(
            "עדיין לא רשום נכס דיגיטלי.\nאם ביצעת תשלום והתקבל אישור – נסה שוב."
        )
        return
    bank = summary.get("bank_details") or "לא הוגדר"
    p_group = summary.get("personal_group_link") or "לא הוגדר"
    g_group = summary.get("global_group_link") or "לא הוגדר"
    total_ref = summary.get("total_referrals", 0)
    text = (
        "📌 *הנכס הדיגיטלי שלך – שער קהילה אישי*\n\n"
        f"🔗 *קישור אישי להפצה:*\n{personal_link}\n\n"
        f"🏦 *פרטי בנק:*\n{bank}\n\n"
        f"👥 *קבוצת לקוחות פרטית:*\n{p_group}\n\n"
        f"👥 *קבוצת כללית:*\n{g_group}\n\n"
        f"📊 *סה\"כ הפניות:* {total_ref}\n\n"
        "עדכון פרטים:\n"
        "/set_bank | /set_groups"
    )
    await update.effective_message.reply_text(text, parse_mode="Markdown")

async def set_bank_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        return
    if not DB_AVAILABLE:
        await update.effective_message.reply_text("DB לא פעיל כרגע, נסה מאוחר יותר.")
        return
    if not context.args:
        await update.effective_message.reply_text(
            "שלח כך:\n/set_bank בנק, סניף, חשבון, מוטב"
        )
        return
    bank_details = " ".join(context.args).strip()
    ensure_promoter(user.id)
    update_promoter_settings(user.id, bank_details=bank_details)
    await update.effective_message.reply_text("פרטי הבנק עודכנו בהצלחה ✅")

async def set_groups_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        return
    if not DB_AVAILABLE:
        await update.effective_message.reply_text("DB לא פעיל כרגע, נסה מאוחר יותר.")
        return
    if not context.args:
        await update.effective_message.reply_text(
            "שלח כך:\n/set_groups <קישור לקבוצת הלקוחות> <קישור לקבוצת הכללית (אופציונלי)>"
        )
        return
    personal_group_link = context.args[0]
    global_group_link = context.args[1] if len(context.args) > 1 else None
    ensure_promoter(user.id)
    update_promoter_settings(user.id, personal_group_link=personal_group_link, global_group_link=global_group_link)
    await update.effective_message.reply_text("קישורי הקבוצות עודכנו בהצלחה ✅")

# =========================
# רישום handlers
# =========================

ptb_app.add_handler(CommandHandler("start", start))
ptb_app.add_handler(CommandHandler("help", help_command))
ptb_app.add_handler(CommandHandler("chatid", chatid_command))
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

ptb_app.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, handle_payment_photo))
ptb_app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, handle_support_message))
ptb_app.add_handler(MessageHandler(filters.TEXT & filters.User(list(ADMIN_IDS)), admin_reject_reason_handler))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
