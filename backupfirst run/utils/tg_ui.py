from telegram import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

def reply_menu(paid: bool) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton("📊 יתרה"), KeyboardButton("👤 פרופיל")],
        [KeyboardButton("🧾 תשלום כניסה"), KeyboardButton("🔗 שמור ארנק")],
    ]
    if paid:
        rows += [
            [KeyboardButton("🛒 קנייה (דמה)"), KeyboardButton("🏪 מכירה (דמה)")],
            [KeyboardButton("🔁 העברה (דמה)"), KeyboardButton("📜 היסטוריה")],
        ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

def kb_inline(rows):
    return InlineKeyboardMarkup([[InlineKeyboardButton(t, callback_data=d) for (t,d) in row] for row in rows])