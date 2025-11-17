import logging
import asyncio

from telegram.ext import Application, CommandHandler, ContextTypes
from telegram import Update

from config import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def build_start_message() -> str:
    lines = [
        "ברוך הבא ל-Buy My Shop / SLH Digital Assets!\n",
        "כאן אתה רוכש גישה לקהילה סגורה + דשבורד נכסים דיגיטליים + הכנסה מרשת שיווק.\n",
    ]
    if config.NOTIFICATION_SETTINGS.get("community_group_link"):
        lines.append(f"👥 קהילת העסק: {config.NOTIFICATION_SETTINGS['community_group_link']}\n")
    if config.NOTIFICATION_SETTINGS.get("support_group_link"):
        lines.append(f"🆘 קבוצת תמיכה: {config.NOTIFICATION_SETTINGS['support_group_link']}\n")
    if config.LANDING_URL:
        lines.append(f"🌐 דף נחיתה: {config.LANDING_URL}\n")
    if config.PAYMENT_LINKS.get("paybox") or config.PAYMENT_LINKS.get("bit") or config.PAYMENT_LINKS.get("paypal"):
        lines.append("\nאפשרויות תשלום: ")
        if config.PAYMENT_LINKS.get("paybox"):
            lines.append(f"PayBox – {config.PAYMENT_LINKS['paybox']} ")
        if config.PAYMENT_LINKS.get("bit"):
            lines.append(f"• Bit – {config.PAYMENT_LINKS['bit']} ")
        if config.PAYMENT_LINKS.get("paypal"):
            lines.append(f"• PayPal – {config.PAYMENT_LINKS['paypal']} ")
    return "\n".join(lines)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(build_start_message())

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("פקודות בסיס: /start, /help")

async def main():
    if not config.BOT_TOKEN:
        logger.error("BOT_TOKEN not set – cannot start Telegram bot")
        return
    app = Application.builder().token(config.BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    logger.info("Starting Telegram bot polling ...")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
