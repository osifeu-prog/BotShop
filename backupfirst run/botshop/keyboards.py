from telegram import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

def reply_main() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton("💳 תשלום"), KeyboardButton("📥 הצטרפות")],
        [KeyboardButton("ℹ️ מצב"), KeyboardButton("👥 קבוצה")],
    ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=False, input_field_placeholder="בחר פעולה…")

def inline_pay_actions(invite_link: str) -> InlineKeyboardMarkup:
    btns = [
        [InlineKeyboardButton("שליחת אסמכתה ✅", callback_data="pay_proof")],
    ]
    if invite_link:
        btns.append([InlineKeyboardButton("כניסה לקבוצה 👥", url=invite_link)])
    return InlineKeyboardMarkup(btns)