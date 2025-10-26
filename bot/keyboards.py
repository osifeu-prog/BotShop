from telegram import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

def user_reply_keyboard():
    rows = [
        [KeyboardButton("🧭 תפריט"), KeyboardButton("🧾 סטטוס")],
        [KeyboardButton("💳 תשלום"), KeyboardButton("📥 הצטרפות לקבוצה")],
        [KeyboardButton("🧮 היסטוריה")]
    ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=False, is_persistent=True)

def pay_inline_menu(pay_urls: dict):
    rows = []
    if pay_urls.get("paypal"):
        rows.append([InlineKeyboardButton("PayPal", url=pay_urls["paypal"])])
    rows.append([InlineKeyboardButton("פרטי בנק", callback_data="pay_bank"),
                 InlineKeyboardButton("ביט/פייבוקס", callback_data="pay_bit")])
    return InlineKeyboardMarkup(rows)

def confirm_paid_inline(chat_id: int, deal_id: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ אשר תשלום", callback_data=f"admin_mark_paid:{chat_id}:{deal_id}")],
    ])