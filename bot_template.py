# bot_template.py
"""
תבנית בוט בסיסית שניתן לשכפל עבור משתמשים
"""

BOT_TEMPLATE_CODE = '''
import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Configuration
BOT_TOKEN = "{bot_token}"
ADMIN_USER_ID = {user_id}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    user = update.effective_user
    
    welcome_text = (
        "🤖 *ברוך הבא לבוט האישי שלי!*\\n\\n"
        "אני הבוט האישי של @{owner_username}\\n"
        "כאן תוכל למצוא:\\n"
        "• נכסים דיגיטליים למכירה\\n"
        "• קישורים להצטרפות לקהילה\\n"
        "• מידע על מוצרים ושירותים\\n\\n"
        "לפרטים נוספים פנה לבעל הבוט!"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 נכסים דיגיטליים", callback_data="digital_assets")],
        [InlineKeyboardButton("👥 הצטרף לקהילה", url="{community_link}")],
        [InlineKeyboardButton("📞 צור קשר", url="https://t.me/{owner_username}")],
    ])
    
    await update.message.reply_text(
        welcome_text.format(owner_username="{owner_username}"),
        parse_mode="Markdown",
        reply_markup=keyboard
    )

async def digital_assets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show digital assets"""
    query = update.callback_query
    await query.answer()
    
    text = (
        "💎 *נכסים דיגיטליים זמינים*\\n\\n"
        "1. **נכס בסיסי** - 39₪\\n"
        "   • גישה לקהילת עסקים\\n"
        "   • לינק הפצה אישי\\n"
        "   • בוט טלגרם אישי\\n\\n"
        "2. **חבילת מתקדם** - 99₪\\n"
        "   • כל מה שבנכס הבסיסי\\n"
        "   • הדרכה אישית\\n"
        "   • תמיכה טכנית\\n\\n"
        "3. **חבילת עסקים** - 199₪\\n"
        "   • כל מה שבחבילת המתקדם\\n"
        "   • ניהול צוות\\n"
        "   • כלים מתקדמים\\n\\n"
        "לפרטים נוספים:@{owner_username}"
    )
    
    await query.edit_message_text(
        text.format(owner_username="{owner_username}"),
        parse_mode="Markdown"
    )

def main():
    """Start the bot"""
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(digital_assets, pattern="^digital_assets$"))
    
    # Start polling
    application.run_polling()

if __name__ == "__main__":
    main()
'''
