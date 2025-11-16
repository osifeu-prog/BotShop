import logging
import os
from typing import Optional, Dict

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
import asyncio

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("botshop-gateway-minimal")

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
BOT_USERNAME = os.getenv("BOT_USERNAME", "Buy_My_Shop_bot")

# קבוצת לוגים / אדמינים (chat_id כ-int, לא לינק)
ADMIN_LOG_CHAT_ID = os.getenv("ADMIN_LOG_CHAT_ID")
# קבוצת העסקים אליה מקבלים קישור אחרי אישור (Invite link קבוע)
BUSINESS_GROUP_URL = os.getenv("BUSINESS_GROUP_URL") or os.getenv("GROUP_STATIC_INVITE")
# קבוצת תמיכה  לשם נשלחות פניות תמיכה
SUPPORT_GROUP_ID = os.getenv("SUPPORT_GROUP_ID")

LANDING_URL = os.getenv("LANDING_URL", "https://slh-nft.com")
PAYBOX_URL = os.getenv("PAYBOX_URL")
PAYPAL_URL = os.getenv("PAYPAL_URL")
BIT_PHONE = os.getenv("BIT_URL")  # טלפון להעברת ביט
SLH_NIS = os.getenv("SLH_NIS", "39")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is required")

# === FastAPI app ===
app = FastAPI(title="Buy My Shop  Gateway Bot")

# שרת את docs כסטטי
docs_path = os.path.join(os.path.dirname(__file__), "docs")
if os.path.isdir(docs_path):
    app.mount("/site", StaticFiles(directory=docs_path, html=True), name="site")


@app.get("/", response_class=HTMLResponse)
async def root():
    # הפניה לדף התדמיתי
    return RedirectResponse(url="/site/index.html")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "telegram-gateway-community-bot", "db": "disabled"}


# === Telegram Application ===
telegram_app: Application = ApplicationBuilder().token(BOT_TOKEN).build()

# זיכרון מינימלי לבקשות תמיכה
SUPPORT_WAITING: Dict[int, bool] = {}


def _safe_int(value: Optional[str]) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def build_main_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("איך מצטרפים?", callback_data="how_to_join"),
        ],
        [
            InlineKeyboardButton("שליחת הוכחת תשלום", callback_data="send_proof"),
        ],
        [
            InlineKeyboardButton("תמיכה טכנית", callback_data="support"),
        ],
        [
            InlineKeyboardButton("לאתר הפרויקט", url=LANDING_URL),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


async def notify_admins_new_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not ADMIN_LOG_CHAT_ID:
        return

    chat = update.effective_chat
    user = update.effective_user
    text = (
        "📥 הפעלה חדשה של הבוט\n"
        f"Chat ID: {chat.id}\n"
        f"User ID: {user.id}\n"
        f"Username: @{user.username if user.username else '-'}\n"
        f"Full name: {user.full_name}\n"
    )
    try:
        await context.bot.send_message(chat_id=int(ADMIN_LOG_CHAT_ID), text=text)
    except Exception as e:
        logger.error("Failed to notify admins on start: %s", e)


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await notify_admins_new_start(update, context)

    text = (
        "🌐 *שער הכניסה לקהילת העסקים של SLH*\n\n"
        f"עלות ההצטרפות: *{SLH_NIS} ש\"ח* בלבד (חדפעמי).\n\n"
        "מה תקבלו לאחר אישור התשלום:\n"
        "• גישה לקבוצת עסקים פרטית וסגורה.\n"
        "• נכסים דיגיטליים (בוטים, קלפים, NFT, טוקני SLH) שיחולקו בקבוצה.\n"
        "• הסבר איך להשתמש בבוטים כדי לייצר הכנסה משיתופים.\n"
        "• קישור אישי לשיתוף  שמאפשר לכם להרוויח מהפניות נוספות.\n\n"
        "כדי להתחיל  בחרו אחת מהאפשרויות שלמטה."
    )
    await update.effective_chat.send_message(
        text=text,
        reply_markup=build_main_keyboard(),
        parse_mode="Markdown",
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start_cmd(update, context)


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == "how_to_join":
        lines = [
            "🧭 *איך מצטרפים לקהילת העסקים?*",
            "",
            f"1. מעבירים *{SLH_NIS} ש\"ח* באחת מהאפשרויות הבאות:",
        ]
        if PAYBOX_URL:
            lines.append(f"• PayBox: {PAYBOX_URL}")
        if PAYPAL_URL:
            lines.append(f"• PayPal: {PAYPAL_URL}")
        if BIT_PHONE:
            lines.append(f"• Bit / העברה בנקאית לטלפון: {BIT_PHONE}")
        lines.extend(
            [
                "",
                "2. לאחר ביצוע התשלום  חוזרים לבוט ולוחצים על _\"שליחת הוכחת תשלום\"_.",
                "3. מעלים צילום מסך / צילום של האישור.",
                "4. לאחר האישור  תקבלו קישור לקבוצת העסקים הסגורה שלנו.",
            ]
        )
        await query.edit_message_text(
            "\n".join(lines),
            parse_mode="Markdown",
            reply_markup=build_main_keyboard(),
        )

    elif query.data == "send_proof":
        await query.edit_message_text(
            "📤 *שליחת הוכחת תשלום*\n\n"
            "נא העלה כאן צילום מסך של האישור (PayBox / PayPal / העברה בנקאית).\n"
            "אנו נבדוק ונאשר, ואז נשלח לך קישור לקבוצת העסקים.",
            parse_mode="Markdown",
            reply_markup=build_main_keyboard(),
        )

    elif query.data == "support":
        user_id = update.effective_user.id
        SUPPORT_WAITING[user_id] = True
        await query.edit_message_text(
            "🆘 *תמיכה טכנית*\n\n"
            "כתוב עכשיו את הפנייה שלך (טקסט בלבד), ואעביר אותה ישירות לצוות התמיכה.",
            parse_mode="Markdown",
            reply_markup=build_main_keyboard(),
        )


async def handle_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not SUPPORT_GROUP_ID:
        return

    user = update.effective_user
    chat = update.effective_chat

    if not update.message or not update.message.text:
        return

    if not SUPPORT_WAITING.get(user.id):
        return

    SUPPORT_WAITING[user.id] = False

    text = update.message.text
    msg = (
        "🆘 *פניית תמיכה חדשה*\n\n"
        f"From User ID: `{user.id}`\n"
        f"Username: @{user.username if user.username else '-'}\n"
        f"Chat ID: `{chat.id}`\n\n"
        f"Message:\n{text}"
    )
    try:
        await context.bot.send_message(
            chat_id=int(SUPPORT_GROUP_ID),
            text=msg,
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error("Failed to send support message to group: %s", e)

    await update.message.reply_text(
        "✅ פנייתך נשלחה לתמיכה. נשיב לך בהקדם האפשרי."
    )


async def handle_payment_proof(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not ADMIN_LOG_CHAT_ID:
        await update.message.reply_text(
            "התקבלה הוכחת תשלום. המערכת בתהליך הגדרה, נעדכן לאחר האישור."
        )
        return

    user = update.effective_user
    chat = update.effective_chat

    caption = (
        "📥 *התקבלה הוכחת תשלום חדשה*\n\n"
        f"From User ID: `{user.id}`\n"
        f"Username: @{user.username if user.username else '-'}\n"
        f"Full name: {user.full_name}\n"
        f"Chat ID: `{chat.id}`\n"
    )

    try:
        if update.message.photo:
            photo = update.message.photo[-1]
            await context.bot.send_photo(
                chat_id=int(ADMIN_LOG_CHAT_ID),
                photo=photo.file_id,
                caption=caption,
                parse_mode="Markdown",
            )
        elif update.message.document:
            await context.bot.send_document(
                chat_id=int(ADMIN_LOG_CHAT_ID),
                document=update.message.document.file_id,
                caption=caption,
                parse_mode="Markdown",
            )
        else:
            await context.bot.send_message(
                chat_id=int(ADMIN_LOG_CHAT_ID),
                text=caption + "\n(ללא קובץ מצורף)",
                parse_mode="Markdown",
            )
    except Exception as e:
        logger.error("Failed to forward payment proof: %s", e)

    await update.message.reply_text(
        "✅ קיבלנו את האישור. לאחר בדיקה ואישור ידני תקבל קישור לקבוצת העסקים."
    )


async def approve_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    \"\"\"/approve <user_id>  לרשום בקבוצת האדמינים בלבד.\"\"\"
    if not BUSINESS_GROUP_URL:
        await update.message.reply_text("BUSINESS_GROUP_URL לא מוגדר במערכת.")
        return

    if not ADMIN_LOG_CHAT_ID or update.effective_chat.id != int(ADMIN_LOG_CHAT_ID):
        await update.message.reply_text("הפקודה זמינה רק בקבוצת האדמינים.")
        return

    if not context.args:
        await update.message.reply_text("שימוש: /approve <user_id>")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("user_id לא תקין.")
        return

    text_user = (
        "🎉 התשלום שלך אושר!\n\n"
        "הנה הקישור לקבוצת העסקים הפרטית שלנו:\n"
        f"{BUSINESS_GROUP_URL}\n\n"
        "נתראה בפנים  מחכים לך עם כל הבוטים וההטבות. "
    )
    try:
        await context.bot.send_message(chat_id=target_id, text=text_user)
    except Exception as e:
        await update.message.reply_text(f"שגיאה בשליחת הודעה למשתמש: {e}")
        return

    await update.message.reply_text(
        f"✅ נשלח קישור הצטרפות למשתמש {target_id}."
    )


# רישום handlers
telegram_app.add_handler(CommandHandler("start", start_cmd))
telegram_app.add_handler(CommandHandler("help", help_cmd))
telegram_app.add_handler(CommandHandler("approve", approve_cmd))

telegram_app.add_handler(CallbackQueryHandler(callback_handler))

telegram_app.add_handler(
    MessageHandler(
        filters.TEXT & filters.ChatType.PRIVATE,
        handle_support_message,
    )
)

telegram_app.add_handler(
    MessageHandler(
        (filters.PHOTO | filters.Document.IMAGE) & filters.ChatType.PRIVATE,
        handle_payment_proof,
    )
)


@app.on_event("startup")
async def on_startup() -> None:
    logger.info("Starting Telegram application (webhook mode)...")
    await telegram_app.initialize()
    await telegram_app.start()
    if WEBHOOK_URL:
        try:
            await telegram_app.bot.set_webhook(WEBHOOK_URL)
            logger.info("Webhook set to %s", WEBHOOK_URL)
        except Exception as e:
            logger.error("Failed to set webhook: %s", e)


@app.on_event("shutdown")
async def on_shutdown() -> None:
    logger.info("Stopping Telegram application...")
    await telegram_app.stop()
    await telegram_app.shutdown()


@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return JSONResponse({"ok": True})
