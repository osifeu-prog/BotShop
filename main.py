#!/usr/bin/env python3
"""
שער קהילת העסקים - Buy My Shop
בוט טלגרם מתקדם עם FastAPI, ניהול תשלומים, מערכת הפניות, דשבורד ניהול וממשק API

פונקציונליות עיקרית:
- ניהול תשלומים עם אישור ידני
- מערכת הפניות (referrals) עם ניקוד
- דשבורד ניהול למארגנים
- ממשק API לסטטיסטיקות
- הגנה מפני כפילות ועומסים
- תמיכה במספר שיטות תשלום
- אינטגרציה עם DB (אופציונלי)
- ממשק וובי לניהול
"""

import asyncio
import os
import logging
import json
import secrets
from collections import deque, defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from http import HTTPStatus
from typing import Deque, Set, Literal, Optional, Dict, Any, List, Tuple, Union
from pathlib import Path
import uuid
import hashlib

import httpx
from fastapi import FastAPI, Request, Response, HTTPException, Depends, Form, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    BotCommand,
    User as TelegramUser,
    Chat as TelegramChat
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    PicklePersistence,
    JobQueue
)
from telegram.error import TelegramError, NetworkError

# =========================
# קונפיגורציה מתקדמת
# =========================

# הגדרות לוגינג מתקדמות
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("gateway-bot")

# הגדרות סביבה עם ברירות מחדל
class Config:
    """מחלקה לניהול הגדרות המערכת"""
    
    def __init__(self):
        self.BOT_TOKEN = os.environ.get("BOT_TOKEN")
        self.WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
        self.ADMIN_DASH_TOKEN = os.environ.get("ADMIN_DASH_TOKEN", secrets.token_urlsafe(32))
        
        # AI / מודלים / הגדרות נוספות מה-ENV (לא חובה לשימוש מיידי)
        self.AI_ENABLE = os.environ.get("AI_ENABLE", "false").lower() == "true"
        self.AI_DAILY_QUOTA_FREE = int(os.environ.get("AI_DAILY_QUOTA_FREE", "0") or 0)
        self.AI_DAILY_QUOTA_PAID = int(os.environ.get("AI_DAILY_QUOTA_PAID", "0") or 0)
        self.AI_POINTS_THRESHOLD = int(os.environ.get("AI_POINTS_THRESHOLD", "0") or 0)
        self.OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
        self.HF_TOKEN = os.environ.get("HF_TOKEN")
        self.HF_TEXT_MODEL = os.environ.get("HF_TEXT_MODEL", "")
        self.HF_IMAGE_MODEL = os.environ.get("HF_IMAGE_MODEL", "")
        self.DEFAULT_LANG = os.environ.get("DEFAULT_LANG", "he")
        self.SLH_NIS = float(os.environ.get("SLH_NIS", "0") or 0.0)
        self.BOT_USERNAME = os.environ.get("BOT_USERNAME")
        self.GIT_REPO_URL = os.environ.get("GIT_REPO_URL")
        self.GROUP_STATIC_INVITE = os.environ.get("GROUP_STATIC_INVITE")

        # URLs עם ברירות מחדל
        self.PAYBOX_URL = os.environ.get("PAYBOX_URL", "https://links.payboxapp.com/1SNfaJ6XcYb")
        self.BIT_URL = os.environ.get("BIT_URL", "https://www.bitpay.co.il/app/share-info?i=190693822888_19l4oyvE")
        self.PAYPAL_URL = os.environ.get("PAYPAL_URL", "https://paypal.me/osifdu")
        self.LANDING_URL = os.environ.get("LANDING_URL", "https://osifeu-prog.github.io/botshop/")
        
        # קבוצות
        self.COMMUNITY_GROUP_LINK = "https://t.me/+HIzvM8sEgh1kNWY0"
        self.COMMUNITY_GROUP_ID = -1002981609404
        self.SUPPORT_GROUP_LINK = "https://t.me/+1ANn25HeVBoxNmRk"
        self.SUPPORT_GROUP_ID = -1001651506661
        self.PAYMENTS_LOG_CHAT_ID = -1001748319682
        
        # משתמשים
        self.DEVELOPER_USER_ID = 224223270
        self.ADMIN_IDS = {self.DEVELOPER_USER_ID}
        
        # קבצים
        self.START_IMAGE_PATH = os.environ.get("START_IMAGE_PATH", "assets/start_banner.jpg")
        self.DATA_DIR = Path("data")
        self.BACKUP_DIR = self.DATA_DIR / "backups"
        
        # הגדרות אבטחה
        self.RATE_LIMIT_WINDOW = 60  # שניות
        self.MAX_REQUESTS_PER_WINDOW = 10
        self.SESSION_TIMEOUT = 30 * 60  # 30 דקות
        
        # הגדרות עסקים
        self.JOIN_FEE = 39  # ש"ח
        self.REFERRAL_BONUS = 5  # נקודות לכל הפניה
        self.MIN_PAYOUT = 100  # נקודות מינימום למשיכה
        
        # אתחול תיקיות
        self._init_directories()
    
    def _init_directories(self):
        """יצירת תיקיות נדרשות"""
        self.DATA_DIR.mkdir(exist_ok=True)
        self.BACKUP_DIR.mkdir(exist_ok=True)
        (self.DATA_DIR / "sessions").mkdir(exist_ok=True)
        
    def validate(self):
        """וידוא שהגדרות חובה קיימות"""
        if not self.BOT_TOKEN:
            raise RuntimeError("BOT_TOKEN environment variable is not set")
        if not self.WEBHOOK_URL:
            raise RuntimeError("WEBHOOK_URL environment variable is not set")
        
        logger.info("Configuration loaded successfully")
        return self

config = Config().validate()

# =========================
# מודלים של נתונים
# =========================

class PaymentRequest(BaseModel):
    """מודל לבקשת תשלום"""
    user_id: int
    amount: float
    currency: str = "ILS"
    method: str
    description: Optional[str] = None

class UserStats(BaseModel):
    """מודל לסטטיסטיקות משתמש"""
    user_id: int
    username: Optional[str]
    join_date: datetime
    total_referrals: int = 0
    total_points: int = 0
    payments_count: int = 0
    last_activity: datetime

class SystemStatus(BaseModel):
    """מודל לסטטוס מערכת"""
    db_status: str
    bot_status: str
    webhook_status: str
    active_users_24h: int
    pending_payments: int
    total_earnings: float

class AdminAuth(BaseModel):
    """מודל לאימות אדמין"""
    token: str

# =========================
# DB אופציונלי (db.py) - גרסה משופרת
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
        get_user_stats,
        get_system_stats,
        log_admin_action,
        get_recent_activities,
        # פונקציות חדשות
        backup_database,
        cleanup_old_data,
        get_user_payments_history,
        update_user_balance,
        create_support_ticket,
        update_support_ticket,
        get_pending_tickets,
        log_audit_event
    )
    DB_AVAILABLE = True
    logger.info("DB module loaded successfully with extended features")
except Exception as e:
    logger.warning("DB not available (missing db.py or error loading it): %s", e)
    DB_AVAILABLE = False
    
    # יצירת פונקציות דמה למקרה ש-DB לא זמין
    def create_dummy_function(name):
        def dummy(*args, **kwargs):
            logger.warning(f"DB not available - {name} called but ignored")
            return [] if "get" in name else None
        return dummy
    
    # אתחול פונקציות דמה
    for func_name in [
        'init_schema', 'log_payment', 'update_payment_status', 'store_user', 
        'add_referral', 'get_top_referrers', 'get_monthly_payments', 
        'get_approval_stats', 'create_reward', 'increment_metric', 'get_metric',
        'get_user_stats', 'get_system_stats', 'log_admin_action', 'get_recent_activities',
        'backup_database', 'cleanup_old_data', 'get_user_payments_history',
        'update_user_balance', 'create_support_ticket', 'update_support_ticket',
        'get_pending_tickets', 'log_audit_event'
    ]:
        globals()[func_name] = create_dummy_function(func_name)

# =========================
# ניהול State ו-Cache מתקדם
# =========================

class RateLimiter:
    """מגביל קצב בקשות למניעת התקפות"""
    
    def __init__(self):
        self.requests = defaultdict(list)
    
    def is_limited(self, key: str, max_requests: int, window: int) -> bool:
        """בודק אם המשתמש חורג ממגבלת הקצב"""
        now = datetime.now()
        window_start = now - timedelta(seconds=window)
        
        # ניקוי בקשות ישנות
        self.requests[key] = [req_time for req_time in self.requests[key] if req_time > window_start]
        
        # בדיקת מגבלה
        if len(self.requests[key]) >= max_requests:
            return True
        
        self.requests[key].append(now)
        return False

class SessionManager:
    """מנהל סשנים למשתמשים"""
    
    def __init__(self):
        self.sessions = {}
        self.timeout = config.SESSION_TIMEOUT
    
    def create_session(self, user_id: int, data: Dict[str, Any] = None) -> str:
        """יצירת סשן חדש"""
        session_id = secrets.token_urlsafe(32)
        self.sessions[session_id] = {
            'user_id': user_id,
            'created_at': datetime.now(),
            'data': data or {}
        }
        return session_id
    
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """קבלת סשן"""
        session = self.sessions.get(session_id)
        if not session:
            return None
        
        # בדיקת תוקף
        if datetime.now() - session['created_at'] > timedelta(seconds=self.timeout):
            del self.sessions[session_id]
            return None
        
        return session
    
    def cleanup_expired(self):
        """ניקוי סשנים שפג תוקפם"""
        now = datetime.now()
        expired = []
        for session_id, session in self.sessions.items():
            if now - session['created_at'] > timedelta(seconds=self.timeout):
                expired.append(session_id)
        
        for session_id in expired:
            del self.sessions[session_id]

# אתחול מנהלים
rate_limiter = RateLimiter()
session_manager = SessionManager()

# =========================
# Dedup – מניעת כפילות מתקדמת
# =========================

class DedupManager:
    """מנהל מניעת כפילות עם cleanup אוטומטי"""
    
    def __init__(self, max_size: int = 5000):
        self.processed_ids: Deque[int] = deque(maxlen=max_size)
        self.processed_set: Set[int] = set()
        self.max_size = max_size
        
    def is_duplicate(self, update_id: int) -> bool:
        """בודק אם update כבר טופל"""
        if update_id in self.processed_set:
            return True
        
        self.processed_set.add(update_id)
        self.processed_ids.append(update_id)
        
        # ניקוי אוטומטי אם הסט גדול מדי
        if len(self.processed_set) > self.max_size + 100:
            self._cleanup()
            
        return False
    
    def _cleanup(self):
        """ניקוי סט לפי ה-deque"""
        valid_ids = set(self.processed_ids)
        self.processed_set.intersection_update(valid_ids)

dedup_manager = DedupManager()

def is_duplicate_update(update: Update) -> bool:
    """בודק אם update כבר טופל (ע״פ update_id)"""
    if update is None or update.update_id is None:
        return False
    return dedup_manager.is_duplicate(update.update_id)

# =========================
# זיכרון פשוט לתשלומים + State
# =========================

class PaymentManager:
    """מנהל תשלומים בזיכרון"""
    
    def __init__(self):
        self.payments = {}
        self.pending_rejects = {}
        self.user_states = {}
        
    def get_payments_store(self, context: ContextTypes.DEFAULT_TYPE) -> Dict[int, Dict[str, Any]]:
        """קבלת מאגר התשלומים"""
        store = context.application.bot_data.get("payments")
        if store is None:
            store = {}
            context.application.bot_data["payments"] = store
        return store
    
    def get_pending_rejects(self, context: ContextTypes.DEFAULT_TYPE) -> Dict[int, int]:
        """קבלת רשימת דחיות ממתינות"""
        store = context.application.bot_data.get("pending_rejects")
        if store is None:
            store = {}
            context.application.bot_data["pending_rejects"] = store
        return store
    
    def set_user_state(self, user_id: int, state: str, data: Dict = None):
        """הגדרת state למשתמש"""
        self.user_states[user_id] = {
            'state': state,
            'data': data or {},
            'timestamp': datetime.now()
        }
    
    def get_user_state(self, user_id: int) -> Optional[Dict]:
        """קבלת state של משתמש"""
        state_data = self.user_states.get(user_id)
        if not state_data:
            return None
        
        # בדיקת תוקף state
        if datetime.now() - state_data['timestamp'] > timedelta(minutes=30):
            del self.user_states[user_id]
            return None
        
        return state_data
    
    def clear_user_state(self, user_id: int):
        """ניקוי state של משתמש"""
        if user_id in self.user_states:
            del self.user_states[user_id]

payment_manager = PaymentManager()

# =========================
# אפליקציית Telegram עם persistence
# =========================

try:
    # ניסיון להשתמש ב-persistence
    persistence = PicklePersistence(filepath="bot_data.pickle")
    logger.info("Using PicklePersistence for bot data")
except Exception as e:
    logger.warning("Failed to initialize persistence: %s. Using in-memory storage.", e)
    persistence = None

ptb_app: Application = (
    Application.builder()
    .updater(None)  # אין polling – רק webhook
    .token(config.BOT_TOKEN)
    .persistence(persistence)
    .concurrent_updates(True)  # תמיכה ב-concurrent updates
    .build()
)

# =========================
# מערכת קומנדות אוטומטית
# =========================

async def setup_commands():
    """הגדרת פקודות הבוט בטלגרם"""
    commands = [
        BotCommand("start", "התחל - שער הכניסה לקהילה"),
        BotCommand("help", "עזרה והסברים"),
        BotCommand("status", "סטטוס המשתמש שלי"),
        BotCommand("referral", "קישור ההפניה שלי"),
    ]
    
    # הוספת פקודות אדמין
    admin_commands = [
        BotCommand("admin", "תפריט ניהול"),
        BotCommand("stats", "סטטיסטיקות מערכת"),
        BotCommand("approve", "אשר תשלום"),
        BotCommand("reject", "דחה תשלום"),
    ]
    
    try:
        await ptb_app.bot.set_my_commands(commands)
        logger.info("Bot commands set up successfully")
    except Exception as e:
        logger.error("Failed to set up bot commands: %s", e)

# =========================
# עזרי UI מתקדמים (מקשים ודפים)
# =========================

def main_menu_keyboard(user_id: int = None) -> InlineKeyboardMarkup:
    """תפריט ראשי מותאם אישית"""
    buttons = [
        [
            InlineKeyboardButton("🚀 הצטרפות לקהילת העסקים (39 ₪)", callback_data="join"),
        ],
        [
            InlineKeyboardButton("ℹ מה אני מקבל?", callback_data="info"),
            InlineKeyboardButton("📊 הסטטוס שלי", callback_data="user_status"),
        ],
        [
            InlineKeyboardButton("🔗 שתף את שער הקהילה", callback_data="share"),
            InlineKeyboardButton("👥 ההפניות שלי", callback_data="my_referrals"),
        ],
        [
            InlineKeyboardButton("🆘 תמיכה", callback_data="support"),
            InlineKeyboardButton("💬 צ'אט קהילה", url=config.COMMUNITY_GROUP_LINK),
        ],
    ]
    
    # הוספת כפתור אדמין למשתמשים מורשים
    if user_id and user_id in config.ADMIN_IDS:
        buttons.append([
            InlineKeyboardButton("🛠 ניהול", callback_data="admin_menu"),
        ])
    
    return InlineKeyboardMarkup(buttons)

def payment_methods_keyboard() -> InlineKeyboardMarkup:
    """בחירת סוג תשלום"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🏦 העברה בנקאית", callback_data="pay_bank"),
            InlineKeyboardButton("📲 ביט/פייבוקס", callback_data="pay_paybox"),
        ],
        [
            InlineKeyboardButton("💎 טלגרם (TON)", callback_data="pay_ton"),
            InlineKeyboardButton("💳 PayPal", callback_data="pay_paypal"),
        ],
        [
            InlineKeyboardButton("❓ עזרה בתשלום", callback_data="payment_help"),
        ],
        [
            InlineKeyboardButton("⬅ חזרה לתפריט ראשי", callback_data="back_main"),
        ],
    ])

def payment_confirmation_keyboard(payment_method: str) -> InlineKeyboardMarkup:
    """כפתורים לאישור שליחת תשלום"""
    buttons = [
        [
            InlineKeyboardButton("✅ שלחתי תשלום", callback_data=f"confirm_paid:{payment_method}"),
        ],
        [
            InlineKeyboardButton("❌ ביטול", callback_data="back_main"),
        ]
    ]
    return InlineKeyboardMarkup(buttons)

def payment_links_keyboard(payment_method: str) -> InlineKeyboardMarkup:
    """כפתורי לינקים אמיתיים לתשלום"""
    buttons = []
    
    if payment_method in ["paybox", "paypal"]:
        buttons.extend([
            [InlineKeyboardButton("📲 תשלום בפייבוקס", url=config.PAYBOX_URL)],
            [InlineKeyboardButton("📲 תשלום בביט", url=config.BIT_URL)],
            [InlineKeyboardButton("💳 תשלום ב-PayPal", url=config.PAYPAL_URL)],
        ])
    elif payment_method == "bank":
        buttons.append([InlineKeyboardButton("📋 העתק פרטי העברה", callback_data="copy_bank_details")])
    elif payment_method == "ton":
        buttons.append([InlineKeyboardButton("📋 העתק כתובת TON", callback_data="copy_ton_address")])
    
    buttons.extend([
        [InlineKeyboardButton("🔄 החלפת שיטת תשלום", callback_data="change_payment_method")],
        [InlineKeyboardButton("⬅ חזרה לתפריט ראשי", callback_data="back_main")],
    ])
    
    return InlineKeyboardMarkup(buttons)

def support_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💬 קבוצת תמיכה", url=config.SUPPORT_GROUP_LINK),
            InlineKeyboardButton("👨‍💻 מתכנת המערכת", url=f"tg://user?id={config.DEVELOPER_USER_ID}"),
        ],
        [
            InlineKeyboardButton("📞 יצירת קריאת תמיכה", callback_data="create_support_ticket"),
        ],
        [
            InlineKeyboardButton("⬅ חזרה לתפריט ראשי", callback_data="back_main"),
        ],
    ])

def referral_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """כפתורי הפניות"""
    referral_link = f"https://t.me/{(await ptb_app.bot.get_me()).username}?start=ref_{user_id}"
    
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔗 קישור הפניה", url=referral_link),
            InlineKeyboardButton("📤 שתף בקבוצה", callback_data="share_referral"),
        ],
        [
            InlineKeyboardButton("📊 לוח מפנים", callback_data="referral_leaderboard"),
        ],
        [
            InlineKeyboardButton("⬅ חזרה", callback_data="back_main"),
        ],
    ])

def admin_approval_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """כפתורי אישור/דחייה ללוגים"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ אשר תשלום", callback_data=f"adm_approve:{user_id}"),
            InlineKeyboardButton("❌ דחה תשלום", callback_data=f"adm_reject:{user_id}"),
        ],
        [
            InlineKeyboardButton("👀 צפה בפרופיל", callback_data=f"adm_view_profile:{user_id}"),
            InlineKeyboardButton("💬 הודע למשתמש", callback_data=f"adm_message_user:{user_id}"),
        ],
    ])

def admin_menu_keyboard() -> InlineKeyboardMarkup:
    """תפריט אדמין מתקדם"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 סטטוס מערכת", callback_data="adm_status"),
            InlineKeyboardButton("👥 ניהול משתמשים", callback_data="adm_users"),
        ],
        [
            InlineKeyboardButton("💰 תשלומים ממתינים", callback_data="adm_pending_payments"),
            InlineKeyboardButton("📈 סטטיסטיקות", callback_data="adm_stats"),
        ],
        [
            InlineKeyboardButton("🎯 ניהול הטבות", callback_data="adm_rewards"),
            InlineKeyboardButton("🔧 הגדרות", callback_data="adm_settings"),
        ],
        [
            InlineKeyboardButton("🔄 גיבויים", callback_data="adm_backups"),
            InlineKeyboardButton("📋 לוגים", callback_data="adm_logs"),
        ],
    ])

# =========================
# מערכת תבניות והודעות דינמיות
# =========================

class MessageTemplates:
    """מחלקה לניהול תבניות הודעות"""
    
    @staticmethod
    def welcome_message(user: TelegramUser) -> str:
        """הודעת ברוך הבא מותאמת אישית"""
        name = user.first_name or "חבר/ה"
        return f"""
👋 שלום {name}!

ברוך הבא ל**שער הכניסה לקהילת העסקים הדיגיטליים** - המקום שבו עסקים, יזמים ויוצרים נפגשים.

🎯 **מה תמצא כאן?**
• קהילת עסקים פעילה ותומכת
• כלים לשיווק דיגיטלי מתקדם
• הזדמנויות לשיתופי פעולה
• נכסים דיגיטליים וטוקנים בלעדיים

💼 **דמי הצטרפות:** {config.JOIN_FEE} ש"ח חד-פעמיים

לאחר התשלום והאישור תקבל גישה מלאה לכל ההטבות והשירותים.

בחר באפשרות הרצויה ממתפריט הבא:
        """.strip()
    
    @staticmethod
    def payment_instructions(method: str) -> str:
        """הוראות תשלום לפי שיטה"""
        base_instructions = """
לאחר ביצוע התשלום:
1. שלח/י אלינו את **אישור התשלום** (צילום מסך/תמונה)
2. הצוות שלנו יאמת את התשלום בתוך עד 24 שעות
3. עם האישור - תקבל/י קישור ישירות לקהילת העסקים

❓ נתקלת בבעיה? פנה/י לקבוצת התמיכה
        """.strip()
        
        methods = {
            "bank": f"""
🏦 **תשלום בהעברה בנקאית**

בנק הפועלים
סניף כפר גנים (153)
חשבון 73462
המוטב: קאופמן צביקה

סכום: *{config.JOIN_FEE} ש"ח*

{base_instructions}
            """,
            "paybox": f"""
📲 **תשלום בביט / פייבוקס / PayPal**

אפשר לשלם דרך האפליקציות שלך בביט, פייבוקס או PayPal.
הקישורים המעודכנים מופיעים בכפתורים למטה.

סכום: *{config.JOIN_FEE} ש"ח*

{base_instructions}
            """,
            "ton": f"""
💎 **תשלום ב-TON (טלגרם קריפטו)**

אם יש לך כבר ארנק טלגרם (TON Wallet), אפשר לשלם גם בקריפטו.

ארנק לקבלת התשלום:
`UQCr743gEr_nqV_0SBkSp3CtYS_15R3LDLBvLmKeEv7XdGvp`

סכום: *{config.JOIN_FEE} ש"ח* (שווה ערך ב-TON)

👀 בקרוב נחלק גם טוקני *SLH* ייחודיים על רשת TON

{base_instructions}
            """,
            "paypal": f"""
💳 **תשלום ב-PayPal**

ניתן לשלם באמצעות PayPal לכתובת:
[הכנס כאן את כתובת ה-PayPal]

סכום: *{config.JOIN_FEE} ש"ח*

{base_instructions}
            """
        }
        
        return methods.get(method, "שיטת תשלום לא זמינה כרגע.")

# =========================
# עוזר: שליחת תמונת ה-START עם מונים מתקדמים
# =========================

async def send_start_image(context: ContextTypes.DEFAULT_TYPE, chat_id: int, mode: str = "view", user_id: int = None) -> None:
    """
    mode:
      - "view": הצגה ב-/start, מעלה מונה צפיות
      - "download": עותק ממוספר למשתמש אחרי אישור תשלום
      - "reminder": תזכורת בקבוצת לוגים
      - "welcome": תמונת ברוך הבא אישית
    """
    app_data = context.application.bot_data

    # אתחול מונים אם לא קיימים
    if "start_image_views" not in app_data:
        app_data["start_image_views"] = 0
    if "start_image_downloads" not in app_data:
        app_data["start_image_downloads"] = 0
    if "user_downloads" not in app_data:
        app_data["user_downloads"] = {}

    views = app_data["start_image_views"]
    downloads = app_data["start_image_downloads"]

    caption = ""
    serial_number = None

    if mode == "view":
        views += 1
        app_data["start_image_views"] = views
        caption = (
            f"🌐 שער הכניסה לקהילת העסקים\n"
            f"מספר הצגה כולל: *{views}*\n"
            "הצטרפ/י עכשיו כדי לקבל גישה בלעדית!"
        )
        
    elif mode == "download":
        downloads += 1
        app_data["start_image_downloads"] = downloads
        serial_number = downloads
        
        if user_id:
            app_data["user_downloads"][user_id] = serial_number
            
        caption = (
            "🎁 **מתנה אישית שלך!**\n\n"
            f"מספר סידורי לעותק: *#{serial_number}*\n"
            "עותק זה הוא הסמל לגישה המלאה שלך לקהילת העסקים.\n"
            "שמור/י אותו - הוא ייחודי רק עבורך!"
        )
        
    elif mode == "reminder":
        caption = (
            "⏰ **תזכורת: בדיקת לינקי תשלום**\n\n"
            f"מצב מונים נוכחי:\n"
            f"• הצגות תמונה: {views}\n"
            f"• עותקים ממוספרים שנשלחו: {downloads}\n\n"
            "אנא וודא/י שהלינקים של PayBox/Bit/PayPal עדיין תקפים."
        )
        
    elif mode == "welcome":
        caption = (
            "🎉 **ברוך הבא לקהילה!**\n\n"
            "זו התמונה הרשמית של שער הקהילה - עותק אישי רק עבורך.\n"
            "שמור/י אותו כסמל להצטרפותך לקהילת העסקים היוקרתית שלנו."
        )

    try:
        # בדיקה אם הקובץ קיים
        if not os.path.exists(config.START_IMAGE_PATH):
            logger.warning("Start image not found at %s, sending text only", config.START_IMAGE_PATH)
            await context.bot.send_message(
                chat_id=chat_id,
                text=caption,
                parse_mode="Markdown"
            )
            return

        with open(config.START_IMAGE_PATH, "rb") as f:
            # רישום במערכת המטרות אם זמינה
            if DB_AVAILABLE:
                try:
                    if mode == "view":
                        increment_metric("start_image_views", 1)
                    elif mode == "download":
                        increment_metric("start_image_downloads", 1)
                        if user_id:
                            log_audit_event(user_id, "image_download", f"Downloaded start image #{serial_number}")
                except Exception as e:
                    logger.error("Failed to update metrics: %s", e)

            await context.bot.send_photo(
                chat_id=chat_id,
                photo=f,
                caption=caption,
                parse_mode="Markdown",
            )
            
    except FileNotFoundError:
        logger.error("Start image not found at path: %s", config.START_IMAGE_PATH)
        await context.bot.send_message(
            chat_id=chat_id,
            text=caption,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error("Failed to send start image: %s", e)
        # נסיון חלופי עם טקסט בלבד
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=caption,
                parse_mode="Markdown"
            )
        except Exception as e2:
            logger.error("Failed to send fallback message: %s", e2)

# =========================
# Handlers – לוגיקת הבוט המתקדמת
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """תשובת /start משודרגת"""
    message = update.message or update.effective_message
    user = update.effective_user
    
    if not message or not user:
        return

    # בדיקת מגבלת קצב
    user_key = f"start_{user.id}"
    if rate_limiter.is_limited(user_key, 3, 60):  # 3 בקשות ב-60 שניות
        await message.reply_text("⏳ יותר מדי בקשות. נסה שוב בעוד דקה.")
        return

    # 1. רישום משתמש ב-DB
    if DB_AVAILABLE:
        try:
            store_user(user.id, user.username, user.first_name, user.last_name)
            log_audit_event(user.id, "start_command", "User started the bot")
        except Exception as e:
            logger.error("Failed to store user: %s", e)

    # 2. טיפול ב-deep link: /start ref_<referrer_id>
    referral_processed = False
    if message.text and message.text.startswith("/start") and len(message.text.split()) > 1:
        ref_param = message.text.split()[1]
        
        if ref_param.startswith("ref_"):
            try:
                referrer_id = int(ref_param.split("ref_")[1])
                if referrer_id != user.id:  # מניעת הפניה עצמית
                    if DB_AVAILABLE:
                        add_referral(referrer_id, user.id, source="bot_start")
                        # מתן נקודות bonus למפנה
                        update_user_balance(referrer_id, config.REFERRAL_BONUS, "referral_bonus")
                    
                    referral_processed = True
                    logger.info("Referral processed: %s -> %s", referrer_id, user.id)
                    
            except (ValueError, IndexError) as e:
                logger.error("Invalid referral parameter: %s", ref_param)
            except Exception as e:
                logger.error("Failed to process referral: %s", e)

    # 3. שליחת תמונת ברוך הבא
    await send_start_image(context, message.chat_id, mode="view", user_id=user.id)

    # 4. הודעת ברוך הבא מותאמת אישית
    welcome_text = MessageTemplates.welcome_message(user)
    
    if referral_processed:
        welcome_text += "\n\n🎁 **הצטרפת דרך קישור הפניה - קיבלת בונוס נקודות!**"

    await message.reply_text(
        welcome_text,
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(user.id),
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """פקודת /help משודרגת"""
    message = update.message or update.effective_message
    if not message:
        return

    help_text = """
🤖 **מדריך שימוש בבוט - שער קהילת העסקים**

**פקודות בסיסיות:**
/start - התחלת שיחה עם הבוט
/help - הצגת מסך זה
/status - הצגת הסטטוס האישי שלך
/referral - קבלת קישור הפניה אישי

**תהליך ההצטרפות:**
1. לחץ/י על 'הצטרפות לקהילת העסקים'
2. בחר/י שיטת תשלום
3. שלח/י אישור תשלום לאחר הביצוע
4. המתן/י לאישור (עד 24 שעות)
5. קבל/י קישור לקהילה + מתנה דיגיטלית

**הטבות לחברים:**
• גישה לקהילת עסקים פרטית
• הדרכות ושיתופי ידע
• נכסים דיגיטליים בלעדיים
• מערכת נקודות והטבות
• תמיכה טכנית מלאה

**תמיכה:**
לשאלות ובעיות - פנה/י לקבוצת התמיכה או למתכנת המערכת.

*המערכת מתעדכנת באופן שוטף עם פיצ'רים חדשים!*
    """.strip()

    await message.reply_text(help_text, parse_mode="Markdown")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """פקודת /status - מציגה סטטוס משתמש"""
    message = update.message or update.effective_message
    user = update.effective_user
    
    if not message or not user:
        return

    # קבלת נתוני משתמש
    user_data = {}
    if DB_AVAILABLE:
        try:
            user_data = get_user_stats(user.id)
        except Exception as e:
            logger.error("Failed to get user stats: %s", e)

    # בניית הודעת סטטוס
    status_text = f"""
📊 **הסטטוס האישי של {user.first_name}**

👤 **פרופיל:**
• ID: `{user.id}`
• שם: {user.first_name or ""} {user.last_name or ""}
• משתמש: @{user.username or "ללא"}

""".strip()

    if user_data:
        status_text += f"""
📈 **פעילות:**
• הצטרף: {user_data.get('join_date', 'לא ידוע')}
• הפניות: {user_data.get('total_referrals', 0)}
• נקודות: {user_data.get('total_points', 0)}
• תשלומים: {user_data.get('payments_count', 0)}

💎 **סטטוס חברות:**
{"✅ פעיל" if user_data.get('payments_count', 0) > 0 else "❌ ממתין להצטרפות"}
"""
    else:
        status_text += "\n❓ *נתונים לא זמינים כרגע*"

    status_text += "\n\nלצפייה בנתונים מפורטים - השתמש/י בתפריט הראשי."

    await message.reply_text(status_text, parse_mode="Markdown")

# =========================
# handlers לקליקים - גרסה משודרגת
# =========================

async def info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """מידע מפורט על ההטבות"""
    query = update.callback_query
    await query.answer()

    info_text = """
🎁 **מה אני מקבל בהצטרפות?**

**קהילת עסקים פרטית:**
• גישה לקבוצת טלגרם בלעדית לעסקים ויזמים
• שיתופי פעולה ונטוורקינג
• הדרכות מקצועיות שבועיות
• עדכונים על מבצעים והטבות

**נכסים דיגיטליים:**
• טוקני SLH בלעדיים על רשת TON
• NFT ייחודי לחברי קהילה
• נקודות נאמנות שניתנות להמרה

**כלים ושירותים:**
• בוט ניהול עסקי אישי
• מערכת הפניות מתקדמת
• דשבורד ניהול אישי
• תמיכה טכנית מלאה

**יתרונות נוספים:**
• עדיפות בהשתתפות במיזמים חדשים
• הנחות על שירותים נוספים
• גישה לתוכן בלעדי

💵 **דמי הצטרפות:** 39 ש"ח חד-פעמיים
⏱ **משך חברות:** ללא הגבלה

*ההצטרפות כוללת את כל ההטבות הנוכחיות והעתידיות!*
    """.strip()

    await query.edit_message_text(
        info_text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 אני רוצה להצטרף!", callback_data="join")],
            [InlineKeyboardButton("💬 שאלות נוספות", callback_data="support")],
            [InlineKeyboardButton("⬅ חזרה", callback_data="back_main")],
        ])
    )

async def join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """הצטרפות לקהילה - גרסה משודרגת"""
    query = update.callback_query
    await query.answer()

    user = query.from_user
    
    # בדיקה אם המשתמש כבר חבר קהילה
    is_member = False
    if DB_AVAILABLE:
        try:
            user_stats = get_user_stats(user.id)
            is_member = user_stats.get('payments_count', 0) > 0
        except Exception as e:
            logger.error("Failed to check user membership: %s", e)

    if is_member:
        await query.edit_message_text(
            "✅ *אתה כבר חבר קהילה!*\n\n"
            f"הנה הקישור המעודכן לקהילה: {config.COMMUNITY_GROUP_LINK}\n\n"
            "אם הקישור לא עובד - פנה לקבוצת התמיכה.",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(user.id)
        )
        return

    join_text = """
🚀 **הצטרפות לקהילת העסקים**

אנחנו שמחים שבחרת להצטרף לקהילת העסקים הדיגיטליים!

**מה כוללת ההצטרפות?**
✅ גישה לקהילת טלגרם פרטית
✅ כל ההטבות והשירותים
✅ תמיכה טכנית מלאה
✅ עדכונים שוטפים

**תהליך ההצטרפות:**
1. בחר/י שיטת תשלום
2. שלח/י אישור תשלום
3. קבל/י אישור תוך 24 שעות
4. היכנס/י לקהילה!

**דמי הצטרפות:** 39 ש"ח (חד-פעמי)

בחר/י את שיטת התשלום המועדפת:
    """.strip()

    await query.edit_message_text(
        join_text,
        parse_mode="Markdown",
        reply_markup=payment_methods_keyboard()
    )

async def payment_method_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """בחירת שיטת תשלום"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user = query.from_user
    
    if data == "pay_bank":
        method = "bank"
    elif data == "pay_paybox":
        method = "paybox" 
    elif data == "pay_ton":
        method = "ton"
    elif data == "pay_paypal":
        method = "paypal"
    elif data == "payment_help":
        # הצגת עזרה בתשלום
        await query.edit_message_text(
            "❓ **עזרה בתהליך התשלום**\n\n"
            "**בעיות נפוצות:**\n"
            "• התשלום לא עובר - נסה שיטה אחרת\n"
            "• אין אישור - שלח צילום מסך ידני\n"
            "• שאלות על סכום - תמיד 39 ש\"ח\n\n"
            "**תמיכה:**\n"
            "לכל בעיה - פנה לקבוצת התמיכה או למתכנת המערכת.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💬 קבוצת תמיכה", url=config.SUPPORT_GROUP_LINK)],
                [InlineKeyboardButton("⬅ חזרה", callback_data="join")],
            ])
        )
        return
    else:
        return

    # שמירת שיטת התשלום ב-user_data
    context.user_data["selected_payment_method"] = method
    
    # הצגת הוראות תשלום
    payment_text = MessageTemplates.payment_instructions(method)
    
    await query.edit_message_text(
        payment_text,
        parse_mode="Markdown",
        reply_markup=payment_links_keyboard(method)
    )

async def handle_payment_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """טיפול בתמונות אישור תשלום - גרסה משודרגת"""
    message = update.message
    if not message or not message.photo:
        return

    user = update.effective_user
    chat_id = message.chat_id
    
    # בדיקת מגבלת קצב
    user_key = f"payment_photo_{user.id}"
    if rate_limiter.is_limited(user_key, 2, 300):  # 2 תמונות ב-5 דקות
        await message.reply_text("⏳ יותר מדי אישורי תשלום. נסה שוב בעוד 5 דקות.")
        return

    # קבלת שיטת התשלום
    payment_method = context.user_data.get("selected_payment_method", "unknown")
    
    # שמירת פרטי התשלום
    photo = message.photo[-1]  # התמונה באיכות הגבוהה ביותר
    file_id = photo.file_id
    
    payments = payment_manager.get_payments_store(context)
    payments[user.id] = {
        "file_id": file_id,
        "pay_method": payment_method,
        "username": f"@{user.username}" if user.username else user.first_name,
        "chat_id": chat_id,
        "timestamp": datetime.now().isoformat(),
        "status": "pending"
    }

    # רישום ב-DB
    if DB_AVAILABLE:
        try:
            log_payment(user.id, user.username or user.first_name, payment_method)
            log_audit_event(user.id, "payment_submitted", f"Submitted {payment_method} payment")
        except Exception as e:
            logger.error("Failed to log payment: %s", e)

    # שליחה לקבוצת הלוגים
    log_text = f"""
📥 **אישור תשלום חדש**

👤 **משתמש:**
• ID: `{user.id}`
• שם: {user.first_name or ""}
• משתמש: @{user.username or "ללא"}

💳 **תשלום:**
• שיטה: {payment_method}
• סכום: {config.JOIN_FEE} ש"ח
• זמן: {datetime.now().strftime('%d/%m/%Y %H:%M')}

**פעולות:**
    """.strip()

    try:
        await context.bot.send_photo(
            chat_id=config.PAYMENTS_LOG_CHAT_ID,
            photo=file_id,
            caption=log_text,
            reply_markup=admin_approval_keyboard(user.id),
            parse_mode="Markdown"
        )
        log_sent = True
    except Exception as e:
        logger.error("Failed to send payment to log group: %s", e)
        log_sent = False

    # הודעה למשתמש
    user_message = """
✅ **תודה! אישור התשלום התקבל**

האישור נשלח לצוות שלנו לבדיקה.
נעדכן אותך תוך עד 24 שעות.

**מה עכשיו?**
• המתן/י לאישור
• תקבל/י הודעה עם קישור לקהילה
• + מתנה דיגיטלית בלעדית!

❓ **שאלות?** פנה/י לקבוצת התמיכה.
    """.strip()

    await message.reply_text(
        user_message,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💬 קבוצת תמיכה", url=config.SUPPORT_GROUP_LINK)],
            [InlineKeyboardButton("🏠 תפריט ראשי", callback_data="back_main")],
        ])
    )

    # גיבוי - שליחה למפתח אם הקבוצה הראשית נכשלה
    if not log_sent:
        try:
            await context.bot.send_photo(
                chat_id=config.DEVELOPER_USER_ID,
                photo=file_id,
                caption=f"גיבוי - אישור תשלום מ-{user.id}\n{log_text}",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error("Failed to send backup payment notification: %s", e)

# =========================
# מערכת אישור/דחייה מתקדמת
# =========================

async def do_approve(target_id: int, context: ContextTypes.DEFAULT_TYPE, source_message=None, admin_id: int = None) -> None:
    """אישור תשלום - גרסה משודרגת"""
    
    # שליחת הודעה למשתמש
    approval_text = f"""
🎉 **מזל טוב! התשלום אושר**

ברוך הבא לקהילת העסקים הדיגיטליים!

**הקישור לקהילה:**
{config.COMMUNITY_GROUP_LINK}

**מה עכשיו?**
1. היכנס/י לקהילה והצג/י את עצמך
2. קבל/י את המתנה הדיגיטלית שלך
3. התחל/י ליהנות מההטבות

📞 **תמיכה:** תמיד זמינה בקבוצת התמיכה.

*שמחים שהצטרפת אלינו!* 👋
    """.strip()

    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=approval_text,
            parse_mode="Markdown"
        )
        
        # שליחת תמונה ממוספרת
        await send_start_image(context, target_id, mode="download", user_id=target_id)
        
        # עדכון סטטוס
        if DB_AVAILABLE:
            try:
                update_payment_status(target_id, "approved", None)
                if admin_id:
                    log_admin_action(admin_id, "payment_approval", f"Approved payment for user {target_id}")
            except Exception as e:
                logger.error("Failed to update payment status: %s", e)
        
        # עדכון ההודעה המקורית
        if source_message:
            await source_message.reply_text(
                f"✅ תשלום של משתמש {target_id} אושר ונשלחו ההנחיות."
            )
            
    except Exception as e:
        logger.error("Failed to send approval: %s", e)
        if source_message:
            await source_message.reply_text(f"❌ שגיאה באישור: {e}")

async def do_reject(target_id: int, reason: str, context: ContextTypes.DEFAULT_TYPE, source_message=None, admin_id: int = None) -> None:
    """דחיית תשלום - גרסה משודרגת"""
    
    rejection_text = f"""
❌ **אישור התשלום נדחה**

לצערנו לא יכולנו לאמת את התשלום שלך.

**סיבה:** {reason}

**מה אפשר לעשות?**
• שלח/י שוב את אישור התשלום
• פנה/י לתמיכה אם לדעתך מדובר בטעות
• נסה/י שיטת תשלום אחרת

💬 **עזרה:** קבוצת התמיכה זמינה לשאלות.
    """.strip()

    try:
        # שליחת הודעת דחייה
        await context.bot.send_message(
            chat_id=target_id,
            text=rejection_text,
            parse_mode="Markdown"
        )
        
        # עדכון סטטוס
        if DB_AVAILABLE:
            try:
                update_payment_status(target_id, "rejected", reason)
                if admin_id:
                    log_admin_action(admin_id, "payment_rejection", f"Rejected payment for user {target_id}: {reason}")
            except Exception as e:
                logger.error("Failed to update payment status: %s", e)
        
        if source_message:
            await source_message.reply_text(
                f"❌ תשלום של משתמש {target_id} נדחה. סיבה: {reason}"
            )
            
    except Exception as e:
        logger.error("Failed to send rejection: %s", e)
        if source_message:
            await source_message.reply_text(f"❌ שגיאה בדחייה: {e}")

# =========================
# פקודות אדמין מתקדמות
# =========================

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """פקודת /admin - תפריט ניהול"""
    message = update.message or update.effective_message
    user = update.effective_user
    
    if not message or not user or user.id not in config.ADMIN_IDS:
        await message.reply_text("❌ אין לך הרשאות ניהול.")
        return

    admin_text = """
🛠 **פאנל ניהול - שער קהילת העסקים**

**סטטוס מערכת:**
• בוט: 🟢 פעיל
• DB: {db_status}
• Webhook: 🟢 פעיל

**סטטיסטיקות מהירות:**
• משתמשים: {user_count}
• תשלומים: {payment_count}
• ממתינים: {pending_count}

**פעולות ניהול:**
    """.strip()

    # קבלת נתונים עדכניים
    db_status = "🟢 פעיל" if DB_AVAILABLE else "🔴 כבוי"
    user_count = "N/A"
    payment_count = "N/A" 
    pending_count = "N/A"
    
    if DB_AVAILABLE:
        try:
            stats = get_system_stats()
            user_count = stats.get('total_users', 'N/A')
            payment_count = stats.get('total_payments', 'N/A')
            pending_count = stats.get('pending_payments', 'N/A')
        except Exception as e:
            logger.error("Failed to get system stats: %s", e)

    admin_text = admin_text.format(
        db_status=db_status,
        user_count=user_count,
        payment_count=payment_count,
        pending_count=pending_count
    )

    await message.reply_text(
        admin_text,
        parse_mode="Markdown",
        reply_markup=admin_menu_keyboard()
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """פקודת /stats - סטטיסטיקות מערכת"""
    message = update.message or update.effective_message
    user = update.effective_user
    
    if not message or not user or user.id not in config.ADMIN_IDS:
        await message.reply_text("❌ אין לך הרשאות ניהול.")
        return

    if not DB_AVAILABLE:
        await message.reply_text("❌ DB לא זמין לסטטיסטיקות.")
        return

    try:
        stats = get_system_stats()
        approval_stats = get_approval_stats()
        top_referrers = get_top_referrers(5)
        
        stats_text = f"""
📊 **סטטיסטיקות מערכת מפורטות**

**משתמשים:**
• סה"כ: {stats.get('total_users', 0)}
• חדשים היום: {stats.get('new_users_today', 0)}
• פעילים (24h): {stats.get('active_users_24h', 0)}

**תשלומים:**
• סה"כ: {stats.get('total_payments', 0)}
• מאושרים: {approval_stats.get('approved', 0)}
• נדחים: {approval_stats.get('rejected', 0)}
• ממתינים: {approval_stats.get('pending', 0)}
• אחוז אישור: {approval_stats.get('approval_rate', 0)}%

**הכנסות:**
• סה"כ: {stats.get('total_earnings', 0)} ש"ח
• היום: {stats.get('earnings_today', 0)} ש"ח

**מפנים מובילים:**
        """.strip()

        for i, referrer in enumerate(top_referrers, 1):
            stats_text += f"\n{i}. {referrer.get('username', 'Unknown')} - {referrer.get('total_referrals', 0)} הפניות"
        
        await message.reply_text(stats_text, parse_mode="Markdown")
        
    except Exception as e:
        logger.error("Failed to get system stats: %s", e)
        await message.reply_text("❌ שגיאה בטעינת סטטיסטיקות.")

# =========================
# callback handlers לניהול
# =========================

async def admin_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """טיפול בבחירת תפריט אדמין"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    if user.id not in config.ADMIN_IDS:
        await query.answer("❌ אין הרשאה", show_alert=True)
        return

    data = query.data
    
    if data == "adm_status":
        # סטטוס מערכת מפורט
        status_text = await get_system_status_text()
        await query.edit_message_text(
            status_text,
            parse_mode="Markdown",
            reply_markup=admin_menu_keyboard()
        )
        
    elif data == "adm_pending_payments":
        # תשלומים ממתינים
        pending_text = await get_pending_payments_text(context)
        await query.edit_message_text(
            pending_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 רענן", callback_data="adm_pending_payments")],
                [InlineKeyboardButton("⬅ חזרה", callback_data="admin_menu")],
            ])
        )
        
    elif data == "adm_stats":
        # סטטיסטיקות מתקדמות
        stats_text = await get_advanced_stats_text()
        await query.edit_message_text(
            stats_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 דוח מלא", callback_data="adm_full_report")],
                [InlineKeyboardButton("⬅ חזרה", callback_data="admin_menu")],
            ])
        )
    
    elif data == "admin_menu":
        await query.edit_message_text(
            "🛠 **פאנל ניהול**\n\nבחר פעולה:",
            parse_mode="Markdown",
            reply_markup=admin_menu_keyboard()
        )

async def get_system_status_text() -> str:
    """מחזיר טקסט סטטוס מערכת מפורט"""
    basic_status = """
🖥 **סטטוס מערכת - שער קהילת העסקים**

**מערכת:**
• בוט: 🟢 פעיל
• Webhook: 🟢 פעיל
• DB: {db_status}
• זמן פעילות: {uptime}

**משאבים:**
• זיכרון: {memory_usage}
• CPU: {cpu_usage}
• דיסק: {disk_usage}
    """.strip()

    # נתונים דינמיים (בפועל צריך לקבל ממוניטורינג אמיתי)
    import psutil
    process = psutil.Process()
    
    db_status = "🟢 פעיל" if DB_AVAILABLE else "🔴 כבוי"
    uptime = str(datetime.now() - start_time).split('.')[0]
    memory_usage = f"{process.memory_info().rss / 1024 / 1024:.1f} MB"
    cpu_usage = f"{process.cpu_percent():.1f}%"
    disk_usage = "N/A"  # ניתן להוסיף בדיקת דיסק

    return basic_status.format(
        db_status=db_status,
        uptime=uptime,
        memory_usage=memory_usage,
        cpu_usage=cpu_usage,
        disk_usage=disk_usage
    )

async def get_pending_payments_text(context: ContextTypes.DEFAULT_TYPE) -> str:
    """מחזיר טקסט תשלומים ממתינים"""
    payments = payment_manager.get_payments_store(context)
    pending_payments = {k: v for k, v in payments.items() if v.get('status') == 'pending'}
    
    if not pending_payments:
        return "✅ **אין תשלומים ממתינים לאישור**"
    
    text = "📋 **תשלומים ממתינים לאישור:**\n\n"
    
    for user_id, payment_data in list(pending_payments.items())[:10]:  # הגבלה ל-10
        text += f"• User ID: `{user_id}`\n"
        text += f"  שיטה: {payment_data.get('pay_method', 'Unknown')}\n"
        text += f"  זמן: {payment_data.get('timestamp', 'Unknown')}\n"
        text += f"  [אשר](tg://user?id={config.DEVELOPER_USER_ID}) | [דחה](tg://user?id={config.DEVELOPER_USER_ID})\n\n"
    
    if len(pending_payments) > 10:
        text += f"\n...ועוד {len(pending_payments) - 10} תשלומים"
    
    return text

# =========================
# רישום handlers מתקדם
# =========================

def setup_handlers():
    """הגדרת כל ה-handlers של הבוט"""
    
    # command handlers
    ptb_app.add_handler(CommandHandler("start", start))
    ptb_app.add_handler(CommandHandler("help", help_command))
    ptb_app.add_handler(CommandHandler("status", status_command))
    ptb_app.add_handler(CommandHandler("admin", admin_command))
    ptb_app.add_handler(CommandHandler("stats", stats_command))
    ptb_app.add_handler(CommandHandler("approve", approve_command))
    ptb_app.add_handler(CommandHandler("reject", reject_command))
    ptb_app.add_handler(CommandHandler("referral", referral_command))

    # callback handlers
    ptb_app.add_handler(CallbackQueryHandler(info_callback, pattern="^info$"))
    ptb_app.add_handler(CallbackQueryHandler(join_callback, pattern="^join$"))
    ptb_app.add_handler(CallbackQueryHandler(support_callback, pattern="^support$"))
    ptb_app.add_handler(CallbackQueryHandler(share_callback, pattern="^share$"))
    ptb_app.add_handler(CallbackQueryHandler(back_main_callback, pattern="^back_main$"))
    ptb_app.add_handler(CallbackQueryHandler(payment_method_callback, pattern="^pay_"))
    ptb_app.add_handler(CallbackQueryHandler(admin_menu_callback, pattern="^adm_"))
    ptb_app.add_handler(CallbackQueryHandler(user_status_callback, pattern="^user_status$"))
    ptb_app.add_handler(CallbackQueryHandler(my_referrals_callback, pattern="^my_referrals$"))

    # message handlers
    ptb_app.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, handle_payment_photo))
    ptb_app.add_handler(MessageHandler(filters.TEXT & filters.User(list(config.ADMIN_IDS)), admin_reject_reason_handler))

    # error handler
    ptb_app.add_error_handler(error_handler)

    logger.info("All handlers registered successfully")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """טיפול בשגיאות כלליות"""
    try:
        raise context.error
    except TelegramError as e:
        logger.error(f"Telegram error: {e}")
    except NetworkError as e:
        logger.error(f"Network error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        
        # שליחת התראה למפתח
        try:
            error_msg = f"❌ **שגיאה בבוט:**\n```{str(e)[:1000]}```"
            await context.bot.send_message(
                chat_id=config.DEVELOPER_USER_ID,
                text=error_msg,
                parse_mode="Markdown"
            )
        except Exception as notify_error:
            logger.error(f"Failed to send error notification: {notify_error}")

# =========================
# FastAPI + Webhook + Admin Dashboard
# =========================

# אתחול FastAPI
app = FastAPI(
    title="שער קהילת העסקים",
    description="בוט ניהול קהילת עסקים דיגיטליים עם מערכת תשלומים והפניות",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# הרחבת lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    ניהול מחזור חיים של האפליקציה
    """
    logger.info("Starting application lifespan...")
    
    # 1. אתחול DB
    if DB_AVAILABLE:
        try:
            init_schema()
            logger.info("Database schema initialized")
        except Exception as e:
            logger.error("Failed to initialize database: %s", e)
    
    # 2. הגדרת webhook
    try:
        await ptb_app.bot.setWebhook(
            url=config.WEBHOOK_URL,
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
        logger.info("Webhook set to: %s", config.WEBHOOK_URL)
    except Exception as e:
        logger.error("Failed to set webhook: %s", e)
        raise
    
    # 3. אתחול הבוט
    try:
        await ptb_app.start()
        logger.info("Telegram application started")
        
        # הגדרת פקודות
        await setup_commands()
        
        # אתחול job queue
        if ptb_app.job_queue:
            # תזכורת לעדכון לינקים כל 6 ימים
            ptb_app.job_queue.run_repeating(
                remind_update_links,
                interval=6 * 24 * 60 * 60,
                first=10
            )
            
            # cleanup יומי
            ptb_app.job_queue.run_daily(
                daily_cleanup,
                time=datetime.time(hour=3, minute=0)  # 3:00 בלילה
            )
            
            logger.info("Job queue initialized")
        
    except Exception as e:
        logger.error("Failed to start Telegram application: %s", e)
        raise
    
    # 4. אתחול מוצלח
    logger.info("Application startup completed successfully")
    global start_time
    start_time = datetime.now()
    
    yield
    
    # 5. shutdown
    logger.info("Shutting down application...")
    try:
        await ptb_app.stop()
        logger.info("Telegram application stopped")
    except Exception as e:
        logger.error("Error during shutdown: %s", e)

# jobs
async def remind_update_links(context: ContextTypes.DEFAULT_TYPE):
    """תזכורת לעדכון לינקי תשלום"""
    await send_start_image(context, config.PAYMENTS_LOG_CHAT_ID, mode="reminder")

async def daily_cleanup(context: ContextTypes.DEFAULT_TYPE):
    """ניקוי יומי של נתונים"""
    logger.info("Running daily cleanup")
    
    # ניקוי סשנים
    session_manager.cleanup_expired()
    
    # ניקוי DB אם זמין
    if DB_AVAILABLE:
        try:
            cleanup_old_data()
            logger.info("Database cleanup completed")
        except Exception as e:
            logger.error("Database cleanup failed: %s", e)
    
    # גיבוי אם זמין
    if DB_AVAILABLE:
        try:
            backup_database()
            logger.info("Database backup completed")
        except Exception as e:
            logger.error("Database backup failed: %s", e)

# =========================
# FastAPI Routes מתקדמים
# =========================

@app.post("/webhook")
async def telegram_webhook(request: Request) -> Response:
    """נקודת הכניסה לעדכונים מטלגרם"""
    try:
        data = await request.json()
        update = Update.de_json(data, ptb_app.bot)
        
        # בדיקת כפילות
        if is_duplicate_update(update):
            logger.debug("Duplicate update ignored: %s", update.update_id)
            return Response(status_code=HTTPStatus.OK)
        
        # עיבוד העדכון
        await ptb_app.process_update(update)
        return Response(status_code=HTTPStatus.OK)
        
    except Exception as e:
        logger.error("Error processing webhook: %s", e)
        return Response(status_code=HTTPStatus.INTERNAL_SERVER_ERROR)

@app.get("/health")
async def health():
    """Healthcheck מקיף"""
    health_status = {
        "status": "healthy",
        "service": "telegram-gateway-community-bot",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0",
        "components": {
            "bot": "active",
            "webhook": "active",
            "database": "enabled" if DB_AVAILABLE else "disabled",
            "uptime": str(datetime.now() - start_time).split('.')[0] if 'start_time' in globals() else "unknown"
        }
    }
    
    # בדיקות נוספות
    try:
        # בדיקת חיבור לבוט
        bot_info = await ptb_app.bot.get_me()
        health_status["components"]["bot_username"] = bot_info.username
    except Exception as e:
        health_status["status"] = "degraded"
        health_status["components"]["bot"] = "error"
        health_status["error"] = str(e)
    
    return health_status

@app.get("/admin/stats")
async def admin_stats_api(token: str = ""):
    """API לסטטיסטיקות ניהול"""
    if not config.ADMIN_DASH_TOKEN or token != config.ADMIN_DASH_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    if not DB_AVAILABLE:
        return {"error": "Database not available"}
    
    try:
        stats = get_system_stats()
        approval_stats = get_approval_stats()
        top_referrers = get_top_referrers(10)
        recent_activities = get_recent_activities(20)
        
        return {
            "system": stats,
            "payments": approval_stats,
            "top_referrers": top_referrers,
            "recent_activities": recent_activities,
            "metrics": {
                "start_image_views": get_metric("start_image_views"),
                "start_image_downloads": get_metric("start_image_downloads"),
                "total_payments": get_metric("total_payments"),
            }
        }
    except Exception as e:
        logger.error("Failed to get admin stats: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/admin/dashboard")
async def admin_dashboard_html(request: Request, token: str = ""):
    """דשבורד ניהול HTML"""
    if not config.ADMIN_DASH_TOKEN or token != config.ADMIN_DASH_TOKEN:
        return HTMLResponse("""
        <html dir="rtl">
        <head><title>Unauthorized</title></head>
        <body><h1>❌ אין הרשאה</h1></body>
        </html>
        """, status_code=401)
    
    # כאן ניתן להחזיר דשבורד HTML אמיתי
    dashboard_html = """
    <html dir="rtl">
    <head>
        <title>פאנל ניהול - שער קהילת העסקים</title>
        <meta charset="utf-8">
        <style>
            body { font-family: Arial; background: #f5f5f5; margin: 0; padding: 20px; }
            .container { max-width: 1200px; margin: 0 auto; }
            .card { background: white; padding: 20px; margin: 10px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; }
            .stat-card { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 8px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🛠 פאנל ניהול - שער קהילת העסקים</h1>
            
            <div class="stats-grid" id="stats-grid">
                <div class="stat-card">
                    <h3>👥 משתמשים</h3>
                    <p id="user-count">טוען...</p>
                </div>
                <div class="stat-card">
                    <h3>💰 תשלומים</h3>
                    <p id="payment-count">טוען...</p>
                </div>
                <div class="stat-card">
                    <h3>📈 הכנסות</h3>
                    <p id="earnings">טוען...</p>
                </div>
            </div>
            
            <div class="card">
                <h2>סטטיסטיקות נוספות</h2>
                <pre id="full-stats">טוען...</pre>
            </div>
        </div>
        
        <script>
            async function loadStats() {
                try {
                    const response = await fetch('/admin/stats?token=' + new URLSearchParams(window.location.search).get('token'));
                    const data = await response.json();
                    
                    document.getElementById('user-count').textContent = data.system?.total_users || 0;
                    document.getElementById('payment-count').textContent = data.payments?.total || 0;
                    document.getElementById('earnings').textContent = (data.system?.total_earnings || 0) + ' ש"ח';
                    document.getElementById('full-stats').textContent = JSON.stringify(data, null, 2);
                } catch (error) {
                    console.error('Error loading stats:', error);
                }
            }
            
            loadStats();
            setInterval(loadStats, 30000); // רענון כל 30 שניות
        </script>
    </body>
    </html>
    """
    
    return HTMLResponse(dashboard_html)

# =========================
# הרצת האפליקציה
# =========================

if __name__ == "__main__":
    import uvicorn
    
    # הגדרת handlers
    setup_handlers()
    
    # הרצת השרת
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        log_level="info"
    )
# === SLHNET EXTENSION: BSC wallet + sales + social posts + stable /health ===
from typing import Optional, Dict, Any, List
from pydantic import BaseModel

# API models
class TokenSalePublic(BaseModel):
    id: int
    user_id: int
    wallet_address: str
    chain_id: int
    amount_slh: float
    tx_hash: str
    tx_status: str
    tx_error: Optional[str] = None
    block_number: Optional[int] = None
    created_at: Any


class PostCreate(BaseModel):
    title: str
    content: str
    image_url: Optional[str] = None
    link_url: Optional[str] = None
    user_id: Optional[int] = None
    username: Optional[str] = None


class PostPublic(BaseModel):
    id: int
    user_id: int
    username: Optional[str]
    title: Optional[str]
    content: Optional[str]
    image_url: Optional[str] = None
    link_url: Optional[str] = None
    created_at: Any
    status: str


# override /health with simple OK endpoint for Railway
@app.get("/health")
async def health_slhnet():
    return {
        "status": "ok",
        "service": "slhnet-gateway",
    }


# token meta + sales API
@app.get("/api/token/meta")
async def api_token_meta():
    from slh_token import (
        SLH_CHAIN_ID,
        SLH_RPC_URL,
        SLH_TOKEN_ADDRESS,
        SLH_TOKEN_SYMBOL,
        SLH_TOKEN_DECIMALS,
        TREASURY_ADDRESS,
    )

    return {
        "network": {
            "name": "Binance Smart Chain",
            "chain_id": SLH_CHAIN_ID,
            "rpc_url": SLH_RPC_URL,
            "explorer": "https://bscscan.com",
        },
        "token": {
            "address": SLH_TOKEN_ADDRESS,
            "symbol": SLH_TOKEN_SYMBOL,
            "decimals": SLH_TOKEN_DECIMALS,
        },
        "treasury_address": TREASURY_ADDRESS,
    }


@app.get("/api/token/sales")
async def api_token_sales(limit: int = 50, offset: int = 0):
    from db import list_token_sales
    items = list_token_sales(limit=limit, offset=offset)
    return {"items": items, "count": len(items)}


@app.get("/api/posts")
async def api_list_posts(limit: int = 20, offset: int = 0):
    from db import list_recent_posts
    items = list_recent_posts(limit=limit, offset=offset)
    return {"items": items, "count": len(items)}


@app.post("/api/posts")
async def api_create_post(post: PostCreate):
    from db import create_post
    pid = create_post(
        user_id=post.user_id or 0,
        username=post.username,
        title=post.title,
        content=post.content,
        image_url=post.image_url,
        link_url=post.link_url,
    )
    return {"id": pid}


# Telegram commands: wallet + sell + sales + post + mynet

async def wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from slh_token import SLH_CHAIN_ID, SLH_TOKEN_SYMBOL, get_slh_balance
    from db import get_user_wallets

    message = update.message or update.effective_message
    user = update.effective_user
    if not message or not user:
        return

    wallets = get_user_wallets(user.id, chain_id=SLH_CHAIN_ID)
    if not wallets:
        text = (
            " *אין לך עדיין ארנק SLH מחובר*\n\n"
            "כדי לחבר ארנק BSC (MetaMask):\n"
            "/setwallet 0xהכתובת_שלך\n\n"
            "הארנק צריך להיות על BSC Mainnet."
        )
        await message.reply_text(text, parse_mode="Markdown")
        return

    lines = [" *הארנקים שלך על BSC (SLHNET):*"]
    for w in wallets:
        addr = w["address"]
        primary_mark = " (ראשי)" if w["is_primary"] else ""
        bal = get_slh_balance(addr)
        balance_str = f"  {bal:.4f} {SLH_TOKEN_SYMBOL}" if bal is not None else ""
        lines.append(f" {addr}{primary_mark}{balance_str}")

    lines.append(
        "\nלעדכון ארנק ראשי:\n"
        "/setwallet 0xכתובת_הארנק_החדשה"
    )
    await message.reply_text("\n".join(lines), parse_mode="Markdown")


async def setwallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from slh_token import SLH_CHAIN_ID, SLH_TOKEN_SYMBOL, is_valid_bsc_address, get_slh_balance
    from db import add_wallet

    message = update.message or update.effective_message
    user = update.effective_user
    if not message or not user or not message.text:
        return

    parts = message.text.strip().split(maxsplit=1)
    if len(parts) != 2:
        await message.reply_text(
            "שימוש:\n/setwallet 0xכתובת_הארנק_BSC_שלך",
            parse_mode="Markdown",
        )
        return

    addr = parts[1].strip()
    if not is_valid_bsc_address(addr):
        await message.reply_text(" כתובת ארנק לא תקינה. ודא שהיא מתחילה ב0x ושייכת לרשת BSC.")
        return

    add_wallet(user.id, user.username, SLH_CHAIN_ID, addr, is_primary=True)
    bal = get_slh_balance(addr)
    bal_text = ""
    if bal is not None:
        bal_text = f"\n\nיתרה משוערת: *{bal:.4f} {SLH_TOKEN_SYMBOL}*"

    await message.reply_text(
        f" הארנק נשמר בהצלחה:\n{addr}{bal_text}",
        parse_mode="Markdown",
    )


async def sell_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from slh_token import (
        SLH_CHAIN_ID,
        SLH_TOKEN_SYMBOL,
        TREASURY_ADDRESS,
        verify_slh_sale_tx,
    )
    from db import get_primary_wallet, create_token_sale

    message = update.message or update.effective_message
    user = update.effective_user
    if not message or not user or not message.text:
        return

    parts = message.text.strip().split()
    if len(parts) != 3:
        await message.reply_text(
            "שימוש:\n/sell <כמות_SLH> <tx_hash>\n\n"
            "1. העבר SLH מהארנק שלך לכתובת ה-Treasury:\n"
            f"{TREASURY_ADDRESS}\n"
            "2. העתיק/י את ה-tx hash\n"
            "3. הרץ/י את הפקודה עם הכמות וה-hash.",
            parse_mode="Markdown",
        )
        return

    try:
        amount = float(parts[1])
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.reply_text(" כמות לא תקינה.")
        return

    tx_hash = parts[2].strip()
    wallet = get_primary_wallet(user.id, SLH_CHAIN_ID)
    if not wallet:
        await message.reply_text(
            " אין לך עדיין ארנק SLH מחובר.\n"
            "קודם כל הגדר ארנק באמצעות:\n/setwallet 0xכתובת_הארנק",
            parse_mode="Markdown",
        )
        return

    user_address = wallet["address"]
    await message.reply_text(" מאמת את העסקה על BSC...")

    ok, reason, amount_on_chain, block_number = verify_slh_sale_tx(
        tx_hash=tx_hash,
        expected_from=user_address,
        min_amount=amount,
    )

    status = "verified" if ok else "rejected"
    error_text = None if ok else reason
    recorded_amount = amount_on_chain if amount_on_chain is not None else amount

    sale_id = create_token_sale(
        user_id=user.id,
        wallet_address=user_address,
        chain_id=SLH_CHAIN_ID,
        amount_slh=recorded_amount,
        tx_hash=tx_hash,
        status=status,
        error=error_text,
        block_number=block_number,
    )

    if ok:
        await message.reply_text(
            f" *המכירה נרשמה בהצלחה!*\n\n"
            f"ID פנימי: {sale_id}\n"
            f"סכום: *{recorded_amount:.4f} {SLH_TOKEN_SYMBOL}*\n"
            f"בלוק: {block_number}\n\n"
            f"צפייה בעסקה:\nhttps://bscscan.com/tx/{tx_hash}",
            parse_mode="Markdown",
        )
    else:
        await message.reply_text(
            f" המכירה נרשמה כ*לא מאומתת*.\n"
            f"סיבה: {reason}\n\n"
            f"ID פנימי: {sale_id}\n"
            f"עסקה: https://bscscan.com/tx/{tx_hash}\n\n"
            "אם לדעתך מדובר בטעות  פנה לתמיכה.",
            parse_mode="Markdown",
        )


async def sales_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from slh_token import SLH_TOKEN_SYMBOL, TREASURY_ADDRESS
    from db import get_user_token_sales

    message = update.message or update.effective_message
    user = update.effective_user
    if not message or not user:
        return

    rows = get_user_token_sales(user.id)
    if not rows:
        await message.reply_text(
            "אין עדיין מכירות SLH רשומות עבורך.\n\n"
            "כדי למכור:\n"
            f"1. העבר/י SLH לכתובת Treasury:\n{TREASURY_ADDRESS}\n"
            "2. דווח/י לבוט:\n/sell <כמות_SLH> <tx_hash>",
            parse_mode="Markdown",
        )
        return

    lines = [" *המכירות האחרונות שלך ב-SLHNET:*"]
    for s in rows[:10]:
        lines.append(
            f"- {s['amount_slh']:.4f} {SLH_TOKEN_SYMBOL} | "
            f"[tx](https://bscscan.com/tx/{s['tx_hash']}) | "
            f"סטטוס: {s['tx_status']}"
        )

    lines.append("\nרשימה מלאה זמינה באתר: https://slh-nft.com/#sales")
    await message.reply_text("\n".join(lines), parse_mode="Markdown", disable_web_page_preview=True)


async def post_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from db import create_post

    message = update.message or update.effective_message
    user = update.effective_user
    if not message or not user or not message.text:
        return

    # format: /post title | content
    text = message.text
    parts = text.split(" ", 1)
    if len(parts) < 2:
        await message.reply_text(
            "שימוש:\n/post כותרת | תוכן הפוסט\n\n"
            "לדוגמה:\n/post השקת SLHNET | פוסט קצר על מה שהכנתי לקהילה",
            parse_mode="Markdown",
        )
        return

    payload = parts[1]
    if "|" in payload:
        title, content = [p.strip() for p in payload.split("|", 1)]
    else:
        title, content = payload.strip(), ""

    pid = create_post(
        user_id=user.id,
        username=user.username,
        title=title,
        content=content,
        image_url=None,
        link_url=None,
    )

    await message.reply_text(
        f" הפוסט שלך נשמר במערכת (ID={pid}).\n"
        "הפוסט יוצג באתר SLHNET וניתן לשתף אותו ברשתות החברתיות.",
    )


async def mynet_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message or update.effective_message
    if not message:
        return

    text = (
        " *SLHNET  רשת העסקים שלך*\n\n"
        "אתר הרשת: https://slh-nft.com/\n"
        "בוט שער: https://t.me/Buy_My_Shop\n\n"
        "הצטרף, חבר ארנק, מכור SLH, פתח חנות וקבוצת עסקים משלך."
    )
    await message.reply_text(text, parse_mode="Markdown")


def setup_slhnet_handlers():
    from telegram.ext import CommandHandler

    ptb_app.add_handler(CommandHandler("wallet", wallet_command))
    ptb_app.add_handler(CommandHandler("setwallet", setwallet_command))
    ptb_app.add_handler(CommandHandler("sell", sell_command))
    ptb_app.add_handler(CommandHandler("sales", sales_command))
    ptb_app.add_handler(CommandHandler("post", post_command))
    ptb_app.add_handler(CommandHandler("mynet", mynet_command))


# make sure handlers are registered on import (for uvicorn main:app on Railway)
try:
    setup_handlers()
    setup_slhnet_handlers()
    logger.info("SLHNET handlers registered on import.")
except Exception as e:
    logger.error("SLHNET: failed to setup handlers on import: %s", e)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

# CORS רחב  כדי שהאתר slh-nft.com יוכל לקרוא את ה-API
try:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
except Exception:
    pass


@app.get("/config/public")
async def public_config():
    import os
    return {
        "business_group_link": os.getenv("GROUP_STATIC_INVITE"),
        "paybox_url": os.getenv("PAYBOX_URL"),
        "paypal_url": os.getenv("PAYPAL_URL"),
        "slh_nis": os.getenv("SLH_NIS", "39"),
        "bot_username": os.getenv("BOT_USERNAME"),
    }


@app.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard_page():
    html = """<!doctype html>
<html lang="he" dir="rtl">
<head>
  <meta charset="utf-8" />
  <title>SLHNET  לוח בקרה</title>
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <style>
    body {
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #020617;
      color: #f9fafb;
      margin: 0;
      padding: 16px;
    }
    h1, h2 {
      margin: 0 0 12px;
    }
    .card {
      background: rgba(15,23,42,0.96);
      border-radius: 14px;
      padding: 16px;
      margin-bottom: 16px;
      border: 1px solid rgba(148,163,184,0.35);
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.85rem;
    }
    th, td {
      border-bottom: 1px solid rgba(148,163,184,0.35);
      padding: 6px 4px;
      text-align: right;
    }
    th {
      font-weight: 600;
      color: #e5e7eb;
    }
    code {
      background: rgba(15,23,42,0.85);
      padding: 2px 6px;
      border-radius: 6px;
      font-size: 0.8rem;
    }
  </style>
</head>
<body>
  <h1>SLHNET  לוח בקרה אדמיניסטרטיבי</h1>
  <div class="card">
    <p>
      הטוקן מועבר דרך הפרמטר <code>token</code> ב-URL, לדוגמה:<br/>
      <code>/admin/dashboard?token=ADMIN_DASH_TOKEN</code>
    </p>
  </div>

  <div class="card">
    <h2>סטטיסטיקות תשלומים</h2>
    <div id="stats-box">טוען נתונים...</div>
  </div>

  <script>
    async function loadStats() {
      const params = new URLSearchParams(window.location.search);
      const token = params.get("token") || "";
      let url = "/admin/stats";
      if (token) {
        url += "?token=" + encodeURIComponent(token);
      }

      const box = document.getElementById("stats-box");
      try {
        const res = await fetch(url);
        if (!res.ok) {
          box.textContent = "שגיאה בטעינת /admin/stats: HTTP " + res.status;
          return;
        }
        const data = await res.json();
        const ps = data.payments_stats || {};
        const breakdown = data.monthly_breakdown || [];
        const topRef = data.top_referrers || [];

        let html = "";
        html += "<p>DB: <strong>" + (data.db || "-") + "</strong></p>";
        html += "<p>Pending: <strong>" + (ps.pending || 0) + "</strong> | Approved: <strong>" + (ps.approved || 0) + "</strong> | Rejected: <strong>" + (ps.rejected || 0) + "</strong> | Total: <strong>" + (ps.total || 0) + "</strong></p>";

        html += "<h3>פילוח חודשי לפי אמצעי תשלום</h3>";
        if (breakdown.length === 0) {
          html += "<p>אין נתונים.</p>";
        } else {
          html += "<table><thead><tr><th>אמצעי תשלום</th><th>סטטוס</th><th>כמות</th></tr></thead><tbody>";
          breakdown.forEach((r) => {
            html += "<tr><td>" + r.pay_method + "</td><td>" + r.status + "</td><td>" + r.count + "</td></tr>";
          });
          html += "</tbody></table>";
        }

        html += "<h3 style='margin-top:14px;'>מפנים מובילים</h3>";
        if (topRef.length === 0) {
          html += "<p>אין עדיין מפנים רשומים.</p>";
        } else {
          html += "<ul>";
          topRef.forEach((r) => {
            html += "<li>" + r.username + "  " + r.count + " הפניות</li>";
          });
          html += "</ul>";
        }

        box.innerHTML = html;
      } catch (err) {
        console.error(err);
        box.textContent = "שגיאה בטעינת הנתונים.";
      }
    }

    loadStats();
  </script>
</body>
</html>
"""
    return HTMLResponse(content=html)
