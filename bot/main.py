import os, logging
from dotenv import load_dotenv

try:
    from telegram import Update
    from telegram.ext import Application, CommandHandler, ContextTypes
except Exception as e:
    raise RuntimeError("python-telegram-bot not installed. Check requirements.txt") from e

load_dotenv()
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
log = logging.getLogger("Botshop")

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Botshop is alive ✅  |  /start")

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN missing")
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    log.info("Starting polling…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()