# main.py
import os
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from db import (
    ensure_user,
    get_user,
    mark_paid,
    set_bank_details,
    add_payment,
    add_staking_position,
    get_user_staking,
    all_users,
)

# =========================
# Logging & ENV
# =========================

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("slhnet")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0") or "0")
BUSINESS_GROUP_URL = os.getenv(
    "BUSINESS_GROUP_URL", "https://t.me/+HIzvM8sEgh1kNWY0"
)
PAYBOX_URL = os.getenv(
    "PAYBOX_URL", "https://links.payboxapp.com/1SNfaJ6XcYb"
)
BIT_URL = os.getenv("BIT_URL", "")
PAYPAL_URL = os.getenv("PAYPAL_URL", "https://paypal.me/osifdu")
LANDING_URL = os.getenv("LANDING_URL", "https://slh-nft.com/")
START_IMAGE_PATH = os.getenv("START_IMAGE_PATH", "assets/start_banner.jpg")

SLH_PRICE_NIS = float(os.getenv("SLH_PRICE_NIS", "444"))
SLH_TOKEN_ADDRESS = os.getenv(
    "SLH_TOKEN_ADDRESS", "0xACb0A09414CEA1C879c67bB7A877E4e19480f022"
)
BSC_RPC_URL = os.getenv(
    "BSC_RPC_URL", "https://bsc-dataseed.binance.org/"
)

if not BOT_TOKEN:
    logger.error("BOT_TOKEN is not set! Bot will not work properly.")

# =========================
# FastAPI app
# =========================

app = FastAPI(title="SLHNET Bot + Landing API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# Telegram Application
# =========================

application = Application.builder().token(BOT_TOKEN).build()


# ===== Helper functions =====

def _user_from_update(update: Update) -> Dict[str, Any]:
    u = update.effective_user
    referrer_id: Optional[int] = None
    # אפשר בהמשך להכניס כאן קריאת ref מתוך פרמטר start
    user_obj = ensure_user(
        user_id=u.id,
        username=u.username,
        first_name=u.first_name,
        last_name=u.last_name,
        referrer_id=referrer_id,
    )
    return user_obj


def _personal_ref_link(user_id: int) -> str:
    # לינק הפניה אישי – אפשר לשדרג בהמשך עם start=ref_...
    return f"{LANDING_URL}?ref={user_id}"


# =========================
# Telegram Handlers
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    מסך פתיחה פרסומי חזק עם כל הערכים של 39 ש"ח + כפתורים.
    """
    chat = update.effective_chat
    user = _user_from_update(update)

    keyboard = [
        [
            InlineKeyboardButton("תשלום 39 ₪ וגישה מלאה", url=PAYBOX_URL),
        ],
        [
            InlineKeyboardButton("דף נחיתה / פרטים נוספים", url=LANDING_URL),
        ],
        [
            InlineKeyboardButton("הצטרפות לקבוצת העסקים", url=BUSINESS_GROUP_URL),
        ],
    ]

    if BIT_URL:
        keyboard.append(
            [InlineKeyboardButton("תשלום בביט", url=BIT_URL)]
        )
    if PAYPAL_URL:
        keyboard.append(
            [InlineKeyboardButton("תשלום ב-PayPal", url=PAYPAL_URL)]
        )

    reply_markup = InlineKeyboardMarkup(keyboard)

    text = (
        "שער הכניסה ל-SLHNET\n\n"
        "מכאן הכל מתחיל: קהילה עסקית, טוקן SLH על BSC, חנויות דיגיטליות ושרשרת הפניות "
        "שיכולה להפוך אותך לשותף במודל הצמיחה.\n\n"
        "מה מקבלים אחרי תשלום חד־פעמי של 39 ₪?\n"
        "• קישור אישי לשיתוף והפצה\n"
        "• נכס דיגיטלי ראשון (חנות / פרופיל עסקי)\n"
        "• גישה לקבוצת העסקים הסגורה\n"
        "• בסיס לרשת ריפרל מדורגת שמתחילה ממך\n\n"
        "איך מתקדמים:\n"
        "1. מבצעים תשלום (פייבוקס / ביט / PayPal)\n"
        "2. שולחים לבוט צילום מסך / אישור תשלום\n"
        "3. אחרי אישור אדמין, תקבל את כל הקישורים האישיים שלך, כולל אפשרות להגדיר פרטי בנק לקבלת תשלומים.\n\n"
        "פקודות שימושיות:\n"
        "/whoami – הפרופיל שלך במערכת\n"
        "/links – כל הקישורים שאפשר לשתף + הבוט + האתר\n"
        "/staking – הסבר וסטטוס סטייקינג דמו\n"
        "/investor – מידע למשקיעים\n"
    )

    # ננסה לשלוח תמונה אם קיימת
    try:
        if os.path.exists(START_IMAGE_PATH):
            await chat.send_photo(
                photo=open(START_IMAGE_PATH, "rb"),
                caption=text,
                reply_markup=reply_markup,
            )
        else:
            await chat.send_message(text=text, reply_markup=reply_markup)
    except Exception as e:
        logger.warning(f"Failed to send start image: {e}")
        await chat.send_message(text=text, reply_markup=reply_markup)


async def investor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "מידע למשקיעים: SLHNET בונה אקו-סיסטם חברתי-פיננסי שקוף, "
        "עם מודל הפניות מדורג וצמיחה אורגנית.\n\n"
        "אנחנו מחברים בין חנויות דיגיטליות, טוקן SLH על Binance Smart Chain, "
        "ו-NFTים ייעודיים לקהילה.\n\n"
        "יצירת קשר ישירה עם המייסד:\n"
        "טלפון: 058-420-3384\n"
        "טלגרם: https://t.me/Osif83\n\n"
        "כאן בונים יחד מודל ריפרל שקוף, סטייקינג ופתרונות תשואה על בסיס "
        "אקו-סיסטם אמיתי של עסקים, לא על אוויר."
    )
    await update.effective_chat.send_message(text=text)


async def whoami(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = _user_from_update(update)
    ref_link = _personal_ref_link(user["user_id"])
    status = "✅ משלם מאושר" if user.get("is_paid") else "❗ טרם אושר תשלום"

    text = (
        "פרטי המשתמש שלך:\n"
        f"user_id: {user['user_id']}\n"
        f"username: @{user.get('username') or 'ללא'}\n"
        f"סטטוס: {status}\n\n"
        f"קישור הפניה אישי (לשיתוף):\n{ref_link}\n"
    )

    if user.get("bank_details"):
        text += f"\nפרטי קבלת תשלומים שהגדרת:\n{user['bank_details']}\n"
    else:
        text += (
            "\nעדיין לא הוגדרו פרטי קבלת תשלומים.\n"
            "לאחר אישור התשלום תוכל לשלוח /setbank ולצרף את פרטי הבנק/ביט שלך."
        )

    await update.effective_chat.send_message(text=text)


async def links(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = _user_from_update(update)
    ref_link = _personal_ref_link(user["user_id"])

    keyboard = [
        [InlineKeyboardButton("דף נחיתה SLHNET", url=LANDING_URL)],
        [InlineKeyboardButton("הצטרפות לבוט החברים", url="https://t.me/Buy_My_Shop_bot")],
        [InlineKeyboardButton("קבוצת העסקים", url=BUSINESS_GROUP_URL)],
    ]

    text = (
        "כל הקישורים המרכזיים שלך ב-SLHNET:\n\n"
        f"🔗 קישור הפניה אישי:\n{ref_link}\n\n"
        f"🌐 אתר / דף נחיתה:\n{LANDING_URL}\n\n"
        "שתף את הקישור האישי שלך עם חברים – ברגע שהם נכנסים דרך הקישור הזה, "
        "אנחנו יכולים לשייך אותם אליך ברשת ההפניות.\n"
    )

    await update.effective_chat.send_message(
        text=text, reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def setbank(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = _user_from_update(update)
    args = context.args

    if not user.get("is_paid"):
        await update.effective_chat.send_message(
            "כדי להגדיר פרטי קבלת תשלומים צריך קודם אישור תשלום על ה-39 ₪."
        )
        return

    if not args:
        await update.effective_chat.send_message(
            "שלח את הפקודה כך:\n/setbank פרטי הבנק/ביט/פייבוקס שלך לקבלת תשלומים."
        )
        return

    details = " ".join(args)
    set_bank_details(user["user_id"], details)
    await update.effective_chat.send_message(
        "פרטי קבלת התשלומים שלך נשמרו בהצלחה.\n"
        "תוכל תמיד לעדכן אותם שוב עם /setbank."
    )


async def staking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = _user_from_update(update)
    positions = get_user_staking(user["user_id"])

    if not positions:
        text = (
            "סטייקינג ב-SLHNET (דמו):\n\n"
            "בשלב הזה אנחנו בונים מנגנון סטייקינג שיאפשר לך לנעול טוקני SLH "
            "בתמורה לתשואה והטבות בקהילה.\n\n"
            "כרגע זה מוד דמו: ברגע שתאושר ותירשם, נוכל להוסיף לך סטייקינג נסיוני "
            "ולהציג כאן את התשואות שלך.\n\n"
            "אם תרצה שנדמה עבורך סטייקינג דמו, שלח לי הודעה אישית או "
            "ציין את זה מול האדמין אחרי האישור."
        )
    else:
        total = sum(p["amount"] for p in positions)
        text = (
            "סטייקינג – פרופיל אישי:\n\n"
            f"מספר פוזיציות: {len(positions)}\n"
            f"סך הכל סכום (דמו): {total:.2f} SLH\n\n"
            "זהו מנגנון דמו שנועד להציג למשקיעים ולמשתמשים הראשונים איך יראה "
            "הסטייקינג במערכת.\n"
        )

    await update.effective_chat.send_message(text=text)


async def handle_payment_evidence(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    כל תמונה/קובץ שנשלח בבוט בפרטי – נתייחס אליו כאישור תשלום.
    נשמור ב-DB ונשלח ללוג באדמין (אם קיים ADMIN_CHAT_ID).
    """
    chat = update.effective_chat
    user = _user_from_update(update)
    message = update.effective_message

    file_id = None
    evidence_type = None

    if message.photo:
        photo = message.photo[-1]
        file_id = photo.file_id
        evidence_type = "photo"
    elif message.document:
        doc = message.document
        file_id = doc.file_id
        evidence_type = "document"

    if not file_id:
        return

    method = "unknown"
    add_payment(
        user_id=user["user_id"],
        username=user.get("username"),
        chat_id=chat.id,
        method=method,
        evidence_type=evidence_type,
        file_id=file_id,
    )

    # שליחת לוג לאדמין
    if ADMIN_CHAT_ID:
        text = (
            "📥 התקבל אישור תשלום חדש.\n\n"
            f"user_id = {user['user_id']}\n"
            f"username = @{user.get('username') or 'ללא'}\n"
            f"from chat_id = {chat.id}\n"
            f"סוג קובץ: {evidence_type}\n\n"
            "לאישור (עבור אדמין ראשי):\n"
            f"/approve {user['user_id']}\n"
            f"/reject {user['user_id']} <סיבה>\n"
        )
        try:
            if evidence_type == "photo":
                await context.bot.send_photo(
                    chat_id=ADMIN_CHAT_ID,
                    photo=file_id,
                    caption=text,
                )
            else:
                await context.bot.send_document(
                    chat_id=ADMIN_CHAT_ID,
                    document=file_id,
                    caption=text,
                )
        except Exception as e:
            logger.error(f"Failed to send payment evidence to admin: {e}")

    await chat.send_message(
        "תודה! קיבלנו את אישור התשלום שלך.\n"
        "אדמין יעבור עליו ויאשר בהקדם. לאחר האישור תקבל את כל הקישורים האישיים שלך."
    )


async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.id != ADMIN_CHAT_ID:
        return

    if not context.args:
        await update.effective_chat.send_message("שימוש: /approve <user_id>")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.effective_chat.send_message("user_id חייב להיות מספר.")
        return

    mark_paid(target_id)
    user = get_user(target_id)

    text_admin = f"אושר תשלום למשתמש {target_id}."
    await update.effective_chat.send_message(text_admin)

    # שליחת הודעה למשתמש – אם נצליח
    try:
        ref_link = _personal_ref_link(target_id)
        msg_user = (
            "✅ התשלום שלך אושר!\n\n"
            "קיבלת גישה מלאה ל-SLHNET.\n\n"
            "מה עכשיו?\n"
            "1. שלח /setbank עם פרטי קבלת התשלומים שלך (בנק / ביט / פייבוקס).\n"
            "2. שלח /links כדי לקבל את כל הקישורים לשיתוף.\n"
            "3. התחל להפיץ את הקישור האישי שלך ולהצטרף לפעילות בקהילה.\n\n"
            f"קישור הפניה אישי:\n{ref_link}\n"
        )
        await context.bot.send_message(chat_id=target_id, text=msg_user)
    except Exception as e:
        logger.error(f"Failed to notify user {target_id} after approval: {e}")


async def reject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.id != ADMIN_CHAT_ID:
        return

    if len(context.args) < 2:
        await update.effective_chat.send_message(
            "שימוש: /reject <user_id> <סיבה>"
        )
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.effective_chat.send_message("user_id חייב להיות מספר.")
        return

    reason = " ".join(context.args[1:])
    text_admin = f"נדחה תשלום למשתמש {target_id}. סיבה: {reason}"
    await update.effective_chat.send_message(text_admin)

    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=(
                "❗ התשלום לא אושר.\n"
                f"סיבה: {reason}\n"
                "ניתן לנסות שוב או ליצור קשר לתמיכה."
            ),
        )
    except Exception as e:
        logger.error(f"Failed to notify user {target_id} after reject: {e}")


# =========================
# PTB registration
# =========================

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("investor", investor))
application.add_handler(CommandHandler("whoami", whoami))
application.add_handler(CommandHandler("links", links))
application.add_handler(CommandHandler("setbank", setbank))
application.add_handler(CommandHandler("staking", staking))
application.add_handler(CommandHandler("approve", approve))
application.add_handler(CommandHandler("reject", reject))

# כל תמונה/דוק בפרטי = אישור תשלום אפשרי
application.add_handler(
    MessageHandler(
        filters.ChatType.PRIVATE & (filters.PHOTO | filters.Document.ALL),
        handle_payment_evidence,
    )
)


# =========================
# FastAPI <-> Telegram Webhook
# =========================

@app.post("/webhook")
async def telegram_webhook(request: Request):
    if not BOT_TOKEN:
        raise HTTPException(status_code=500, detail="BOT_TOKEN not configured")

    data = await request.json()
    update = Update.de_json(data, application.bot)

    await application.process_update(update)
    return JSONResponse({"ok": True})


# =========================
# Public API for website
# =========================

@app.get("/health")
async def health():
    return {"status": "ok", "ts": datetime.utcnow().isoformat() + "Z"}


@app.get("/config/public")
async def config_public():
    return {
        "project": "SLHNET",
        "network": "BSC Mainnet",
        "chain_id": 56,
        "rpc_url": BSC_RPC_URL,
        "token_address": SLH_TOKEN_ADDRESS,
        "token_symbol": "SLH",
        "token_decimals": 15,
        "slh_price_nis": SLH_PRICE_NIS,
        "urls": {
            "bot": "https://t.me/Buy_My_Shop_bot",
            "business_group": BUSINESS_GROUP_URL,
            "paybox": PAYBOX_URL,
            "bit": BIT_URL,
            "paypal": PAYPAL_URL,
        },
    }


@app.get("/api/token/price")
async def token_price():
    return {
        "symbol": "SLH",
        "price_nis": SLH_PRICE_NIS,
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }


@app.get("/api/token/sales")
async def token_sales(limit: int = 50):
    # דמו: מחזיר רשימה ריקה – אפשר להרחיב מאוחר יותר
    return []


@app.get("/api/posts")
async def posts(limit: int = 20):
    # דמו: פוסטים תיאורטיים – אפשר לשלוף בהמשך מה-DB
    base_posts = [
        {
            "id": 1,
            "title": "ברוכים הבאים ל-SLHNET",
            "body": "הרשת העסקית החדשה שמחברת בין חנויות דיגיטליות, טוקן SLH וקהילת יזמים.",
            "created_at": "2025-11-16T00:00:00Z",
        },
        {
            "id": 2,
            "title": "איך מרוויחים מהפניות?",
            "body": "שתפו את הקישור האישי שלכם, כל הצטרפות עובדת לטובתכם ולרשת שלכם.",
            "created_at": "2025-11-16T01:00:00Z",
        },
    ]
    return base_posts[:limit]


@app.get("/api/referral/stats")
async def referral_stats():
    users = all_users()
    total_users = len(users)
    total_with_referrer = sum(1 for u in users if u.get("referrer_id"))
    roots = [u["user_id"] for u in users if not u.get("referrer_id")]

    # מיפוי גס של גודל רשת פר משתמש – דמו (ניתן לשפר)
    network_sizes: Dict[str, int] = {}
    for u in users:
        uid = u["user_id"]
        network_sizes[str(uid)] = sum(
            1 for x in users if x.get("referrer_id") == uid
        )

    return {
        "total_users": total_users,
        "total_with_referrer": total_with_referrer,
        "total_roots": len(roots),
        "roots": roots,
        "network_sizes": network_sizes,
    }


@app.get("/api/referral/tree/{user_id}")
async def referral_tree(user_id: int):
    users = all_users()
    ids = {u["user_id"] for u in users}
    if user_id not in ids:
        raise HTTPException(status_code=404, detail="user not found in referral map")

    # דמו: עץ חד-רמה – רק מי שמופיע עם referrer_id=user_id
    children = [u for u in users if u.get("referrer_id") == user_id]
    return {
        "user_id": user_id,
        "children": children,
    }


# =========================
# Startup
# =========================

@app.on_event("startup")
async def on_startup():
    logger.info("Starting SLHNET gateway service...")
    if BOT_TOKEN and WEBHOOK_URL:
        try:
            await application.bot.set_webhook(WEBHOOK_URL)
            logger.info(f"Webhook set to {WEBHOOK_URL}")
        except Exception as e:
            logger.error(f"Failed to set webhook: {e}")
    else:
        logger.error("BOT_TOKEN or WEBHOOK_URL not set – webhook not configured.")
    logger.info("Startup complete.")


@app.get("/")
async def root_landing():
    # redirect-like text for debugging; האתר עצמו רץ מ-GitHub Pages
    return PlainTextResponse("SLHNET Bot/API backend is running.")
