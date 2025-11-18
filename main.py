import os
import logging
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from http import HTTPStatus
from typing import Deque, Set, Literal, Optional, Dict, Any, List
import json
import uuid

from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove
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
# לוגינג מתקדם
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log", encoding='utf-8')
    ]
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
        get_user_language,
        update_user_language,
        get_pending_payments_count,
        get_user,
        get_social_posts,
        get_token_sales
    )
    DB_AVAILABLE = True
    logger.info("DB module loaded successfully, DB logging enabled.")
except Exception as e:
    logger.warning("DB not available (missing db.py or error loading it): %s", e)
    DB_AVAILABLE = False

    # יצירת פונקציות דמה במקרה שאין DB
    def init_schema():
        pass

    def log_payment(user_id: int, username: str, payment_method: str):
        logger.info(f"Payment logged - User: {user_id}, Method: {payment_method}")

    def update_payment_status(user_id: int, status: str, reason: str = None):
        logger.info(f"Payment status updated - User: {user_id}, Status: {status}")

    def store_user(user_id: int, username: str = None, first_name: str = None, last_name: str = None):
        logger.info(f"User stored - ID: {user_id}, Username: {username}")

    def add_referral(referrer_id: int, referred_id: int, source: str = "bot_start"):
        logger.info(f"Referral added - From: {referrer_id}, To: {referred_id}")

    def get_top_referrers(limit: int = 10):
        return []

    def get_monthly_payments(year: int, month: int):
        return []

    def get_approval_stats():
        return {"total": 0, "approved": 0, "pending": 0, "rejected": 0}

    def create_reward(user_id: int, points: float, reason: str, reward_type: str = "slh_points"):
        logger.info(f"Reward created - User: {user_id}, Points: {points}")

    def ensure_promoter(user_id: int):
        logger.info(f"Promoter ensured - User: {user_id}")

    def update_promoter_settings(user_id: int, bank_details: str = None, personal_group_link: str = None):
        logger.info(f"Promoter settings updated - User: {user_id}")

    def get_promoter_summary(user_id: int):
        return None

    def incr_metric(metric_name: str, value: int = 1):
        logger.info(f"Metric incremented - {metric_name}: {value}")

    def get_metric(metric_name: str):
        return 0

    def get_user_language(user_id: int):
        return 'he'

    def update_user_language(user_id: int, language: str):
        logger.info(f"User language updated - User: {user_id}, Language: {language}")

    def get_pending_payments_count(user_id: int):
        return 0

    def get_user(user_id: int):
        return None

    def get_social_posts(limit: int = 20):
        return []

    def get_token_sales(limit: int = 50):
        return []

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

# הגדרות TON
TON_WALLET = os.environ.get("TON_WALLET", "UQCr743gEr_nqV_0SBkSp3CtYS_15R3LDLBvLmKeEv7XdGvp")
TON_DISCOUNT_PERCENT = 10  # 10% הנחה
TON_DISCOUNTED_PRICE = 35  # מחיר לאחר הנחה

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

# פרטי TON
TON_DETAILS = (
    f"💎 *תשלום ב-TON עם {TON_DISCOUNT_PERCENT}% הנחה!*\n\n"
    
    f"🏦 *פרטי הארנק:*\n"
    f"`{TON_WALLET}`\n\n"
    
    f"💰 *מחיר רגיל:* 39 ₪\n"
    f"💰 *מחיר לאחר הנחה:* {TON_DISCOUNTED_PRICE} ₪\n"
    f"🎁 *הנחה:* {TON_DISCOUNT_PERCENT}%\n\n"
    
    f"📋 *איך משלמים?*\n"
    f"1. פתחו את ארנק TON שלכם\n"
    f"2. שלחו את הסכום לארנק למעלה\n"
    f"3. שמרו צילום מסך של ההעברה\n"
    f"4. שלחו את הצילום לבוט\n\n"
    
    f"⚡ *יתרונות תשלום ב-TON:*\n"
    f"• הנחה {TON_DISCOUNT_PERCENT}%\n"
    f"• העברה מיידית\n"
    f"• עמלות נמוכות\n"
    f"• ביטחון גבוה\n"
    f"• תמיכה ברשת מתקדמת\n\n"
    
    f"🚀 *הצטרף לקהילה המתקדמת עם טכנולוגיית TON!*"
)

ADMIN_IDS = {DEVELOPER_USER_ID}
PayMethod = Literal["bank", "paybox", "ton"]

# =========================
# מערכת תרגום
# =========================
class TranslationManager:
    def __init__(self):
        self.translations = {
            'he': self._hebrew_translations(),
            'en': self._english_translations(),
            'ru': self._russian_translations(),
            'ar': self._arabic_translations()
        }
    
    def _hebrew_translations(self):
        return {
            # תפריט ראשי
            "welcome": "🎉 *ברוך הבא לנכס הדיגיטלי המניב שלך!*",
            "main_menu": "📱 *תפריט ראשי*",
            "join_community": "🚀 הצטרפות לקהילת העסקים (39 ₪)",
            "digital_asset_info": "💎 מה זה הנכס הדיגיטלי?",
            "share_gateway": "🔗 שתף את שער הקהילה",
            "slh_vision": "🌟 חזון SLH",
            "my_area": "👤 האזור האישי שלי",
            "support": "🆘 תמיכה",
            
            # תשלומים
            "payment_received": "✅ *אישור התשלום התקבל!*",
            "payment_under_review": "האישור נשלח לצוות שלנו לאימות.\nתקבל הודעה עם הנכס הדיגיטלי שלך בתוך זמן קצר.",
            "payment_approved": "🎉 *התשלום אושר! ברוך הבא לבעלי הנכסים!*",
            "payment_rejected": "❌ *אישור התשלום נדחה*",
            
            # כפתורים
            "back": "⬅ חזרה",
            "approve": "✅ אשר תשלום",
            "reject": "❌ דחה תשלום",
            "bank_transfer": "🏦 העברה בנקאית",
            "bit_paybox": "📲 ביט / פייבוקס / PayPal",
            "ton_payment": f"💎 טלגרם (TON) - {TON_DISCOUNT_PERCENT}% הנחה!",
            
            # הודעות מערכת
            "new_user_start": "🚀 *הפעלת בוט חדשה - Buy_My_Shop*",
            "payment_confirmation": "💰 *אישור תשלום חדש התקבל!*",
            "admin_approval_notice": "👤 *נדרשת אישור מנהל*",
            
            # TON
            "ton_discount": f"🎊 *קבל {TON_DISCOUNT_PERCENT}% הנחה כאשר אתה משלם באמצעות TON!*",
            "ton_wallet": f"💎 *ארנק TON:* `{TON_WALLET}`",
            "ton_instructions": TON_DETAILS,
            "ton_payment_benefits": (
                f"🎯 *למה לשלם ב-TON?*\n\n"
                f"• 💰 *הנחה {TON_DISCOUNT_PERCENT}%* - חוסך לך כסף\n"
                f"• ⚡ *מהירות* - העברה מיידית\n"
                f"• 🔒 *בטיחות* - טכנולוגיה מתקדמת\n"
                f"• 💎 *עתידי* - רשת TON היא העתיד\n"
                f"• 🌐 *גלובלי* - מתאים לכל העולם\n\n"
                f"*הוזל מחיר מיוחד למשתמשי TON!*"
            )
        }
    
    def _english_translations(self):
        return {
            "welcome": "🎉 *Welcome to your profitable digital asset!*",
            "main_menu": "📱 *Main Menu*",
            "join_community": "🚀 Join Business Community (39 ₪)",
            "digital_asset_info": "💎 What is the Digital Asset?",
            "share_gateway": "🔗 Share Community Gateway",
            "slh_vision": "🌟 SLH Vision",
            "my_area": "👤 My Personal Area",
            "support": "🆘 Support",
            
            "payment_received": "✅ *Payment Confirmation Received!*",
            "payment_under_review": "The confirmation has been sent to our team for verification.\nYou will receive your digital asset shortly.",
            "payment_approved": "🎉 *Payment Approved! Welcome Asset Owner!*",
            "payment_rejected": "❌ *Payment Approval Rejected*",
            
            "back": "⬅ Back",
            "approve": "✅ Approve Payment",
            "reject": "❌ Reject Payment",
            "bank_transfer": "🏦 Bank Transfer",
            "bit_paybox": "📲 Bit / Paybox / PayPal",
            "ton_payment": f"💎 Telegram (TON) - {TON_DISCOUNT_PERCENT}% discount!",
            
            "new_user_start": "🚀 *New Bot Activation - Buy_My_Shop*",
            "payment_confirmation": "💰 *New Payment Confirmation Received!*",
            "admin_approval_notice": "👤 *Admin Approval Required*",
            
            # TON
            "ton_discount": f"🎊 *Get {TON_DISCOUNT_PERCENT}% discount when you pay with TON!*",
            "ton_wallet": f"💎 *TON Wallet:* `{TON_WALLET}`",
            "ton_instructions": (
                f"💎 *Payment with TON - {TON_DISCOUNT_PERCENT}% Discount!*\n\n"
                
                f"🏦 *Wallet Details:*\n"
                f"`{TON_WALLET}`\n\n"
                
                f"💰 *Regular Price:* 39 ₪\n"
                f"💰 *Discounted Price:* {TON_DISCOUNTED_PRICE} ₪\n"
                f"🎁 *Discount:* {TON_DISCOUNT_PERCENT}%\n\n"
                
                f"📋 *How to pay?*\n"
                f"1. Open your TON wallet\n"
                f"2. Send the amount to the wallet above\n"
                f"3. Save a screenshot of the transfer\n"
                f"4. Send the screenshot to the bot\n\n"
                
                f"⚡ *TON Payment Benefits:*\n"
                f"• {TON_DISCOUNT_PERCENT}% discount\n"
                f"• Instant transfer\n"
                f"• Low fees\n"
                f"• High security\n"
                f"• Advanced network support\n\n"
                
                f"🚀 *Join the advanced community with TON technology!*"
            ),
            "ton_payment_benefits": (
                f"🎯 *Why pay with TON?*\n\n"
                f"• 💰 *{TON_DISCOUNT_PERCENT}% Discount* - Saves you money\n"
                f"• ⚡ *Speed* - Instant transfer\n"
                f"• 🔒 *Security* - Advanced technology\n"
                f"• 💎 *Future-proof* - TON network is the future\n"
                f"• 🌐 *Global* - Suitable for the whole world\n\n"
                f"*Special discounted price for TON users!*"
            )
        }
    
    def _russian_translations(self):
        return {
            "welcome": "🎉 *Добро пожаловать в ваш прибыльный цифровой актив!*",
            "main_menu": "📱 *Главное меню*",
            "join_community": "🚀 Присоединиться к бизнес-сообществу (39 ₪)",
            "digital_asset_info": "💎 Что такое цифровой актив?",
            "share_gateway": "🔗 Поделиться входом в сообщество",
            "slh_vision": "🌟 Видение SLH",
            "my_area": "👤 Мой личный кабинет",
            "support": "🆘 Поддержка",
            
            "payment_received": "✅ *Подтверждение оплаты получено!*",
            "payment_under_review": "Подтверждение отправлено нашей команде для проверки.\nВы получите ваш цифровой актив в ближайшее время.",
            "payment_approved": "🎉 *Оплата подтверждена! Добро пожаловать, владелец актива!*",
            "payment_rejected": "❌ *Подтверждение оплаты отклонено*",
            
            "back": "⬅ Назад",
            "approve": "✅ Подтвердить оплату",
            "reject": "❌ Отклонить оплату",
            "bank_transfer": "🏦 Банковский перевод",
            "bit_paybox": "📲 Bit / Paybox / PayPal",
            "ton_payment": f"💎 Telegram (TON) - {TON_DISCOUNT_PERCENT}% скидка!",
            
            "new_user_start": "🚀 *Новая активация бота - Buy_My_Shop*",
            "payment_confirmation": "💰 *Получено новое подтверждение оплаты!*",
            "admin_approval_notice": "👤 *Требуется подтверждение администратора*",
            
            # TON
            "ton_discount": f"🎊 *Получите {TON_DISCOUNT_PERCENT}% скидку при оплате через TON!*",
            "ton_wallet": f"💎 *TON кошелек:* `{TON_WALLET}`",
            "ton_instructions": (
                f"💎 *Оплата через TON - {TON_DISCOUNT_PERCENT}% Скидка!*\n\n"
                
                f"🏦 *Детали кошелька:*\n"
                f"`{TON_WALLET}`\n\n"
                
                f"💰 *Обычная цена:* 39 ₪\n"
                f"💰 *Цена со скидкой:* {TON_DISCOUNTED_PRICE} ₪\n"
                f"🎁 *Скидка:* {TON_DISCOUNT_PERCENT}%\n\n"
                
                f"📋 *Как оплатить?*\n"
                f"1. Откройте ваш TON кошелек\n"
                f"2. Отправьте сумму на кошелек выше\n"
                f"3. Сохраните скриншот перевода\n"
                f"4. Отправьте скриншот боту\n\n"
                
                f"⚡ *Преимущества оплаты TON:*\n"
                f"• Скидка {TON_DISCOUNT_PERCENT}%\n"
                f"• Мгновенный перевод\n"
                f"• Низкие комиссии\n"
                f"• Высокая безопасность\n"
                f"• Поддержка передовой сети\n\n"
                
                f"🚀 *Присоединяйтесь к передовому сообществу с технологией TON!*"
            ),
            "ton_payment_benefits": (
                f"🎯 *Почему оплачивать через TON?*\n\n"
                f"• 💰 *{TON_DISCOUNT_PERCENT}% Скидка* - Экономит вам деньги\n"
                f"• ⚡ *Скорость* - Мгновенный перевод\n"
                f"• 🔒 *Безопасность* - Передовая технология\n"
                f"• 💎 *Будущее* - Сеть TON это будущее\n"
                f"• 🌐 *Глобальный* - Подходит для всего мира\n\n"
                f"*Специальная дисконтная цена для пользователей TON!*"
            )
        }
    
    def _arabic_translations(self):
        return {
            "welcome": "🎉 *مرحبًا بك في أصولك الرقمية المربحة!*",
            "main_menu": "📱 *القائمة الرئيسية*",
            "join_community": "🚀 الانضمام إلى مجتمع الأعمال (39 ₪)",
            "digital_asset_info": "💎 ما هي الأصول الرقمية؟",
            "share_gateway": "🔗 مشارحة بوابة المجتمع",
            "slh_vision": "🌟 رؤية SLH",
            "my_area": "👤 منطقتي الشخصية",
            "support": "🆘 الدعم",
            
            "payment_received": "✅ *تم استلام تأكيد الدفع!*",
            "payment_under_review": "تم إرسال التأكيد إلى فريقنا للتحقق.\nستستلم أصولك الرقمية قريبًا.",
            "payment_approved": "🎉 *تم الموافقة على الدفع! مرحبًا بك مالک الأصول!*",
            "payment_rejected": "❌ *تم رفض تأكيد الدفع*",
            
            "back": "⬅ رجوع",
            "approve": "✅ الموافقة على الدفع",
            "reject": "❌ رفض الدفع",
            "bank_transfer": "🏦 تحويل بنكي",
            "bit_paybox": "📲 بت / Paybox / PayPal",
            "ton_payment": f"💎 Telegram (TON) - {TON_DISCOUNT_PERCENT}% خصم!",
            
            "new_user_start": "🚀 *تفعيل بوت جديد - Buy_My_Shop*",
            "payment_confirmation": "💰 *تم استلام تأكيد دفع جديد!*",
            "admin_approval_notice": "👤 *مطلوب موافقة المسؤول*",
            
            # TON
            "ton_discount": f"🎊 *احصل على خصم {TON_DISCOUNT_PERCENT}% عند الدفع باستخدام TON!*",
            "ton_wallet": f"💎 *محفظة TON:* `{TON_WALLET}`",
            "ton_instructions": (
                f"💎 *الدفع باستخدام TON - {TON_DISCOUNT_PERCENT}% خصم!*\n\n"
                
                f"🏦 *تفاصيل المحفظة:*\n"
                f"`{TON_WALLET}`\n\n"
                
                f"💰 *السعر العادي:* 39 ₪\n"
                f"💰 *السعر بعد الخصم:* {TON_DISCOUNTED_PRICE} ₪\n"
                f"🎁 *الخصم:* {TON_DISCOUNT_PERCENT}%\n\n"
                
                f"📋 *كيف تدفع؟*\n"
                f"1. افتح محفظة TON الخاصة بك\n"
                f"2. أرسل المبلغ إلى المحفظة أعلاه\n"
                f"3. احفظ لقطة شاشة للتحويل\n"
                f"4. أرسل لقطة الشاشة إلى البوت\n\n"
                
                f"⚡ *مزايا الدفع بـ TON:*\n"
                f"• خصم {TON_DISCOUNT_PERCENT}%\n"
                f"• تحويل فوري\n"
                f"• رسوم منخفضة\n"
                f"• أمان عالي\n"
                f"• دعم شبكة متقدمة\n\n"
                
                f"🚀 *انضم إلى المجتمع المتقدم مع تقنية TON!*"
            ),
            "ton_payment_benefits": (
                f"🎯 *لماذا تدفع بـ TON؟*\n\n"
                f"• 💰 *خصم {TON_DISCOUNT_PERCENT}%* - يوفر لك المال\n"
                f"• ⚡ *السرعة* - تحويل فوري\n"
                f"• 🔒 *الأمان* - تقنية متقدمة\n"
                f"• 💎 *مستقبلي* - شبكة TON هي المستقبل\n"
                f"• 🌐 *عالمي* - مناسب للعالم أجمع\n\n"
                f"*سعر مخفض خاص لمستخدمي TON!*"
            )
        }
    
    def get_text(self, key: str, lang: str = 'he') -> str:
        """מחזיר טקסט מתורגם"""
        return self.translations.get(lang, self.translations['he']).get(key, key)
    
    def get_user_language(self, user_id: int) -> str:
        """מחזיר את שפת המשתמש"""
        if not DB_AVAILABLE:
            return 'he'
        try:
            return get_user_language(user_id) or 'he'
        except:
            return 'he'

trans_manager = TranslationManager()

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
# מקלדת יציבה (Reply Keyboard)
# =========================
def get_stable_keyboard(lang: str = 'he') -> ReplyKeyboardMarkup:
    """מחזיר מקלדת יציבה עם כפתורים קבועים"""
    keyboard = [
        [
            KeyboardButton(trans_manager.get_text("join_community", lang)),
            KeyboardButton(trans_manager.get_text("digital_asset_info", lang))
        ],
        [
            KeyboardButton(trans_manager.get_text("share_gateway", lang)),
            KeyboardButton(trans_manager.get_text("slh_vision", lang))
        ],
        [
            KeyboardButton(trans_manager.get_text("my_area", lang)),
            KeyboardButton(trans_manager.get_text("support", lang))
        ]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# =========================
# API Routes for Website
# =========================

@app.get("/")
async def serve_site():
    """מגיש את אתר האינטרנט"""
    return FileResponse("docs/index.html")

@app.get("/site")
async def serve_site_alt():
    """מגיש את אתר האינטרנט (alias)"""
    return FileResponse("docs/index.html")

@app.get("/api/posts")
async def get_posts(limit: int = 20):
    """API לפוסטים חברתיים"""
    if not DB_AVAILABLE:
        return {"items": []}
    
    try:
        posts = get_social_posts(limit)
        return {"items": posts}
    except Exception as e:
        logger.error("Failed to get posts: %s", e)
        return {"items": []}

@app.get("/api/token/sales")
async def get_token_sales(limit: int = 50):
    """API למכירות טוקנים"""
    if not DB_AVAILABLE:
        return {"items": []}
    
    try:
        sales = get_token_sales(limit)
        return {"items": sales}
    except Exception as e:
        logger.error("Failed to get token sales: %s", e)
        return {"items": []}

@app.get("/api/token/price")
async def get_token_price():
    """API לשער הטוקן"""
    return {
        "official_price_nis": 444,
        "currency": "ILS",
        "updated_at": datetime.utcnow().isoformat()
    }

@app.get("/config/public")
async def get_public_config():
    """API להגדרות ציבוריות"""
    return {
        "slh_nis": 39,
        "ton_discounted_price": TON_DISCOUNTED_PRICE,
        "ton_discount_percent": TON_DISCOUNT_PERCENT,
        "business_group_link": os.environ.get("COMMUNITY_GROUP_LINK", "https://t.me/+HIzvM8sEgh1kNWY0"),
        "paybox_url": os.environ.get("PAYBOX_URL"),
        "bit_url": os.environ.get("BIT_URL"),
        "paypal_url": os.environ.get("PAYPAL_URL"),
        "ton_wallet": TON_WALLET
    }

@app.get("/admin/dashboard")
async def admin_dashboard(token: str = ""):
    """דשבורד ניהול HTML"""
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
                    document.getElementById('stats').innerHTML = `
                        <div class="stats">
                            <div class="card">משתמשים: ${data.payments_stats?.total || 0}</div>
                            <div class="card">אושרו: ${data.payments_stats?.approved || 0}</div>
                            <div class="card">ממתינים: ${data.payments_stats?.pending || 0}</div>
                        </div>
                    `;
                });
        </script>
    </body>
    </html>
    """
    return HTMLResponse(html_content)

@app.post("/api/telegram-login")
async def handle_telegram_login(user_data: dict):
    """מטפל בהתחברות מטלגרם"""
    try:
        print(f"🔐 Telegram login: {user_data}")
        
        # כאן תוכל לשמור את המשתמש ב-DB
        if DB_AVAILABLE:
            try:
                store_user(
                    user_id=user_data['id'],
                    username=user_data.get('username'),
                    first_name=user_data.get('first_name'),
                    last_name=user_data.get('last_name')
                )
            except Exception as e:
                logger.error(f"Failed to store Telegram user: {e}")
        
        return {
            "status": "success", 
            "message": "Login successful",
            "user_id": user_data['id']
        }
        
    except Exception as e:
        logger.error(f"Telegram login error: {e}")
        return {"status": "error", "message": str(e)}

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
        "ton_discount": f"{TON_DISCOUNT_PERCENT}%",
        "version": "2.0.0"
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

    return {
        "db": "enabled",
        "payments_stats": stats,
        "monthly_breakdown": monthly,
        "top_referrers": top_ref,
        "system": {
            "ton_discount": TON_DISCOUNT_PERCENT,
            "ton_wallet": TON_WALLET,
            "version": "2.0.0"
        }
    }

# =========================
# עזרי UI (מקשים)
# =========================

def main_menu_keyboard(lang: str = 'he') -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(trans_manager.get_text("join_community", lang), callback_data="join"),
        ],
        [
            InlineKeyboardButton(trans_manager.get_text("digital_asset_info", lang), callback_data="digital_asset_info"),
        ],
        [
            InlineKeyboardButton(trans_manager.get_text("share_gateway", lang), callback_data="share"),
        ],
        [
            InlineKeyboardButton(trans_manager.get_text("slh_vision", lang), callback_data="vision"),
        ],
        [
            InlineKeyboardButton(trans_manager.get_text("my_area", lang), callback_data="my_area"),
        ],
        [
            InlineKeyboardButton(trans_manager.get_text("support", lang), callback_data="support"),
        ],
    ])

def payment_methods_keyboard(lang: str = 'he') -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(trans_manager.get_text("bank_transfer", lang), callback_data="pay_bank"),
        ],
        [
            InlineKeyboardButton(trans_manager.get_text("bit_paybox", lang), callback_data="pay_paybox"),
        ],
        [
            InlineKeyboardButton(trans_manager.get_text("ton_payment", lang), callback_data="pay_ton"),
        ],
        [
            InlineKeyboardButton(trans_manager.get_text("back", lang), callback_data="back_main"),
        ],
    ])

def payment_links_keyboard(lang: str = 'he') -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("📲 תשלום בפייבוקס", url=PAYBOX_URL)],
        [InlineKeyboardButton("📲 תשלום בביט", url=BIT_URL)],
        [InlineKeyboardButton("💳 תשלום ב-PayPal", url=PAYPAL_URL)],
        [InlineKeyboardButton(trans_manager.get_text("back", lang), callback_data="back_main")],
    ]
    return InlineKeyboardMarkup(buttons)

def ton_payment_keyboard(lang: str = 'he') -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💎 שלח תשלום TON", url=f"ton://transfer/{TON_WALLET}"),
        ],
        [
            InlineKeyboardButton("📖 מדריך TON", url="https://ton.org/learn"),
        ],
        [
            InlineKeyboardButton(trans_manager.get_text("back", lang), callback_data="join"),
        ],
    ])

def my_area_keyboard(lang: str = 'he') -> InlineKeyboardMarkup:
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
            InlineKeyboardButton("💎 TON & הנחות", callback_data="ton_info"),
        ],
        [
            InlineKeyboardButton(trans_manager.get_text("back", lang), callback_data="back_main"),
        ],
    ])

def support_keyboard(lang: str = 'he') -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("קבוצת תמיכה", url=SUPPORT_GROUP_LINK),
        ],
        [
            InlineKeyboardButton("פניה למתכנת", url=f"tg://user?id={DEVELOPER_USER_ID}"),
        ],
        [
            InlineKeyboardButton("💎 תמיכה ב-TON", callback_data="ton_support"),
        ],
        [
            InlineKeyboardButton(trans_manager.get_text("back", lang), callback_data="back_main"),
        ],
    ])

def admin_approval_keyboard(user_id: int, lang: str = 'he') -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(trans_manager.get_text("approve", lang), callback_data=f"adm_approve:{user_id}"),
            InlineKeyboardButton(trans_manager.get_text("reject", lang), callback_data=f"adm_reject:{user_id}"),
        ],
    ])

def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🇮🇱 עברית", callback_data="lang_he"),
            InlineKeyboardButton("🇺🇸 English", callback_data="lang_en"),
        ],
        [
            InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
            InlineKeyboardButton("🇸🇦 العربية", callback_data="lang_ar"),
        ]
    ])

# =========================
# Error Handler
# =========================

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """לוכד שגיאות שלא טופלו"""
    logger.error("Exception while handling an update:", exc_info=context.error)
    
    try:
        # נסה להודיע למשתמש על השגיאה
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "❌ אירעה שגיאה בלתי צפויה. נסה שוב או פנה לתמיכה.",
                reply_markup=ReplyKeyboardRemove()
            )
    except:
        pass

# =========================
# Handlers – לוגיקת הבוט
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        message = update.message or update.effective_message
        if not message:
            return

        user = update.effective_user
        lang = trans_manager.get_user_language(user.id) if user else 'he'

        # בדיקה אם זה משתמש חדש או תהליך תקוע
        is_new_user = False
        has_stuck_payment = False
        
        if DB_AVAILABLE and user:
            try:
                # בדיקה אם משתמש חדש
                existing_user = get_user(user.id)
                if not existing_user:
                    is_new_user = True
                    store_user(user.id, user.username)
                    incr_metric("total_starts")
                
                # בדיקה אם יש תשלום תלוי יותר מ-24 שעות
                pending_count = get_pending_payments_count(user.id)
                if pending_count > 0:
                    # כאן אפשר להוסיף לוגיקה לבדיקת זמן
                    has_stuck_payment = True
                    
            except Exception as e:
                logger.error("Failed to check user status: %s", e)

        # לוג לקבוצת התשלומים רק למשתמשים חדשים או תהליך תקוע
        if (is_new_user or has_stuck_payment) and PAYMENTS_LOG_CHAT_ID and update.effective_user:
            try:
                user = update.effective_user
                username_str = f"@{user.username}" if user.username else "(ללא username)"
                status_note = "🆕 משתמש חדש" if is_new_user else "⚠️ תהליך תקוע"
                
                log_text = (
                    f"{trans_manager.get_text('new_user_start', 'he')}\n\n"
                    f"👤 user_id: `{user.id}`\n"
                    f"📛 username: {username_str}\n"
                    f"💬 chat_id: `{update.effective_chat.id}`\n"
                    f"📊 סטטוס: {status_note}\n"
                    f"🕐 זמן: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                )
                await context.bot.send_message(
                    chat_id=PAYMENTS_LOG_CHAT_ID,
                    text=log_text,
                    parse_mode="Markdown",
                )
            except Exception as e:
                logger.error("Failed to send /start log to payments group: %s", e)

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

        # שליחת הודעת ברוכים הבאים
        welcome_text = {
            'he': (
                "🎉 *ברוך הבא לנכס הדיגיטלי המניב שלך!*\n\n"
                
                "💎 *מה זה הנכס הדיגיטלי?*\n"
                "זהו שער כניסה אישי לקהילת עסקים פעילה. לאחר רכישה תקבל:\n"
                "• לינק אישי להפצה\n"
                "• אפשרות למכור את הנכס הלאה\n"
                "• גישה לקבוצת משחק כללית\n"
                "• מערכת הפניות מתגמלת\n\n"
                
                f"🎊 *הנחה מיוחדת!* {TON_DISCOUNT_PERCENT}% הנחה לתשלום ב-TON\n\n"
                
                "🔄 *איך זה עובד?*\n"
                "1. רוכשים נכס ב-39₪ (או פחות ב-TON)\n"
                "2. מקבלים לינק אישי\n"
                "3. מפיצים - כל רכישה דרך הלינק שלך מתועדת\n"
                "4. מרוויחים מהפצות נוספות\n\n"
                
                "🚀 *מה תקבל?*\n"
                "✅ גישה לקהילת עסקים\n"
                "✅ נכס דיגיטלי אישי\n"
                "✅ לינק הפצה ייחודי\n"
                "✅ אפשרות מכירה חוזרת\n"
                "✅ מערכת הפניות שקופה\n"
                f"✅ {TON_DISCOUNT_PERCENT}% הנחה בתשלומי TON\n\n"
                
                "💼 *הנכס שלך - העסק שלך!*"
            ),
            'en': (
                "🎉 *Welcome to your profitable digital asset!*\n\n"
                
                "💎 *What is the Digital Asset?*\n"
                "This is a personal gateway to an active business community. After purchase you get:\n"
                "• Personal sharing link\n"
                "• Ability to resell the asset\n"
                "• Access to general community group\n"
                "• Rewarding referral system\n\n"
                
                f"🎊 *Special discount!* {TON_DISCOUNT_PERCENT}% discount for TON payment\n\n"
                
                "🔄 *How it works?*\n"
                "1. Buy an asset for 39₪ (or less with TON)\n"
                "2. Get personal link\n"
                "3. Share - every purchase through your link is recorded\n"
                "4. Earn from additional referrals\n\n"
                
                "🚀 *What you get?*\n"
                "✅ Access to business community\n"
                "✅ Personal digital asset\n"
                "✅ Unique sharing link\n"
                "✅ Resale option\n"
                "✅ Transparent referral system\n"
                f"✅ {TON_DISCOUNT_PERCENT}% discount on TON payments\n\n"
                
                "💼 *Your Asset - Your Business!*"
            ),
            'ru': (
                "🎉 *Добро пожаловать в ваш прибыльный цифровой актив!*\n\n"
                
                "💎 *Что такое цифровой актив?*\n"
                "Это персональный вход в активное бизнес-сообщество. После покупки вы получаете:\n"
                "• Персональную ссылку для распространения\n"
                "• Возможность перепродажи актива\n"
                "• Доступ к общей группе сообщества\n"
                "• Вознаграждающую реферальную систему\n\n"
                
                f"🎊 *Специальная скидка!* {TON_DISCOUNT_PERCENT}% скидка за оплату TON\n\n"
                
                "🔄 *Как это работает?*\n"
                "1. Покупаете актив за 39₪ (или меньше с TON)\n"
                "2. Получаете персональную ссылку\n"
                "3. Распространяете - каждая покупка по вашей ссылке записывается\n"
                "4. Зарабатываете на дополнительных рефералах\n\n"
                
                "🚀 *Что вы получаете?*\n"
                "✅ Доступ к бизнес-сообществу\n"
                "✅ Персональный цифровой актив\n"
                "✅ Уникальную ссылку для распространения\n"
                "✅ Опцию перепродажи\n"
                "✅ Прозрачную реферальную систему\n"
                f"✅ {TON_DISCOUNT_PERCENT}% скидка на оплату TON\n\n"
                
                "💼 *Ваш актив - Ваш бизнес!*"
            ),
            'ar': (
                "🎉 *مرحبًا بك في أصولك الرقمية المربحة!*\n\n"
                
                "💎 *ما هي الأصول الرقمية؟*\n"
                "هذا هو المدخل الشخصي لمجتمع الأعمال النشط. بعد الشراء تحصل على:\n"
                "• رابط مشاركة شخصي\n"
                "• إمكانية إعادة بيع الأصل\n"
                "• الوصول إلى مجموعة المجتمع العامة\n"
                "• نظام إحالة مجزي\n\n"
                
                f"🎊 *خصم خاص!* {TON_DISCOUNT_PERCENT}% خصم للدفع بـ TON\n\n"
                
                "🔄 *كيف يعمل؟*\n"
                "1. شراء أصل بـ 39₪ (أو أقل مع TON)\n"
                "2. الحصول على رابط شخصي\n"
                "3. شارك - يتم تسجيل كل عملية شراء through رابطك\n"
                "4. اربح من الإحالات الإضافية\n\n"
                
                "🚀 *ماذا تحصل؟*\n"
                "✅ الوصول إلى مجتمع الأعمال\n"
                "✅ الأصول الرقمية الشخصية\n"
                "✅ رابط مشاركة فريد\n"
                "✅ خيار إعادة البيع\n"
                "✅ نظام إحالة شفاف\n"
                f"✅ {TON_DISCOUNT_PERCENT}% خصم على مدفوعات TON\n\n"
                
                "💼 *أصولك - عملك!*"
            )
        }

        text = welcome_text.get(lang, welcome_text['he'])

        await message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=get_stable_keyboard(lang),
        )

        # הצעה לבחירת שפה אם עדיין לא נבחרה
        if DB_AVAILABLE and (not get_user_language(user.id) or is_new_user):
            lang_prompt = {
                'he': "🌐 *בחר שפה / Choose language*",
                'en': "🌐 *Choose language / اختر اللغة*", 
                'ru': "🌐 *Выберите язык / اختر اللغة*",
                'ar': "🌐 *اختر اللغة / Choose language*"
            }
            await message.reply_text(
                lang_prompt.get(lang, lang_prompt['he']),
                reply_markup=language_keyboard()
            )

    except Exception as e:
        logger.error("Error in start handler: %s", e)
        # נסה לשלוח הודעת שגיאה בסיסית
        try:
            if update.effective_message:
                await update.effective_message.reply_text(
                    "❌ אירעה שגיאה. נסה שוב או פנה לתמיכה.",
                    reply_markup=ReplyKeyboardRemove()
                )
        except:
            pass

async def handle_language_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """מטפל בבחירת שפה"""
    try:
        query = update.callback_query
        await query.answer()
        
        user = update.effective_user
        lang = query.data.replace('lang_', '')
        
        if DB_AVAILABLE and user:
            try:
                update_user_language(user.id, lang)
            except Exception as e:
                logger.error("Failed to update user language: %s", e)
        
        # הודעת אישור
        confirmation = {
            'he': "✅ שפה נבחרה: עברית",
            'en': "✅ Language selected: English", 
            'ru': "✅ Язык выбран: Русский",
            'ar': "✅ تم اختيار اللغة: العربية"
        }
        
        await query.edit_message_text(
            confirmation.get(lang, confirmation['he'])
        )
        
        # שליחת הודעת ברוכים הבאים מחדש בשפה החדשה
        fake_update = Update(update_id=update.update_id, message=query.message)
        await start(fake_update, context)
    except Exception as e:
        logger.error("Error in language selection: %s", e)

async def digital_asset_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        query = update.callback_query
        await query.answer()
        
        user = update.effective_user
        lang = trans_manager.get_user_language(user.id) if user else 'he'

        text = {
            'he': (
                "💎 *הנכס הדיגיטלי - ההזדמנות העסקית שלך!*\n\n"
                
                "🏗 *מה זה בעצם?*\n"
                "נכס דיגיטלי הוא 'שער כניסה' אישי שאתה קונה פעם אחת ומקבל:\n"
                "• לינק אישי משלך\n"
                "• זכות למכור נכסים נוספים\n"
                "• גישה למערכת שלמה\n\n"
                
                f"💰 *מחירים:*\n"
                f"• מחיר רגיל: 39₪\n"
                f"• מחיר TON: {TON_DISCOUNTED_PRICE}₪ ({TON_DISCOUNT_PERCENT}% הנחה!)\n\n"
                
                "💸 *איך מרוויחים?*\n"
                "1. אתה רוכש נכס\n"
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
                "• שקיפות מלאה\n"
                f"• {TON_DISCOUNT_PERCENT}% הנחה בתשלומי TON\n\n"
                
                "🎯 *המטרה:* ליצור רשת עסקית בה כולם מרוויחים!"
            ),
            'en': (
                "💎 *The Digital Asset - Your Business Opportunity!*\n\n"
                
                "🏗 *What is it actually?*\n"
                "A digital asset is a personal 'gateway' that you buy once and get:\n"
                "• Your personal link\n"
                "• Right to sell additional assets\n"
                "• Access to complete system\n\n"
                
                f"💰 *Prices:*\n"
                f"• Regular price: 39₪\n"
                f"• TON price: {TON_DISCOUNTED_PRICE}₪ ({TON_DISCOUNT_PERCENT}% discount!)\n\n"
                
                "💸 *How to earn?*\n"
                "1. You buy an asset\n"
                "2. Get personal sharing link\n"
                "3 *Every person* who buys through your link - purchase recorded to your credit\n"
                "4. Your asset continues to generate income\n\n"
                
                "🔄 *Resale model:*\n"
                "You're not just a 'user' - you're an 'asset owner'!\n"
                "Can sell additional assets to others\n"
                "Every additional purchase is recorded in referral chain\n\n"
                
                "📈 *Advantages:*\n"
                "• Passive income from sharing\n"
                "• Asset that gains value over time\n"
                "• Supportive community\n"
                "• Full transparency\n"
                f"• {TON_DISCOUNT_PERCENT}% discount on TON payments\n\n"
                
                "🎯 *The goal:* Create business network where everyone wins!"
            ),
            'ru': (
                "💎 *Цифровой актив - Ваша бизнес-возможность!*\n\n"
                
                "🏗 *Что это на самом деле?*\n"
                "Цифровой актив - это персональный 'вход', который вы покупаете один раз и получаете:\n"
                "• Вашу персональную ссылку\n"
                "• Право продавать дополнительные активы\n"
                "• Доступ к полной системе\n\n"
                
                f"💰 *Цены:*\n"
                f"• Обычная цена: 39₪\n"
                f"• Цена TON: {TON_DISCOUNTED_PRICE}₪ ({TON_DISCOUNT_PERCENT}% скидка!)\n\n"
                
                "💸 *Как заработать?*\n"
                "1. Вы покупаете актив\n"
                "2. Получаете персональную ссылку для распространения\n"
                "3 *Каждый человек*, который покупает по вашей ссылке - покупка записывается в ваш зачет\n"
                "4. Ваш актив продолжает генерировать доход\n\n"
                
                "🔄 *Модель перепродажи:*\n"
                "Вы не просто 'пользователь' - вы 'владелец актива'!\n"
                "Можете продавать дополнительные активы другим\n"
                "Каждая дополнительная покупка записывается в реферальную цепочку\n\n"
                
                "📈 *Преимущества:*\n"
                "• Пассивный доход от распространения\n"
                "• Актив, который со временем растет в цене\n"
                "• Поддерживающее сообщество\n"
                "• Полная прозрачность\n"
                f"• {TON_DISCOUNT_PERCENT}% скидка на оплату TON\n\n"
                
                "🎯 *Цель:* Создать бизнес-сеть, где выигрывают все!"
            ),
            'ar': (
                "💎 *الأصول الرقمية - فرصة عملك!*\n\n"
                
                "🏗 *ما هو في الواقع؟*\n"
                "الأصل الرقمي هو 'بوابة' شخصية تشتريها once وتحصل على:\n"
                "• رابطك الشخصي\n"
                "• الحق في بيع أصول إضافية\n"
                "• الوصول إلى النظام الكامل\n\n"
                
                f"💰 *الأسعار:*\n"
                f"• السعر العادي: 39₪\n"
                f"• سعر TON: {TON_DISCOUNTED_PRICE}₪ ({TON_DISCOUNT_PERCENT}% خصم!)\n\n"
                
                "💸 *كيف تربح؟*\n"
                "1. تشتري أصلًا\n"
                "2. احصل على رابط مشاركة شخصي\n"
                "3 *كل شخص* يشتري through رابطك - يتم تسجيل الشراء لرصيدك\n"
                "4. أصولك تستمر في تحقيق الدخل\n\n"
                
                "🔄 *نموذج إعادة البيع:*\n"
                "أنت لست مجرد 'مستخدم' - أنت 'مالك أصول'!\n"
                "يمكنك بيع أصول إضافية للآخرين\n"
                "يتم تسجيل كل عملية شراء إضافية في سلسلة الإحالة\n\n"
                
                "📈 *مزايا:*\n"
                "• دخل سلبي من المشاركة\n"
                "• الأصول التي تكتسب قيمة over time\n"
                "• مجتمع داعم\n"
                "• شفافية كاملة\n"
                f"• {TON_DISCOUNT_PERCENT}% خصم على مدفوعات TON\n\n"
                
                "🎯 *الهدف:* إنشاء شبكة أعمال where everyone wins!"
            )
        }

        await query.edit_message_text(
            text.get(lang, text['he']),
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(lang),
        )
    except Exception as e:
        logger.error("Error in digital_asset_info: %s", e)

async def join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        query = update.callback_query
        await query.answer()
        
        user = update.effective_user
        lang = trans_manager.get_user_language(user.id) if user else 'he'

        text = {
            'he': (
                "🔑 *רכישת הנכס הדיגיטלי*\n\n"
                f"💰 *מחירים:*\n"
                f"• מחיר רגיל: 39₪\n"
                f"• מחיר TON: {TON_DISCOUNTED_PRICE}₪ ({TON_DISCOUNT_PERCENT}% הנחה!)\n\n"
                
                "בתמורה תקבל:\n"
                "• נכס דיגיטלי אישי\n"
                "• לינק הפצה ייחודי\n"
                "• גישה לקהילת עסקים\n"
                "• אפשרות למכור נכסים נוספים\n\n"
                
                f"🎊 *הנחה מיוחדת!* {TON_DISCOUNT_PERCENT}% הנחה לתשלום ב-TON\n\n"
                
                "🔄 *איך התהליך עובד?*\n"
                "1. בוחרים אמצעי תשלום\n"
                "2. משלמים (39₪ או פחות ב-TON)\n"
                "3. שולחים אישור תשלום\n"
                "4. מקבלים אישור + לינק אישי\n"
                "5. מתחילים להפיץ!\n\n"
                
                "💼 *זכור:* אתה קונה *נכס* - לא רק 'גישה'!"
            ),
            'en': (
                "🔑 *Digital Asset Purchase*\n\n"
                f"💰 *Prices:*\n"
                f"• Regular price: 39₪\n"
                f"• TON price: {TON_DISCOUNTED_PRICE}₪ ({TON_DISCOUNT_PERCENT}% discount!)\n\n"
                
                "In return you get:\n"
                "• Personal digital asset\n"
                "• Unique sharing link\n"
                "• Access to business community\n"
                "• Ability to sell additional assets\n\n"
                
                f"🎊 *Special discount!* {TON_DISCOUNT_PERCENT}% discount for TON payment\n\n"
                
                "🔄 *How the process works?*\n"
                "1. Choose payment method\n"
                "2. Pay (39₪ or less with TON)\n"
                "3. Send payment confirmation\n"
                "4. Get approval + personal link\n"
                "5. Start sharing!\n\n"
                
                "💼 *Remember:* You're buying an *asset* - not just 'access'!"
            ),
            'ru': (
                "🔑 *Покупка цифрового актива*\n\n"
                f"💰 *Цены:*\n"
                f"• Обычная цена: 39₪\n"
                f"• Цена TON: {TON_DISCOUNTED_PRICE}₪ ({TON_DISCOUNT_PERCENT}% скидка!)\n\n"
                
                "Взамен вы получаете:\n"
                "• Персональный цифровой актив\n"
                "• Уникальную ссылку для распространения\n"
                "• Доступ к бизнес-сообществу\n"
                "• Возможность продавать дополнительные активы\n\n"
                
                f"🎊 *Специальная скидка!* {TON_DISCOUNT_PERCENT}% скидка за оплату TON\n\n"
                
                "🔄 *Как работает процесс?*\n"
                "1. Выбираете способ оплаты\n"
                "2. Платите (39₪ или меньше с TON)\n"
                "3. Отправляете подтверждение оплаты\n"
                "4. Получаете одобрение + персональную ссылку\n"
                "5. Начинаете распространять!\n\n"
                
                "💼 *Помните:* Вы покупаете *актив* - не просто 'доступ'!"
            ),
            'ar': (
                "🔑 *شراء الأصول الرقمية*\n\n"
                f"💰 *الأسعار:*\n"
                f"• السعر العادي: 39₪\n"
                f"• سعر TON: {TON_DISCOUNTED_PRICE}₪ ({TON_DISCOUNT_PERCENT}% خصم!)\n\n"
                
                "في مقابل تحصل على:\n"
                "• الأصول الرقمية الشخصية\n"
                "• رابط مشاركة فريد\n"
                "• الوصول إلى مجتمع الأعمال\n"
                "• القدرة على بيع أصول إضافية\n\n"
                
                f"🎊 *خصم خاص!* {TON_DISCOUNT_PERCENT}% خصم للدفع بـ TON\n\n"
                
                "🔄 *كيف تعمل العملية؟*\n"
                "1. اختر طريقة الدفع\n"
                "2. ادفع (39₪ أو أقل مع TON)\n"
                "3. أرسل تأكيد الدفع\n"
                "4. احصل على الموافقة + الرابط الشخصي\n"
                "5. ابدأ المشاركة!\n\n"
                
                "💼 *تذكر:* أنت تشتري *أصولًا* - ليس مجرد 'وصول'!"
            )
        }

        await query.edit_message_text(
            text.get(lang, text['he']),
            parse_mode="Markdown",
            reply_markup=payment_methods_keyboard(lang),
        )
    except Exception as e:
        logger.error("Error in join_callback: %s", e)

async def my_area_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        query = update.callback_query
        await query.answer()

        user = update.effective_user
        if not user:
            return

        lang = trans_manager.get_user_language(user.id)

        if DB_AVAILABLE:
            summary = get_promoter_summary(user.id)
            if summary:
                personal_link = build_personal_share_link(user.id)
                bank = summary.get("bank_details") or "לא הוגדר"
                p_group = summary.get("personal_group_link") or "לא הוגדר"
                total_ref = summary.get("total_referrals", 0)
                
                text = {
                    'he': (
                        "👤 *האזור האישי שלך*\n\n"
                        f"🔗 *לינק אישי:*\n`{personal_link}`\n\n"
                        f"🏦 *פרטי בנק:*\n{bank}\n\n"
                        f"👥 *קבוצה אישית:*\n{p_group}\n\n"
                        f"📊 *הפניות:* {total_ref}\n\n"
                        f"💎 *הנחות TON:* {TON_DISCOUNT_PERCENT}% הנחה\n\n"
                        "*ניהול נכס:*"
                    ),
                    'en': (
                        "👤 *Your Personal Area*\n\n"
                        f"🔗 *Personal link:*\n`{personal_link}`\n\n"
                        f"🏦 *Bank details:*\n{bank}\n\n"
                        f"👥 *Personal group:*\n{p_group}\n\n"
                        f"📊 *Referrals:* {total_ref}\n\n"
                        f"💎 *TON Discounts:* {TON_DISCOUNT_PERCENT}% discount\n\n"
                        "*Asset management:*"
                    ),
                    'ru': (
                        "👤 *Ваша личная зона*\n\n"
                        f"🔗 *Персональная ссылка:*\n`{personal_link}`\n\n"
                        f"🏦 *Банковские реквизиты:*\n{bank}\n\n"
                        f"👥 *Персональная группа:*\n{p_group}\n\n"
                        f"📊 *Рефералы:* {total_ref}\n\n"
                        f"💎 *Скидки TON:* {TON_DISCOUNT_PERCENT}% скидка\n\n"
                        "*Управление активом:*"
                    ),
                    'ar': (
                        "👤 *منطقتك الشخصية*\n\n"
                        f"🔗 *رابط شخصي:*\n`{personal_link}`\n\n"
                        f"🏦 *تفاصيل البنك:*\n{bank}\n\n"
                        f"👥 *مجموعة شخصية:*\n{p_group}\n\n"
                        f"📊 *الإحالات:* {total_ref}\n\n"
                        f"💎 *خصومات TON:* {TON_DISCOUNT_PERCENT}% خصم\n\n"
                        "*إدارة الأصول:*"
                    )
                }
            else:
                text = {
                    'he': (
                        "👤 *האזור האישי שלך*\n\n"
                        "עדיין אין לך נכס דיגיטלי.\n"
                        "רכש נכס כדי לקבל:\n"
                        "• לינק אישי להפצה\n"
                        "• אפשרות למכור נכסים\n"
                        "• גישה למערכת המלאה\n"
                        f"• {TON_DISCOUNT_PERCENT}% הנחה בתשלומי TON"
                    ),
                    'en': (
                        "👤 *Your Personal Area*\n\n"
                        "You don't have a digital asset yet.\n"
                        "Purchase an asset to get:\n"
                        "• Personal sharing link\n"
                        "• Ability to sell assets\n"
                        "• Access to full system\n"
                        f"• {TON_DISCOUNT_PERCENT}% discount on TON payments"
                    ),
                    'ru': (
                        "👤 *Ваша личная зона*\n\n"
                        "У вас еще нет цифрового актива.\n"
                        "Приобретите актив, чтобы получить:\n"
                        "• Персональную ссылку для распространения\n"
                        "• Возможность продавать активы\n"
                        "• Доступ к полной системе\n"
                        f"• {TON_DISCOUNT_PERCENT}% скидка на оплату TON"
                    ),
                    'ar': (
                        "👤 *منطقتك الشخصية*\n\n"
                        "ليس لديك أصول رقمية after.\n"
                        "شراء أصول للحصول على:\n"
                        "• رابط مشاركة شخصي\n"
                        "• القدرة على بيع الأصول\n"
                        "• الوصول إلى النظام الكامل\n"
                        f"• {TON_DISCOUNT_PERCENT}% خصم على مدفوعات TON"
                    )
                }
        else:
            text = {
                'he': "מערכת הזמנית לא זמינת. נסה שוב מאוחר יותר.",
                'en': "Temporary system unavailable. Try again later.",
                'ru': "Временная система недоступна. Попробуйте позже.",
                'ar': "النظام المؤقت غير متاح. حاول مرة أخرى later."
            }

        await query.edit_message_text(
            text.get(lang, text['he']),
            parse_mode="Markdown",
            reply_markup=my_area_keyboard(lang),
        )
    except Exception as e:
        logger.error("Error in my_area_callback: %s", e)

async def payment_method_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        query = update.callback_query
        await query.answer()
        data = query.data
        
        user = update.effective_user
        lang = trans_manager.get_user_language(user.id) if user else 'he'

        if data == "pay_ton":
            # טיפול מיוחד בתשלום TON
            ton_instructions = trans_manager.get_text("ton_instructions", lang)
            ton_benefits = trans_manager.get_text("ton_payment_benefits", lang)
            
            full_message = f"{ton_instructions}\n\n{ton_benefits}"
            
            await query.edit_message_text(
                full_message,
                parse_mode="Markdown",
                reply_markup=ton_payment_keyboard(lang),
            )
            return

        method_text = ""
        if data == "pay_bank":
            method_text = BANK_DETAILS
        elif data == "pay_paybox":
            method_text = "📲 *תשלום בביט / פייבוקס / PayPal*"

        text = {
            'he': (
                f"{method_text}\n\n"
                "💎 *לאחר התשלום:*\n"
                "1. שלח צילום מסך של האישור\n"
                "2. נאשר בתוך זמן קצר\n"
                "3. תקבל את הנכס הדיגיטלי שלך\n"
                "4. תוכל להתחיל להפיץ ולהרוויח!\n\n"
                "*זכור:* אתה רוכש *נכס* - לא רק גישה!"
            ),
            'en': (
                f"{method_text}\n\n"
                "💎 *After payment:*\n"
                "1. Send screenshot of confirmation\n"
                "2. We'll approve shortly\n"
                "3. You'll receive your digital asset\n"
                "4. You can start sharing and earning!\n\n"
                "*Remember:* You're buying an *asset* - not just access!"
            ),
            'ru': (
                f"{method_text}\n\n"
                "💎 *После оплаты:*\n"
                "1. Отправьте скриншот подтверждения\n"
                "2. Мы одобрим в ближайшее время\n"
                "3. Вы получите ваш цифровой актив\n"
                "4. Вы можете начать распространять и зарабатывать!\n\n"
                "*Помните:* Вы покупаете *актив* - не просто доступ!"
            ),
            'ar': (
                f"{method_text}\n\n"
                "💎 *بعد الدفع:*\n"
                "1. أرسل لقطة شاشة للتأكيد\n"
                "2. سنوافق shortly\n"
                "3. سوف تتلقى أصولك الرقمية\n"
                "4. يمكنك البدء في المشاركة والربح!\n\n"
                "*تذكر:* أنت تشتري *أصولًا* - ليس مجرد وصول!"
            )
        }

        await query.edit_message_text(
            text.get(lang, text['he']),
            parse_mode="Markdown",
            reply_markup=payment_links_keyboard(lang),
        )
    except Exception as e:
        logger.error("Error in payment_method_callback: %s", e)

async def handle_payment_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
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
            "ton": f"טלגרם (TON) - {TON_DISCOUNT_PERCENT}% הנחה",
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

        # הודעת אישור תשלום לקבוצת הלוגים
        caption_log = (
            f"{trans_manager.get_text('payment_confirmation', 'he')}\n\n"
            f"👤 user_id: `{user.id}`\n"
            f"📛 username: {username}\n"
            f"💳 שיטת תשלום: {pay_method_text}\n"
            f"🕐 זמן: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"*{trans_manager.get_text('admin_approval_notice', 'he')}*"
        )

        try:
            await context.bot.send_photo(
                chat_id=PAYMENTS_LOG_CHAT_ID,
                photo=file_id,
                caption=caption_log,
                parse_mode="Markdown",
                reply_markup=admin_approval_keyboard(user.id, 'he'),
            )
        except Exception as e:
            logger.error("Failed to send payment to log group: %s", e)

        # הודעת אישור למשתמש
        user_lang = trans_manager.get_user_language(user.id)
        confirmation_text = {
            'he': (
                "✅ *אישור התשלום התקבל!*\n\n"
                "האישור נשלח לצוות שלנו לאימות.\n"
                "תקבל הודעה עם הנכס הדיגיטלי שלך בתוך זמן קצר.\n\n"
                "💎 *מה תקבל לאחר אישור:*\n"
                "• לינק אישי להפצה\n"
                "• גישה לקהילה\n"
                "• אפשרות למכור נכסים נוספים\n"
                f"• {TON_DISCOUNT_PERCENT}% הנחה בהפצות נוספות"
            ),
            'en': (
                "✅ *Payment Confirmation Received!*\n\n"
                "The confirmation has been sent to our team for verification.\n"
                "You will receive your digital asset shortly.\n\n"
                "💎 *What you get after approval:*\n"
                "• Personal sharing link\n"
                "• Community access\n"
                "• Ability to sell additional assets\n"
                f"• {TON_DISCOUNT_PERCENT}% discount on additional distributions"
            ),
            'ru': (
                "✅ *Подтверждение оплаты получено!*\n\n"
                "Подтверждение отправлено нашей команде для проверки.\n"
                "Вы получите ваш цифровой актив в ближайшее время.\n\n"
                "💎 *Что вы получите после одобрения:*\n"
                "• Персональная ссылка для распространения\n"
                "• Доступ к сообществу\n"
                "• Возможность продавать дополнительные активы\n"
                f"• {TON_DISCOUNT_PERCENT}% скидка на дополнительные распространения"
            ),
            'ar': (
                "✅ *تم استلام تأكيد الدفع!*\n\n"
                "تم إرسال التأكيد إلى فريقنا للتحقق.\n"
                "ستستلم أصولك الرقمية قريبًا.\n\n"
                "💎 *ما الذي تحصل عليه after الموافقة:*\n"
                "• رابط مشاركة شخصي\n"
                "• الوصول إلى المجتمع\n"
                "• القدرة على بيع أصول إضافية\n"
                f"• {TON_DISCOUNT_PERCENT}% خصم على التوزيعات الإضافية"
            )
        }

        await message.reply_text(
            confirmation_text.get(user_lang, confirmation_text['he']),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error("Error in handle_payment_photo: %s", e)

async def do_approve(target_id: int, context: ContextTypes.DEFAULT_TYPE, source_message) -> None:
    try:
        personal_link = build_personal_share_link(target_id)
        
        # הודעת אישור למשתמש
        user_lang = trans_manager.get_user_language(target_id)
        approval_text = {
            'he': (
                "🎉 *התשלום אושר! ברוך הבא לבעלי הנכסים!*\n\n"
                
                "💎 *הנכס הדיגיטלי שלך מוכן:*\n"
                f"🔗 *לינק אישי:* `{personal_link}`\n\n"
                
                "🚀 *מה עכשיו?*\n"
                "1. שתף את הלינק עם אחרים\n"
                "2. كل רכישה דרך הלינק שלך מתועדת\n"
                "3. תוכל למכור נכסים נוספים\n"
                "4. צבור הכנסה מהפצות\n"
                f"5. קבל {TON_DISCOUNT_PERCENT}% הנחה בהפצות נוספות\n\n"
                
                "👥 *גישה לקהילה:*\n"
                f"{COMMUNITY_GROUP_LINK}\n\n"
                
                "💼 *ניהול הנכס:*\n"
                "השתמש בכפתור '👤 האזור האישי שלי'\n"
                "כדי להגדיר פרטי בנק וקבוצות"
            ),
            'en': (
                "🎉 *Payment Approved! Welcome Asset Owner!*\n\n"
                
                "💎 *Your digital asset is ready:*\n"
                f"🔗 *Personal link:* `{personal_link}`\n\n"
                
                "🚀 *What now?*\n"
                "1. Share the link with others\n"
                "2. Every purchase through your link is recorded\n"
                "3. You can sell additional assets\n"
                "4. Accumulate income from sharing\n"
                f"5. Get {TON_DISCOUNT_PERCENT}% discount on additional distributions\n\n"
                
                "👥 *Community access:*\n"
                f"{COMMUNITY_GROUP_LINK}\n\n"
                
                "💼 *Asset management:*\n"
                "Use the '👤 My Personal Area' button\n"
                "to set bank details and groups"
            ),
            'ru': (
                "🎉 *Оплата подтверждена! Добро пожаловать, владелец актива!*\n\n"
                
                "💎 *Ваш цифровой актив готов:*\n"
                f"🔗 *Персональная ссылка:* `{personal_link}`\n\n"
                
                "🚀 *Что теперь?*\n"
                "1. Поделитесь ссылкой с другими\n"
                "2. Каждая покупка по вашей ссылке записывается\n"
                "3. Вы можете продавать дополнительные активы\n"
                "4. Накопите доход от распространения\n"
                f"5. Получите {TON_DISCOUNT_PERCENT}% скидку на дополнительные распространения\n\n"
                
                "👥 *Доступ к сообществу:*\n"
                f"{COMMUNITY_GROUP_LINK}\n\n"
                
                "💼 *Управление активом:*\n"
                "Используйте кнопку '👤 Моя личная зона'\n"
                "чтобы установить банковские реквизиты и группы"
            ),
            'ar': (
                "🎉 *تمت الموافقة على الدفع! مرحبًا بك مالک الأصول!*\n\n"
                
                "💎 *أصولك الرقمية جاهزة:*\n"
                f"🔗 *رابط شخصي:* `{personal_link}`\n\n"
                
                "🚀 *ماذا now؟*\n"
                "1. شارك الرابط مع الآخرين\n"
                "2. يتم تسجيل كل عملية شراء through رابطك\n"
                "3. يمكنك بيع أصول إضافية\n"
                "4. تراكم الدخل من المشاركة\n"
                f"5. احصل على {TON_DISCOUNT_PERCENT}% خصم على التوزيعات الإضافية\n\n"
                
                "👥 *الوصول إلى المجتمع:*\n"
                f"{COMMUNITY_GROUP_LINK}\n\n"
                
                "💼 *إدارة الأصول:*\n"
                "استخدم زر '👤 منطقتي الشخصية'\n"
                "لتعيين تفاصيل البنك والمجموعات"
            )
        }

        await context.bot.send_message(
            chat_id=target_id, 
            text=approval_text.get(user_lang, approval_text['he']), 
            parse_mode="Markdown",
            reply_markup=get_stable_keyboard(user_lang)
        )
        
        # אישור העברת תשלום לקבוצת הלוגים
        approval_notice = (
            f"✅ *אישור העברת תשלום* ✅\n\n"
            f"👤 user_id: `{target_id}`\n"
            f"🕐 זמן אישור: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"🔗 לינק אישי: `{personal_link}`\n\n"
            f"*התשלום אושר והמשתמש קיבל את הנכס הדיגיטלי שלו*"
        )
        
        await context.bot.send_message(
            chat_id=PAYMENTS_LOG_CHAT_ID,
            text=approval_notice,
            parse_mode="Markdown"
        )
        
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
    try:
        user_lang = trans_manager.get_user_language(target_id)
        rejection_text = {
            'he': (
                "❌ *אישור התשלום נדחה*\n\n"
                f"*סיבה:* {reason}\n\n"
                "אם לדעתך מדובר בטעות, פנה לתמיכה."
            ),
            'en': (
                "❌ *Payment Approval Rejected*\n\n"
                f"*Reason:* {reason}\n\n"
                "If you think this is a mistake, contact support."
            ),
            'ru': (
                "❌ *Подтверждение оплаты отклонено*\n\n"
                f"*Причина:* {reason}\n\n"
                "Если вы считаете, что это ошибка, обратитесь в поддержку."
            ),
            'ar': (
                "❌ *تم رفض تأكيد الدفع*\n\n"
                f"*السبب:* {reason}\n\n"
                "إذا كنت تعتقد أن هذا خطأ، اتصل بالدعم."
            )
        }
        
        await context.bot.send_message(
            chat_id=target_id, 
            text=rejection_text.get(user_lang, rejection_text['he']), 
            parse_mode="Markdown"
        )
        
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
    try:
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
    except Exception as e:
        logger.error("Error in admin_approve_callback: %s", e)

async def admin_reject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
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
    except Exception as e:
        logger.error("Error in admin_reject_callback: %s", e)

async def admin_reject_reason_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user = update.effective_user
        if user is None or user.id not in ADMIN_IDS:
            return

        pending = get_pending_rejects(context)
        if user.id not in pending:
            return

        target_id = pending.pop(user.id)
        reason = update.message.text.strip()
        await do_reject(target_id, reason, context, update.effective_message)
    except Exception as e:
        logger.error("Error in admin_reject_reason_handler: %s", e)

# =========================
# Back handlers
# =========================

async def back_main_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        query = update.callback_query
        await query.answer()
        fake_update = Update(update_id=update.update_id, message=query.message)
        await start(fake_update, context)
    except Exception as e:
        logger.error("Error in back_main_callback: %s", e)

async def support_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        query = update.callback_query
        await query.answer()

        user = update.effective_user
        lang = trans_manager.get_user_language(user.id) if user else 'he'

        text = {
            'he': (
                "🆘 *תמיכה ועזרה*\n\n"
                "בכל שלב אפשר לקבל עזרה באחד הערוצים הבאים:\n\n"
                f"• קבוצת תמיכה: {SUPPORT_GROUP_LINK}\n"
                f"• פניה ישירה למתכנת המערכת: `tg://user?id={DEVELOPER_USER_ID}`\n"
                f"• תמיכה בתשלומי TON: לחץ על הכפתור למטה\n\n"
                "או חזור לתפריט הראשי:"
            ),
            'en': (
                "🆘 *Support and Help*\n\n"
                "At any stage you can get help in one of the following channels:\n\n"
                f"• Support group: {SUPPORT_GROUP_LINK}\n"
                f"• Direct contact with system developer: `tg://user?id={DEVELOPER_USER_ID}`\n"
                f"• TON payment support: Click the button below\n\n"
                "Or return to main menu:"
            ),
            'ru': (
                "🆘 *Поддержка и помощь*\n\n"
                "На любом этапе вы можете получить помощь в одном из следующих каналов:\n\n"
                f"• Группа поддержки: {SUPPORT_GROUP_LINK}\n"
                f"• Прямой контакт с разработчиком системы: `tg://user?id={DEVELOPER_USER_ID}`\n"
                f"• Поддержка оплаты TON: Нажмите кнопку ниже\n\n"
                "Или вернуться в главное меню:"
            ),
            'ar': (
                "🆘 *الدعم والمساعدة*\n\n"
                "في أي مرحلة يمكنك الحصول على المساعدة في one of القنوات التالية:\n\n"
                f"• مجموعة الدعم: {SUPPORT_GROUP_LINK}\n"
                f"• الاتصال المباشر مع مطور النظام: `tg://user?id={DEVELOPER_USER_ID}`\n"
                f"• دعم الدفع بـ TON: انقر على الزر أدناه\n\n"
                "أو العودة إلى القائمة الرئيسية:"
            )
        }

        await query.edit_message_text(
            text.get(lang, text['he']),
            parse_mode="Markdown",
            reply_markup=support_keyboard(lang),
        )
    except Exception as e:
        logger.error("Error in support_callback: %s", e)

async def share_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        query = update.callback_query
        await query.answer()

        user = update.effective_user
        if not user:
            return

        lang = trans_manager.get_user_language(user.id)

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
            text = {
                'he': (
                    "🔗 *שתף את שער הקהילה*\n\n"
                    "הלינק האישי שלך להפצה:\n"
                    f"`{personal_link}`\n\n"
                    "מומלץ לשתף בסטורי / סטטוס / קבוצות, ולהוסיף כמה מילים אישיות משלך.\n"
                    "כל מי שייכנס דרך הלינק וילחץ על Start בבוט – יעבור דרך שער הקהילה שלך.\n\n"
                    f"💎 *טיפ:* הזכירו על {TON_DISCOUNT_PERCENT}% הנחה בתשלומי TON!"
                ),
                'en': (
                    "🔗 *Share the Community Gateway*\n\n"
                    "Your personal sharing link:\n"
                    f"`{personal_link}`\n\n"
                    "Recommended to share in stories/status/groups, and add some personal words of your own.\n"
                    "Anyone who enters through the link and clicks Start in the bot - will go through your community gateway.\n\n"
                    f"💎 *Tip:* Mention the {TON_DISCOUNT_PERCENT}% discount on TON payments!"
                ),
                'ru': (
                    "🔗 *Поделитесь входом в сообщество*\n\n"
                    "Ваша персональная ссылка для распространения:\n"
                    f"`{personal_link}`\n\n"
                    "Рекомендуется делиться в сторис/статусе/группах и добавлять несколько личных слов от себя.\n"
                    "Любой, кто войдет по ссылке и нажмет Start в боте - пройдет через ваш вход в сообщество.\n\n"
                    f"💎 *Совет:* Упомяните {TON_DISCOUNT_PERCENT}% скидку на оплату TON!"
                ),
                'ar': (
                    "🔗 *شارك بوابة المجتمع*\n\n"
                    "رابط المشاركة الشخصي الخاص بك:\n"
                    f"`{personal_link}`\n\n"
                    "يوصى بالمشاركة في القصص/الحالة/المجموعات، وإضافة بعض الكلمات الشخصية من yourself.\n"
                    "أي شخص يدخل through الرابط وينقر على Start في البوت - سيمر through بوابة المجتمع الخاصة بك.\n\n"
                    f"💎 *نصيحة:* اذكر خصم {TON_DISCOUNT_PERCENT}% على مدفوعات TON!"
                )
            }
        else:
            # אם אין לו נכס - הלינק הכללי + הסבר על 39 שיתופים
            text = {
                'he': (
                    "🔗 *שתף את שער הקהילה*\n\n"
                    "כדי להזמין חברים לקהילה, אפשר לשלוח להם את הקישור הבא:\n"
                    f"{LANDING_URL}\n\n"
                    
                    "💝 *אפשרות צדקה - 39 שיתופים*\n"
                    "לאחר 39 שיתופים איכותיים של הקישור, תוכל לקבל גישה מלאה לקהילה ללא תשלום!\n"
                    "זו הזדמנות גם למי שידו אינה משגת להצטרף ולצמוח איתנו.\n\n"
                    
                    f"💎 *הנחת TON:* {TON_DISCOUNT_PERCENT}% הנחה למשלמים ב-TON\n\n"
                    
                    "📢 *איך לשתף:*\n"
                    "מומלץ לשתף בסטורי / סטטוס / קבוצות\n"
                    "ולהוסיף כמה מילים אישיות משלך.\n\n"
                    
                    "*כל מי שייכנס דרך הלינק וילחץ על Start בבוט - יעבור דרך שער הקהילה.*"
                ),
                'en': (
                    "🔗 *Share the Community Gateway*\n\n"
                    "To invite friends to the community, you can send them the following link:\n"
                    f"{LANDING_URL}\n\n"
                    
                    "💝 *Charity option - 39 shares*\n"
                    "After 39 quality shares of the link, you can get full access to the community without payment!\n"
                    "This is an opportunity for those who cannot afford to join and grow with us.\n\n"
                    
                    f"💎 *TON Discount:* {TON_DISCOUNT_PERCENT}% discount for TON payers\n\n"
                    
                    "📢 *How to share:*\n"
                    "Recommended to share in stories/status/groups\n"
                    "and add some personal words of your own.\n\n"
                    
                    "*Anyone who enters through the link and clicks Start in the bot - will go through the community gateway.*"
                ),
                'ru': (
                    "🔗 *Поделитесь входом в сообщество*\n\n"
                    "Чтобы пригласить друзей в сообщество, вы можете отправить им следующую ссылку:\n"
                    f"{LANDING_URL}\n\n"
                    
                    "💝 *Опция благотворительности - 39 репостов*\n"
                    "После 39 качественных репостов ссылки вы можете получить полный доступ к сообществу без оплаты!\n"
                    "Это возможность для тех, кто не может позволить себе присоединиться и расти с нами.\n\n"
                    
                    f"💎 *Скидка TON:* {TON_DISCOUNT_PERCENT}% скидка для плательщиков TON\n\n"
                    
                    "📢 *Как делиться:*\n"
                    "Рекомендуется делиться в сторис/статусе/группах\n"
                    "и добавлять несколько личных слов от себя.\n\n"
                    
                    "*Любой, кто войдет по ссылке и нажмет Start в боте - пройдет через вход в сообщество.*"
                ),
                'ar': (
                    "🔗 *شارك بوابة المجتمع*\n\n"
                    "للدعوة أصدقاء إلى المجتمع، يمكنك إرسال الرابط التالي لهم:\n"
                    f"{LANDING_URL}\n\n"
                    
                    "💝 *خيار charity - 39 مشاركة*\n"
                    "بعد 39 مشاركة جودة للرابط، يمكنك الحصول على وصول كامل إلى المجتمع without دفع!\n"
                    "هذه فرصة لأولئك الذين لا يستطيعون تحمل costs للانضمام والنمو معنا.\n\n"
                    
                    f"💎 *خصم TON:* {TON_DISCOUNT_PERCENT}% خصم لدفعات TON\n\n"
                    
                    "📢 *كيفية المشاركة:*\n"
                    "يوصى بالمشاركة في القصص/الحالة/المجموعات\n"
                    "وإضافة بعض الكلمات الشخصية من yourself.\n\n"
                    
                    "*أي شخص يدخل through الرابط وينقر على Start في البوت - سيمر through بوابة المجتمع.*"
                )
            }

        await query.message.reply_text(
            text.get(lang, text['he']),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error("Error in share_callback: %s", e)

async def vision_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        query = update.callback_query
        await query.answer()

        user = update.effective_user
        lang = trans_manager.get_user_language(user.id) if user else 'he'

        text = {
            'he': (
                "🌟 *Human Capital Protocol - SLH*\n\n"
                
                "💫 *מה זה SLH במשפט אחד?*\n"
                "SLH הוא פרוטוקול הון אנושי שמחבר בין משפחות, קהילות ומומחים לרשת כלכלית אחת "
                "– עם בוטים, חנויות, טוקן SLH, אקדמיה, משחק, ו־Exchange – כך שכל אדם יכול להפוך "
                "לעסק, למומחה ולצומת כלכלי, מתוך הטלפון שלו.\n\n"
                
                f"💎 *חדש!* תמיכה מלאה ב-TON עם {TON_DISCOUNT_PERCENT}% הנחה\n\n"
                
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
            ),
            'en': (
                "🌟 *Human Capital Protocol - SLH*\n\n"
                
                "💫 *What is SLH in one sentence?*\n"
                "SLH is a human capital protocol that connects families, communities and experts into one economic network "
                "- with bots, shops, SLH token, academy, gaming, and Exchange - so that every person can become "
                "a business, an expert and an economic node, from their phone.\n\n"
                
                f"💎 *New!* Full TON support with {TON_DISCOUNT_PERCENT}% discount\n\n"
                
                "🎯 *The long-term vision:*\n"
                "• Turn every person and family into an independent economic unit\n"
                "• Build a decentralized global trade network\n"
                "• Create Meta-Economy: technological overlay layer\n"
                "• Make SLH a global standard for measuring expertise\n\n"
                
                "🏗 *The complete ecosystem:*\n"
                "• 🤖 Bots Layer - Telegram bots\n"
                "• 🛒 Commerce Layer - shops and marketplace\n"
                "• ⛓️ Blockchain Layer - BSC + TON\n"
                "• 🎓 Expertise Layer - Pi Index\n"
                "• 🎮 Academy Layer - learning and gaming\n"
                "• 💱 Exchange Layer - trading and liquidity\n\n"
                
                "🚀 *Human Capital Protocol*\n"
                "SLH is not another 'app' but a Meta-Protocol: like HTTP/Email for family and community economy. "
                "People are the algorithm, the system only measures and rewards.\n\n"
                "*Knowledge = Capital | Families = Assets | Communities = Networks | People = Protocol*"
            ),
            'ru': (
                "🌟 *Протокол человеческого капитала - SLH*\n\n"
                
                "💫 *Что такое SLH в одном предложении?*\n"
                "SLH - это протокол человеческого капитала, который соединяет семьи, сообщества и экспертов в одну экономическую сеть "
                "- с ботами, магазинами, токеном SLH, академией, играми и Exchange - так что каждый человек может стать "
                "бизнесом, экспертом и экономическим узлом, со своего телефона.\n\n"
                
                f"💎 *Новое!* Полная поддержка TON с {TON_DISCOUNT_PERCENT}% скидкой\n\n"
                
                "🎯 *Долгосрочное видение:*\n"
                "• Превратить каждого человека и семью в независимую экономическую единицу\n"
                "• Построить децентрализованную глобальную торговую сеть\n"
                "• Создать Meta-Economy: технологический overlay-слой\n"
                "• Сделать SLH глобальным стандартом для измерения экспертизы\n\n"
                
                "🏗 *Полная экосистема:*\n"
                "• 🤖 Bots Layer - Telegram боты\n"
                "• 🛒 Commerce Layer - магазины и маркетплейс\n"
                "• ⛓️ Blockchain Layer - BSC + TON\n"
                "• 🎓 Expertise Layer - Pi Index\n"
                "• 🎮 Academy Layer - обучение и игры\n"
                "• 💱 Exchange Layer - торговля и ликвидность\n\n"
                
                "🚀 *Протокол человеческого капитала*\n"
                "SLH - это не просто 'приложение', а Meta-Protocol: как HTTP/Email для семейной и общественной экономики. "
                "Люди - это алгоритм, система только измеряет и вознаграждает.\n\n"
                "*Знание = Капитал | Семьи = Активы | Сообщества = Сети | Люди = Протокол*"
            ),
            'ar': (
                "🌟 *بروتوكول رأس المال البشري - SLH*\n\n"
                
                "💫 *ما هو SLH في جملة واحدة؟*\n"
                "SLH هو بروتوكول رأس المال البشري الذي يربط العائلات والمجتمعات والخبراء في شبكة اقتصادية واحدة "
                "- مع البوتات والمتاجر ورمز SLH والأكاديمية والألعاب والتبادل - so that كل شخص can يصبح "
                "عمل وخبير وعقدة اقتصادية، من هاتفه.\n\n"
                
                f"💎 *جديد!* دعم كامل لـ TON مع {TON_DISCOUNT_PERCENT}% خصم\n\n"
                
                "🎯 *الرؤية طويلة المدى:*\n"
                "• تحويل كل شخص وعائلة إلى وحدة اقتصادية مستقلة\n"
                "• بناء شبكة تجارية عالمية لامركزية\n"
                "• إنشاء Meta-Economy: طبقة تقنية overlay\n"
                "• جعل SLH معيارًا عالميًا لقياس الخبرة\n\n"
                
                "🏗 *النظام البيئي الكامل:*\n"
                "• 🤖 Bots Layer - بوتات Telegram\n"
                "• 🛒 Commerce Layer - المتاجر والسوق\n"
                "• ⛓️ Blockchain Layer - BSC + TON\n"
                "• 🎓 Expertise Layer - Pi Index\n"
                "• 🎮 Academy Layer - التعلم والألعاب\n"
                "• 💱 Exchange Layer - التداول والسيولة\n\n"
                
                "🚀 *بروتوكول رأس المال البشري*\n"
                "SLH ليس مجرد 'تطبيق' but بروتوكول Meta: مثل HTTP/Email لاقتصاد الأسرة والمجتمع. "
                "الناس هم الخوارزمية، النظام only يقيس and يكافئ.\n\n"
                "*المعرفة = رأس المال | العائلات = الأصول | المجتمعات = الشبكات | الناس = البروتوكول*"
            )
        }

        await query.edit_message_text(
            text.get(lang, text['he']),
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(lang),
        )
    except Exception as e:
        logger.error("Error in vision_callback: %s", e)

# =========================
# TON handlers
# =========================

async def ton_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        query = update.callback_query
        await query.answer()

        user = update.effective_user
        lang = trans_manager.get_user_language(user.id) if user else 'he'

        text = {
            'he': (
                f"💎 *מידע על TON והנחות*\n\n"
                
                f"🎊 *הנחה מיוחדת:* {TON_DISCOUNT_PERCENT}% הנחה\n"
                f"💰 *מחיר רגיל:* 39₪\n"
                f"💰 *מחיר TON:* {TON_DISCOUNTED_PRICE}₪\n\n"
                
                f"🏦 *ארנק TON:*\n"
                f"`{TON_WALLET}`\n\n"
                
                f"📋 *איך משלמים ב-TON?*\n"
                f"1. פתחו את ארנק TON שלכם\n"
                f"2. שלחו {TON_DISCOUNTED_PRICE}₪ לארנק למעלה\n"
                f"3. שמרו צילום מסך\n"
                f"4. שלחו את הצילום לבוט\n\n"
                
                f"⚡ *יתרונות TON:*\n"
                f"• הנחה {TON_DISCOUNT_PERCENT}%\n"
                f"• העברה מיידית\n"
                f"• עמלות נמוכות\n"
                f"• ביטחון גבוה\n"
                f"• טכנולוגיה מתקדמת\n\n"
                
                f"🚀 *הצטרפו למהפכת TON!*"
            ),
            'en': (
                f"💎 *TON Information & Discounts*\n\n"
                
                f"🎊 *Special discount:* {TON_DISCOUNT_PERCENT}% discount\n"
                f"💰 *Regular price:* 39₪\n"
                f"💰 *TON price:* {TON_DISCOUNTED_PRICE}₪\n\n"
                
                f"🏦 *TON Wallet:*\n"
                f"`{TON_WALLET}`\n\n"
                
                f"📋 *How to pay with TON?*\n"
                f"1. Open your TON wallet\n"
                f"2. Send {TON_DISCOUNTED_PRICE}₪ to the wallet above\n"
                f"3. Save a screenshot\n"
                f"4. Send the screenshot to the bot\n\n"
                
                f"⚡ *TON Advantages:*\n"
                f"• {TON_DISCOUNT_PERCENT}% discount\n"
                f"• Instant transfer\n"
                f"• Low fees\n"
                f"• High security\n"
                f"• Advanced technology\n\n"
                
                f"🚀 *Join the TON revolution!*"
            ),
            'ru': (
                f"💎 *Информация о TON и скидках*\n\n"
                
                f"🎊 *Специальная скидка:* {TON_DISCOUNT_PERCENT}% скидка\n"
                f"💰 *Обычная цена:* 39₪\n"
                f"💰 *Цена TON:* {TON_DISCOUNTED_PRICE}₪\n\n"
                
                f"🏦 *TON кошелек:*\n"
                f"`{TON_WALLET}`\n\n"
                
                f"📋 *Как оплатить через TON?*\n"
                f"1. Откройте ваш TON кошелек\n"
                f"2. Отправьте {TON_DISCOUNTED_PRICE}₪ на кошелек выше\n"
                f"3. Сохраните скриншот\n"
                f"4. Отправьте скриншот боту\n\n"
                
                f"⚡ *Преимущества TON:*\n"
                f"• {TON_DISCOUNT_PERCENT}% скидка\n"
                f"• Мгновенный перевод\n"
                f"• Низкие комиссии\n"
                f"• Высокая безопасность\n"
                f"• Передовая технология\n\n"
                
                f"🚀 *Присоединяйтесь к революции TON!*"
            ),
            'ar': (
                f"💎 *معلومات TON والخصومات*\n\n"
                
                f"🎊 *خصم خاص:* {TON_DISCOUNT_PERCENT}% خصم\n"
                f"💰 *السعر العادي:* 39₪\n"
                f"💰 *سعر TON:* {TON_DISCOUNTED_PRICE}₪\n\n"
                
                f"🏦 *محفظة TON:*\n"
                f"`{TON_WALLET}`\n\n"
                
                f"📋 *كيف تدفع بـ TON؟*\n"
                f"1. افتح محفظة TON الخاصة بك\n"
                f"2. أرسل {TON_DISCOUNTED_PRICE}₪ إلى المحفظة أعلاه\n"
                f"3. احفظ لقطة شاشة\n"
                f"4. أرسل لقطة الشاشة إلى البوت\n\n"
                
                f"⚡ *مزايا TON:*\n"
                f"• {TON_DISCOUNT_PERCENT}% خصم\n"
                f"• تحويل فوري\n"
                f"• رسوم منخفضة\n"
                f"• أمان عالي\n"
                f"• تقنية متقدمة\n\n"
                
                f"🚀 *انضم إلى ثورة TON!*"
            )
        }

        await query.edit_message_text(
            text.get(lang, text['he']),
            parse_mode="Markdown",
            reply_markup=ton_payment_keyboard(lang),
        )
    except Exception as e:
        logger.error("Error in ton_info_callback: %s", e)

async def ton_support_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        query = update.callback_query
        await query.answer()

        user = update.effective_user
        lang = trans_manager.get_user_language(user.id) if user else 'he'

        text = {
            'he': (
                "💎 *תמיכה בתשלומי TON*\n\n"
                
                f"🏦 *ארנק TON:*\n"
                f"`{TON_WALLET}`\n\n"
                
                "📚 *מדריכים:*\n"
                "• [מדריך TON למתחילים](https://ton.org/learn)\n"
                "• [איך להשתמש בארנק TON?](https://ton.org/wallets)\n"
                "• [שאלות נפוצות](https://ton.org/faq)\n\n"
                
                "🆘 *בעיות בתשלום?*\n"
                "אם נתקלת בבעיה בתשלום TON:\n"
                "1. ודא שהעברת את הסכום הנכון\n"
                "2. שלח צילום מסך של ההעברה\n"
                "3. פנה לתמיכה הטכנית\n\n"
                f"📞 *תמיכה:* {SUPPORT_GROUP_LINK}"
            ),
            'en': (
                "💎 *TON Payment Support*\n\n"
                
                f"🏦 *TON Wallet:*\n"
                f"`{TON_WALLET}`\n\n"
                
                "📚 *Guides:*\n"
                "• [TON Guide for Beginners](https://ton.org/learn)\n"
                "• [How to Use TON Wallet?](https://ton.org/wallets)\n"
                "• [Frequently Asked Questions](https://ton.org/faq)\n\n"
                
                "🆘 *Payment Issues?*\n"
                "If you encounter TON payment issues:\n"
                "1. Make sure you sent the correct amount\n"
                "2. Send a screenshot of the transfer\n"
                "3. Contact technical support\n\n"
                f"📞 *Support:* {SUPPORT_GROUP_LINK}"
            ),
            'ru': (
                "💎 *Поддержка оплаты TON*\n\n"
                
                f"🏦 *TON кошелек:*\n"
                f"`{TON_WALLET}`\n\n"
                
                "📚 *Руководства:*\n"
                "• [Руководство TON для начинающих](https://ton.org/learn)\n"
                "• [Как использовать кошелек TON?](https://ton.org/wallets)\n"
                "• [Часто задаваемые вопросы](https://ton.org/faq)\n\n"
                
                "🆘 *Проблемы с оплатой?*\n"
                "Если у вас возникли проблемы с оплатой TON:\n"
                "1. Убедитесь, что вы отправили правильную сумму\n"
                "2. Отправьте скриншот перевода\n"
                "3. Обратитесь в техническую поддержку\n\n"
                f"📞 *Поддержка:* {SUPPORT_GROUP_LINK}"
            ),
            'ar': (
                "💎 *دعم الدفع بـ TON*\n\n"
                
                f"🏦 *محفظة TON:*\n"
                f"`{TON_WALLET}`\n\n"
                
                "📚 *أدلة:*\n"
                "• [دليل TON للمبتدئين](https://ton.org/learn)\n"
                "• [كيفية استخدام محفظة TON؟](https://ton.org/wallets)\n"
                "• [الأسئلة الشائعة](https://ton.org/faq)\n\n"
                
                "🆘 *مشاكل في الدفع؟*\n"
                "إذا واجهت مشاكل في الدفع بـ TON:\n"
                "1. تأكد من إرسال المبلغ الصحيح\n"
                "2. أرسل لقطة شاشة للتحويل\n"
                "3. اتصل بالدعم الفني\n\n"
                f"📞 *الدعم:* {SUPPORT_GROUP_LINK}"
            )
        }

        await query.edit_message_text(
            text.get(lang, text['he']),
            parse_mode="Markdown",
            disable_web_page_preview=True,
            reply_markup=support_keyboard(lang),
        )
    except Exception as e:
        logger.error("Error in ton_support_callback: %s", e)

# =========================
# Additional command handlers
# =========================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """עזרה בסיסית"""
    try:
        message = update.message or update.effective_message
        if not message:
            return

        user = update.effective_user
        lang = trans_manager.get_user_language(user.id) if user else 'he'

        text = {
            'he': (
                "/start – התחלה מחדש ותפריט ראשי\n"
                "/help – עזרה\n\n"
                "אחרי ביצוע תשלום – שלח צילום מסך של האישור לבוט.\n\n"
                f"💎 *הנחת TON:* {TON_DISCOUNT_PERCENT}% הנחה\n\n"
                "לשיתוף שער הקהילה: כפתור '🔗 שתף את שער הקהילה' בתפריט הראשי.\n\n"
                "למארגנים / אדמינים:\n"
                "/admin – תפריט אדמין\n"
                "/leaderboard – לוח מפנים (Top 10)\n"
                "/payments_stats – סטטיסטיקות תשלומים\n"
                "/reward_slh <user_id> <points> <reason> – יצירת Reward ל-SLH\n"
                "/approve <user_id> – אישור תשלום\n"
                "/reject <user_id> <סיבה> – דחיית תשלום\n"
                "או שימוש בכפתורי האישור/דחייה ליד כל תשלום בלוגים."
            ),
            'en': (
                "/start – Restart and main menu\n"
                "/help – Help\n\n"
                "After making payment – send screenshot of confirmation to bot.\n\n"
                f"💎 *TON Discount:* {TON_DISCOUNT_PERCENT}% discount\n\n"
                "For sharing community gateway: '🔗 Share Community Gateway' button in main menu.\n\n"
                "For organizers/admins:\n"
                "/admin – Admin menu\n"
                "/leaderboard – Referrers board (Top 10)\n"
                "/payments_stats – Payment statistics\n"
                "/reward_slh <user_id> <points> <reason> – Create Reward for SLH\n"
                "/approve <user_id> – Approve payment\n"
                "/reject <user_id> <reason> – Reject payment\n"
                "Or use approval/rejection buttons next to each payment in logs."
            ),
            'ru': (
                "/start – Перезапуск и главное меню\n"
                "/help – Помощь\n\n"
                "После совершения оплаты – отправьте скриншот подтверждения боту.\n\n"
                f"💎 *Скидка TON:* {TON_DISCOUNT_PERCENT}% скидка\n\n"
                "Для распространения входа в сообщество: кнопка '🔗 Поделиться входом в сообщество' в главном меню.\n\n"
                "Для организаторов/админов:\n"
                "/admin – Меню админа\n"
                "/leaderboard – Доска рефереров (Топ 10)\n"
                "/payments_stats – Статистика платежей\n"
                "/reward_slh <user_id> <points> <reason> – Создать Reward для SLH\n"
                "/approve <user_id> – Одобрить платеж\n"
                "/reject <user_id> <причина> – Отклонить платеж\n"
                "Или используйте кнопки одобрения/отклонения рядом с каждым платежом в логах."
            ),
            'ar': (
                "/start – إعادة البدء والقائمة الرئيسية\n"
                "/help – مساعدة\n\n"
                "بعد إجراء الدفع – أرسل لقطة شاشة للتأكيد إلى البوت.\n\n"
                f"💎 *خصم TON:* {TON_DISCOUNT_PERCENT}% خصم\n\n"
                "لمشاركة بوابة المجتمع: زر '🔗 مشاركة بوابة المجتمع' في القائمة الرئيسية.\n\n"
                "للمنظمين/المسؤولين:\n"
                "/admin – قائمة المسؤول\n"
                "/leaderboard – لوحة المحيلين (أعلى 10)\n"
                "/payments_stats – إحصائيات الدفع\n"
                "/reward_slh <user_id> <points> <reason> – إنشاء مكافأة لـ SLH\n"
                "/approve <user_id> – الموافقة على الدفع\n"
                "/reject <user_id> <السبب> – رفض الدفع\n"
                "أو use أزرار الموافقة/الرفض بجانب each دفعة in السجلات."
            )
        }

        await message.reply_text(text.get(lang, text['he']))
    except Exception as e:
        logger.error("Error in help_command: %s", e)

async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """פקודת בחירת שפה"""
    try:
        message = update.message or update.effective_message
        if not message:
            return

        user = update.effective_user
        lang = trans_manager.get_user_language(user.id) if user else 'he'

        prompt_text = {
            'he': "🌐 *בחר שפה:*",
            'en': "🌐 *Choose language:*",
            'ru': "🌐 *Выберите язык:*", 
            'ar': "🌐 *اختر اللغة:*"
        }

        await message.reply_text(
            prompt_text.get(lang, prompt_text['he']),
            reply_markup=language_keyboard()
        )
    except Exception as e:
        logger.error("Error in language_command: %s", e)

# =========================
# Handler for stable keyboard text messages
# =========================

async def handle_stable_keyboard_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """מטפל בהודעות טקסט מהמקלדת היציבה"""
    try:
        message = update.message
        if not message or not message.text:
            return

        user = update.effective_user
        lang = trans_manager.get_user_language(user.id) if user else 'he'
        
        text = message.text
        
        # מיפוי טקסט הכפתורים לפעולות
        button_actions = {
            trans_manager.get_text("join_community", lang): "join",
            trans_manager.get_text("digital_asset_info", lang): "digital_asset_info", 
            trans_manager.get_text("share_gateway", lang): "share",
            trans_manager.get_text("slh_vision", lang): "vision",
            trans_manager.get_text("my_area", lang): "my_area",
            trans_manager.get_text("support", lang): "support",
        }
        
        # חיפוש הפעולה המתאימה
        action_key = None
        for button_text, action in button_actions.items():
            if text == button_text:
                action_key = action
                break
        
        if action_key:
            # יצירת callback query מדומה
            class FakeQuery:
                def __init__(self, data, message, user):
                    self.data = data
                    self.message = message
                    self.from_user = user
                
                async def answer(self):
                    pass
                
                async def edit_message_text(self, text, parse_mode=None, reply_markup=None):
                    await self.message.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup)

            fake_query = FakeQuery(action_key, message, user)
            
            # מיפוי handlers לפי action
            handlers = {
                "join": join_callback,
                "digital_asset_info": digital_asset_info,
                "share": share_callback, 
                "vision": vision_callback,
                "my_area": my_area_callback,
                "support": support_callback,
            }
            
            if action_key in handlers:
                fake_update = Update(update_id=update.update_id, callback_query=fake_query)
                await handlers[action_key](fake_update, context)
                return
        
        # אם לא נמצאה פעולה - שליחת הודעת ברירת מחדל
        await message.reply_text(
            trans_manager.get_text("main_menu", lang),
            reply_markup=get_stable_keyboard(lang)
        )
        
    except Exception as e:
        logger.error("Error in stable keyboard handler: %s", e)
        try:
            await update.message.reply_text(
                "❌ אירעה שגיאה בעיבוד הבקשה. נסה שוב.",
                reply_markup=get_stable_keyboard('he')
            )
        except:
            pass

# =========================
# רישום handlers
# =========================

# הוסף error handler ראשון
ptb_app.add_error_handler(error_handler)

# שאר ה-handlers
ptb_app.add_handler(CommandHandler("start", start))
ptb_app.add_handler(CommandHandler("help", help_command))
ptb_app.add_handler(CommandHandler("language", language_command))
ptb_app.add_handler(CommandHandler("lang", language_command))

ptb_app.add_handler(CallbackQueryHandler(handle_language_selection, pattern="^lang_"))

ptb_app.add_handler(CallbackQueryHandler(digital_asset_info, pattern="^digital_asset_info$"))
ptb_app.add_handler(CallbackQueryHandler(join_callback, pattern="^join$"))
ptb_app.add_handler(CallbackQueryHandler(support_callback, pattern="^support$"))
ptb_app.add_handler(CallbackQueryHandler(share_callback, pattern="^share$"))
ptb_app.add_handler(CallbackQueryHandler(vision_callback, pattern="^vision$"))
ptb_app.add_handler(CallbackQueryHandler(back_main_callback, pattern="^back_main$"))
ptb_app.add_handler(CallbackQueryHandler(payment_method_callback, pattern="^pay_"))
ptb_app.add_handler(CallbackQueryHandler(my_area_callback, pattern="^my_area$"))
ptb_app.add_handler(CallbackQueryHandler(admin_approve_callback, pattern="^adm_approve:"))
ptb_app.add_handler(CallbackQueryHandler(admin_reject_callback, pattern="^adm_reject:"))
ptb_app.add_handler(CallbackQueryHandler(ton_info_callback, pattern="^ton_info$"))
ptb_app.add_handler(CallbackQueryHandler(ton_support_callback, pattern="^ton_support$"))

# הוספת handler למקלדת יציבה
ptb_app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, handle_stable_keyboard_text))

# כל תמונה בפרטי – נניח כאישור תשלום
ptb_app.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, handle_payment_photo))

# הודעת טקסט מאדמין – אם יש דחייה ממתינה
ptb_app.add_handler(MessageHandler(filters.TEXT & filters.User(list(ADMIN_IDS)), admin_reject_reason_handler))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
