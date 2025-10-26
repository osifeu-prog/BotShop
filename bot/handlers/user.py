from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
import re

_WALLET_RE = re.compile(r'^0x[a-fA-F0-9]{40}$')

def user_reply_keyboard():
    rows = [
        [KeyboardButton("👤 הפרופיל שלי"), KeyboardButton("💰 קנייה/מכירה")],
        [KeyboardButton("💸 העברה"), KeyboardButton("ℹ️ מידע")]
    ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "ברוך הבא ל-Botshop ✨\nשלח 0x… לשמירת כתובת MetaMask, או השתמש בתפריט למטה."
    if update.message:
        await update.message.reply_text(msg, reply_markup=user_reply_keyboard())

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if _WALLET_RE.match(text):
        context.user_data["wallet"] = text
        await update.message.reply_text("✅ כתובת נשמרה!")
        return

    if text == "ℹ️ מידע":
        await update.message.reply_text("זה בוט דמו: קנייה/מכירה/העברה יתממשקו בהמשך.")
        return

    if text == "👤 הפרופיל שלי":
        w = context.user_data.get("wallet","(לא הוגדר)")
        await update.message.reply_text(f"כתובת: {w}")
        return

    await update.message.reply_text("לא זוהה. לחץ /start או בחר מהתפריט.")
