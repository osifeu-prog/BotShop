from telegram import InlineKeyboardMarkup, InlineKeyboardButton

def main_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("📥 שליחת אישור תשלום", callback_data="send_payment_proof")],
        [InlineKeyboardButton("ℹ️ סטטוס תשלום", callback_data="payment_status")],
    ]
    return InlineKeyboardMarkup(buttons)


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("📄 תשלומים ממתינים", callback_data="admin_list_pending")],
    ]
    return InlineKeyboardMarkup(buttons)
